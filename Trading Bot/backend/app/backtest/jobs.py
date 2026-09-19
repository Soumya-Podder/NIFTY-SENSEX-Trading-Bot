"""Durable, single-worker backtests; browser lifetime never owns a running job."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import threading
import uuid
import math
import pandas as pd
from .data import dataset_path, read_contract_csv
from .reconstruction import dhan_research,dhan_plan_research
from .engine import BacktestConfig, BacktestEngine
from .reports import report_from_run
from .walk_forward import validation_windows
from ..telemetry.agent_metrics import learn_from_outcomes
from ..market_data import HISTORY_CACHE_ONLY
from ..risk import PlanRiskPolicy
from ..ai import LearningService
from .strategy_signals import MODES

ACTIVE={"queued","running","cancelling"}
ARCHIVE_STRIKE_OFFSETS=("ATM","ATM-4","ATM-3","ATM-2","ATM-1","ATM+1","ATM+2","ATM+3","ATM+4")
ARCHIVE_EXTENSION_OFFSETS=("ATM-6","ATM-5","ATM+5","ATM+6")
ARCHIVE_FIELDS=("open","high","low","close","volume","oi","strike","spot","iv")


def resolve_backtest_start(end, from_date=None, days=None, years=1):
    """Resolve a user-selected range without treating an explicit zero year as one year."""
    if from_date is not None: return from_date
    if days is not None: return end-timedelta(days=days-1)
    return (pd.Timestamp(end)-pd.DateOffset(years=years if years is not None else 1)).date()


def download_history(gateway,config,progress,cancel,checkpoint):
    """Archive source observations only; never run a strategy or update learning."""
    fields=list(config.get("fields",ARCHIVE_FIELDS))
    # Dhan's documented rolling buckets are near/next/far (codes 1/2/3).
    # The requested archive uses the same explicit strike set for every
    # bucket and both expiry flags; no offset is silently omitted.
    expiry_codes=tuple(config.get("expiry_codes",(1,2,3)))
    strike_offsets=tuple(config.get("strike_offsets",ARCHIVE_STRIKE_OFFSETS))
    contracts=[(code,offset) for code in expiry_codes for offset in strike_offsets]
    start=pd.Timestamp(config["from"]); end=pd.Timestamp(config["to"])+timedelta(days=1)
    chunks=[]; cursor=start
    while cursor<end:
        stop=min(cursor+timedelta(days=29),end)
        chunks.append((str(cursor.date()),str(stop.date()))); cursor=stop
    underlyings={u["symbol"]:u for u in gateway.underlyings()}
    total=len(chunks)*len(config["symbols"])*(1+2*2*len(contracts))
    counts={"processed":0,"total":total,"nonempty_responses":0,"empty_responses":0,"observations":0}
    for a,b in reversed(chunks):
        for symbol in config["symbols"]:
            if cancel(): raise InterruptedError("Cancelled")
            progress(f"Downloading {symbol} index {a} to {b}",counts["processed"],total)
            frame=gateway.candles(symbol,a,b,cache_seconds=-1,cancel=cancel)
            counts["processed"]+=1; counts["observations"]+=len(frame)
            counts["nonempty_responses" if len(frame) else "empty_responses"]+=1
            checkpoint(dict(counts))
            under=underlyings[symbol]
            for flag in ("WEEK","MONTH"):
                for side in ("CALL","PUT"):
                    for code,offset in contracts:
                        if cancel(): raise InterruptedError("Cancelled")
                        progress(f"Downloading {symbol} {a} to {b}: {flag} expiry {code} {side} {offset}",counts["processed"],total)
                        raw=gateway.call(gateway.client.expired_options_data,under["security_id"],under["exchange_segment"],
                            "OPTIDX",flag,code,offset,side,fields,a,b,1,cache_seconds=-1,cancel=cancel)
                        size=len((raw.get("ce" if side=="CALL" else "pe") or {}).get("timestamp",[]))
                        counts["processed"]+=1; counts["observations"]+=size
                        counts["nonempty_responses" if size else "empty_responses"]+=1
                        checkpoint(dict(counts))
    return counts


def archive_manifest(job_id, config, counts, completed_at):
    """Describe the retained source pass without claiming complete exchange coverage."""
    symbols=list(config.get("symbols", []))
    offsets=list(config.get("strike_offsets", ARCHIVE_STRIKE_OFFSETS))
    expiry_codes=list(config.get("expiry_codes", [1, 2, 3]))
    start=config.get("from"); end=config.get("to")
    chunk_count=max(0,math.ceil((pd.Timestamp(end)+pd.Timedelta(days=1)-pd.Timestamp(start)).days/29)) if start and end else 0
    expected_per_symbol_chunk=1+2*2*len(expiry_codes)*len(offsets)
    return {
        "job_id": job_id,
        "source": config.get("source"),
        "symbols": symbols,
        "requested_from": config.get("requested_from", config.get("from")),
        "actual_from": config.get("from"),
        "actual_to": config.get("to"),
        "interval": config.get("interval", 1),
        "expiry_codes": expiry_codes,
        "strike_offsets": offsets,
        "sides": ["CALL", "PUT"],
        "expiry_flags": ["WEEK", "MONTH"],
        "fields": list(config.get("fields",ARCHIVE_FIELDS)),
        "request_count": counts.get("total", 0),
        "chunk_count": chunk_count,
        "expected_requests_per_symbol_chunk": expected_per_symbol_chunk,
        "expected_request_count": chunk_count*len(symbols)*expected_per_symbol_chunk,
        "processed_requests": counts.get("processed", 0),
        "nonempty_responses": counts.get("nonempty_responses", 0),
        "empty_responses": counts.get("empty_responses", 0),
        "observations": counts.get("observations", 0),
        "coverage_status": "downloaded_source_responses_not_completeness_certified",
        "retention": "compressed SQLite history_cache; overlapping requests are reused",
        "completed_at": completed_at,
    }


def resolve_backtest_budgets(config,settings):
    result=dict(config)
    result.setdefault("capital",settings.paper_capital)
    result.setdefault("risk_per_trade",settings.max_trade_risk_rupees)
    for key,base in (("daily_loss_limit",settings.daily_loss_limit_rupees),("correlated_risk_limit",settings.max_correlated_risk_rupees)):
        if result.get(key) is None: result[key]=result["risk_per_trade"]*(base/settings.max_trade_risk_rupees)
    for key in ("capital","risk_per_trade","daily_loss_limit","correlated_risk_limit"):
        if not math.isfinite(result[key]) or result[key]<=0: raise ValueError(f"{key} must resolve to a positive finite number")
    return result


class BacktestJobs:
    def __init__(self,store,gateway,settings,data_dir):
        self.store=store; self.gateway=gateway; self.settings=settings; self.data_dir=data_dir
        self.lock=threading.RLock(); self.cancel_event=threading.Event(); self.worker=None
        self.finalizing=False

    def recover(self):
        for job in self.store.list_records("jobs",10000):
            if job["status"] in ACTIVE:
                job.update(status="interrupted",message="Server restarted; cached data retained. Run again to resume from cache.")
                self.store.put_record("jobs",job["id"],job)

    def start(self,config):
        with self.lock:
            if self.worker and self.worker.is_alive(): raise ValueError("A backtest is already running")
            strategy_mode=config.get("strategy_mode")
            if config.get("estimate_missing_exits") and config.get("source")!="dhan":
                raise ValueError("Estimated exit scenarios currently support Dhan rolling research only")
            if strategy_mode is not None and strategy_mode not in MODES:
                raise ValueError("Unknown strategy replay mode")
            if strategy_mode and config.get("source")!="csv":
                raise ValueError("Individual/portfolio replay requires observed exact-contract CSV data; rolling Dhan research does not yet provide equivalent execution inputs")
            config=resolve_backtest_budgets(config,self.settings)
            self.cancel_event=threading.Event()
            self.finalizing=False
            identifier=str(uuid.uuid4())
            job={"id":identifier,"status":"queued","config":config,"progress":0,
                 "message":"Queued","created_at":datetime.now(timezone.utc).isoformat()}
            self.store.put_record("jobs",identifier,job)
            self.worker=threading.Thread(target=self._run,args=(identifier,config),name="backtest-worker",daemon=True)
            self.worker.start()
            return job

    def update(self,identifier,**fields):
        with self.lock:
            job=self.store.get_record("jobs",identifier)
            job.update(**fields,updated_at=datetime.now(timezone.utc).isoformat())
            self.store.put_record("jobs",identifier,job)
            return job

    def cancel(self,identifier):
        with self.lock:
            job=self.store.get_record("jobs",identifier)
            if not job: raise KeyError(identifier)
            if job["status"] in ACTIVE:
                if self.finalizing: return {**job,"message":"Validated results are being committed; cancellation is no longer available"}
                self.cancel_event.set()
                job=self.update(identifier,status="cancelling",message="Cancellation requested; waiting for the current bounded operation")
            return job

    def stop(self):
        if not self.finalizing: self.cancel_event.set()
        if self.worker: self.worker.join(timeout=2)

    def _run(self,identifier,config):
        cache_token=HISTORY_CACHE_ONLY.set(bool(config.get("history_cache_only")) and not config.get("download_only"))
        def cancelled(): return self.cancel_event.is_set()
        def progress(stage,current,total):
            if cancelled(): raise InterruptedError("Cancelled")
            self.update(identifier,status="running",message=stage,progress=min(99,round(100*current/max(total,1),1)))
        def before_commit():
            with self.lock:
                if cancelled(): raise InterruptedError("Cancelled")
                self.finalizing=True
        try:
            progress("Validating historical source",0,1)
            if config.get("download_only"):
                counts=download_history(self.gateway,config,progress,cancelled,
                    lambda counts:self.update(identifier,download=counts))
                completed_at=datetime.now(timezone.utc).isoformat()
                manifest=archive_manifest(identifier,config,counts,completed_at)
                self.store.put_record("history_archives",identifier,manifest)
                self.update(identifier,status="download_complete",progress=100,
                    archive_manifest_id=identifier,
                    message=f"Download pass finished: {counts['nonempty_responses']} populated responses; {counts['empty_responses']} empty responses (not verified coverage). Cached data retained; no strategy or learning executed.")
                return
            replay=None; windows=None; dataset_id=None; ml_replay=None
            if config["source"]=="dhan":
                if not self.settings.dhan_client_id or not self.settings.dhan_access_token: raise ValueError("Dhan credentials are not configured")
                result=dhan_research(self.gateway,config,progress,cancelled,self.settings)
            else:
                path=dataset_path(self.data_dir,config["dataset"])
                frame,dataset_id=read_contract_csv(path,config,cancelled)
                cfg=BacktestConfig(initial_capital=config["capital"],risk_per_trade=config["risk_per_trade"],
                    daily_loss_limit=config.get("daily_loss_limit",self.settings.daily_loss_limit_rupees),correlated_risk_limit=config.get("correlated_risk_limit",self.settings.max_correlated_risk_rupees),
                    max_positions=self.settings.max_open_positions,daily_target=self.settings.daily_profit_target,
                    entry_cutoff=self.settings.entry_cutoff,exit_at=self.settings.session_exit,adaptive_exits=bool(config.get("strategy_mode")),
                    horizon_minutes=10,min_stop=0.0,invalidation_buffer=0.0,strategy_mode=config.get("strategy_mode"))
                if config.get("strategy_version")=="orb-retest-v1" or cfg.strategy_mode:
                    # Research inputs are editable; do not cap them to the paper
                    # account. Preserve the declared allocation/reserve ratios.
                    base=PlanRiskPolicy.from_settings(self.settings)
                    ratio=config["daily_loss_limit"]/(base.loss_allocation+base.emergency_reserve)
                    plan=replace(base,trade_risk=config["risk_per_trade"],loss_allocation=base.loss_allocation*ratio,
                        emergency_reserve=base.emergency_reserve*ratio,
                        premium_limit=config["capital"]*(base.premium_limit/self.settings.paper_capital),
                        cash_reserve=config["capital"]*(base.cash_reserve/self.settings.paper_capital),
                        weekly_loss=base.weekly_loss*ratio,
                        max_drawdown=base.max_drawdown*ratio)
                    cfg=replace(cfg,plan_policy=plan,max_positions=1,cooldown_bars=plan.cooldown_minutes)
                # Frozen base rules for historical reporting; today's learned policies would leak future outcomes.
                result=BacktestEngine(cfg).run(frame,cancelled,lambda n,total:progress("Replaying shared-capital portfolio",n,total))
                dates=sorted(set(frame.timestamp.dt.strftime("%Y-%m-%d")))
                windows=validation_windows(dates)
                config={**config,"dataset_id":dataset_id,"actual_from":dates[0],"actual_to":dates[-1],"observed_sessions":len(dates)}
                replay_cache={}
                def replay(policies,start,end):
                    import json
                    key=(json.dumps(policies,sort_keys=True),start,end)
                    if key not in replay_cache:
                        progress(f"Validating agents: {start} to {end}",0,1)
                        # Retain preceding bars for indicator warmup, but do not trade them.
                        subset=frame[frame.timestamp.dt.strftime("%Y-%m-%d")<=end]
                        replay_cache[key]=BacktestEngine(replace(cfg,trade_from=start,learning_policies=policies)).run(subset,cancelled)
                    return replay_cache[key]
                def ml_replay(artifact,start,end):
                    subset=frame[frame.timestamp.dt.strftime("%Y-%m-%d")<=end]
                    baseline=BacktestEngine(replace(cfg,trade_from=start)).run(subset,cancelled)
                    candidate=BacktestEngine(replace(cfg,trade_from=start,ml_artifact=artifact)).run(subset,cancelled)
                    return candidate,baseline
            if cancelled(): raise InterruptedError("Cancelled")
            report=report_from_run(result,config)
            progress("Recording agent feedback and validation evidence",0,1)
            if not config.get("estimate_missing_exits"):
                learn_from_outcomes(report["trades"],config["source"],self.store,identifier,
                    quality=report["quality"],replay=replay if windows else None,dataset_id=dataset_id,windows=windows,before_commit=before_commit)
            run=self.store.get_record("learning_runs",identifier,{})
            report.update(run_id=identifier,learning_run=run.get("entries",[]),validation_windows=windows,
                          created_at=datetime.now(timezone.utc).isoformat())
            with self.lock:
                if cancelled(): raise InterruptedError("Cancelled")
                job=self.store.get_record("jobs",identifier)
                job.update(status=report["status"],progress=100,message="Report saved",report_id=identifier)
                self.store.save_bundle([("reports",identifier,report),("jobs",identifier,job),
                    ("backtest","latest",{"report_id":identifier})])
            try:
                learning=({"status":"EXCLUDED_ESTIMATED_SCENARIO","reason":"Estimated account paths cannot train or promote models"} if config.get("estimate_missing_exits") else LearningService(self.store).train(report,identifier,replay=ml_replay))
                report["ml_learning"]=learning
                self.store.put_record("reports",identifier,report)
            except Exception as exc:
                self.store.put_record("ml_state","latest",{"status":"TRAINING_FAILED","error":type(exc).__name__,"run_id":identifier})
        except InterruptedError:
            self.update(identifier,status="cancelled",message="Cancelled; previous reports and cached data retained")
        except Exception as exc:
            message=str(exc)
            for secret in (self.settings.dhan_client_id,self.settings.dhan_access_token):
                if secret: message=message.replace(secret,"[redacted]")
            self.update(identifier,status="failed",message=message[:600],progress=None)
        finally:
            HISTORY_CACHE_ONLY.reset(cache_token)
