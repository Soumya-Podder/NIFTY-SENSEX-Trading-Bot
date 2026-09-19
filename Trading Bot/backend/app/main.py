import asyncio
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from .config import settings,current_credentials
from .store import Store, json_safe
from .broker import PaperBroker
from .expectancy import CostModel
from .market_data import DhanGateway, DhanMarketData
from .paper_engine import PaperEngine
from .portfolio_engine import MultiStrategyPaperEngine
from .session import now_ist, session_state
from .backtest.jobs import BacktestJobs,resolve_backtest_start
from .telemetry.agent_metrics import agent_metrics_from_events, plan_agent_capabilities
from .telemetry.decision_trace import pipeline_from_events
from .telemetry.event_bus import event_bus
from .risk import PlanRiskPolicy
from .ai import LearningService, get_analysts
from .learning_monitor import LearningMonitor
from .provenance import reviewed_report
from .backtest.presentation import report_view, history_row
from .runtime_health import execution_health
from .backtest.data import dataset_metadata
from .market_calendar import calendar_info
from .quote_recorder import QuoteRecorder
from .forward_comparison import ForwardComparison
from .autonomous_agent import AutonomousTradingAgent, get_autonomous_agent
import threading
import uuid
import asyncio

ROOT=Path(__file__).resolve().parents[2]
store=Store(ROOT/"backend"/"trading_bot.db")
gateway=DhanGateway(settings,store,credential_provider=current_credentials)
plan_policy=PlanRiskPolicy.from_settings(settings)
paper=PaperBroker(store,settings.paper_capital,CostModel(store),settings.max_quote_age_seconds,entry_cutoff=settings.entry_cutoff,policy=plan_policy)
market_data=DhanMarketData(settings.dhan_client_id,settings.dhan_access_token,"NIFTY,SENSEX",gateway,store)
quote_recorder=QuoteRecorder(ROOT/"data"/"market_observations.db")
market_data.recorder=quote_recorder
engine_class=MultiStrategyPaperEngine if settings.paper_strategy_mode=="portfolio" else PaperEngine
engine=engine_class(settings,store,gateway,paper,market_data)
forward_comparison=ForwardComparison(store,engine)
engine.research_positions=forward_comparison.positions
engine.forward_comparison=forward_comparison
jobs=BacktestJobs(store,gateway,settings,ROOT/"data")
ml_learning=getattr(engine,"learning",LearningService(store))
analysts = get_analysts()
llm_client = analysts.get("llm_client")

# Autonomous agent
autonomous_agent = get_autonomous_agent(ROOT)
autonomous_agent.set_dependencies(paper, market_data, engine)
autonomous_agent.backtest_jobs = jobs
learning_monitor = LearningMonitor(store, engine, ml_learning, ROOT/".env", autonomous_agent)


@asynccontextmanager
async def lifespan(app):
    jobs.recover()
    for item in reversed(store.list_records("events",80)): event_bus.publish(item)
    paper.control(enabled=settings.paper_autostart)
    quote_recorder.start()
    engine.start(); market_data.start()
    autonomous_agent.start()
    if isinstance(engine,MultiStrategyPaperEngine): forward_comparison.start()
    learning_monitor.start()
    yield
    learning_monitor.stop()
    forward_comparison.stop()
    autonomous_agent.stop()
    engine.stop(); jobs.stop(); market_data.stop()
    quote_recorder.stop()
    if llm_client:
        await llm_client.close()


app=FastAPI(title="Options Paper Lab",version="4.0.0",lifespan=lifespan)
ORIGINS={settings.web_origin,"http://127.0.0.1:5174","http://localhost:5174"}
app.add_middleware(CORSMiddleware,allow_origins=list(ORIGINS),allow_methods=["GET","POST"],allow_headers=["Content-Type"])


@app.middleware("http")
async def local_mutations(request:Request,call_next):
    if request.method=="POST" and request.headers.get("origin") and request.headers["origin"] not in ORIGINS:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail":"Untrusted browser origin"},status_code=403)
    return await call_next(request)


class ModeRequest(BaseModel):
    mode:Literal["paper","live"]


class PaperControl(BaseModel):
    enabled:bool|None=None


class BacktestRequest(BaseModel):
    model_config=ConfigDict(populate_by_name=True,extra="forbid")
    history_cache_only:bool=True
    estimate_missing_exits:bool=False
    estimate_haircut:float=Field(default=.05,ge=0,le=.25,allow_inf_nan=False)
    source:Literal["dhan","csv"]="dhan"
    underlying:Literal["NIFTY","SENSEX","PARALLEL"]="PARALLEL"
    years:int|None=Field(default=1,ge=0,le=5)
    days:int|None=Field(default=None,ge=1,le=365)
    from_date:date|None=Field(default=None,alias="from")
    to_date:date|None=Field(default=None,alias="to")
    capital:float=Field(default=settings.paper_capital,gt=0,allow_inf_nan=False)
    risk_per_trade:float=Field(default=settings.max_trade_risk_rupees,gt=0,allow_inf_nan=False)
    daily_loss_limit:float|None=Field(default=None,gt=0,allow_inf_nan=False)
    correlated_risk_limit:float|None=Field(default=None,gt=0,allow_inf_nan=False)
    dataset:str=""
    strategy_mode:Literal["orb_retest","trend_pullback","range_rejection","portfolio"]|None=None


class LearningReview(BaseModel):
    action:Literal["approve","reject"]
    reviewed_by:str=Field(min_length=1,max_length=120)
    reason:str=Field(default="",max_length=500)


def last_report():
    pointer=store.get_record("backtest","latest",{})
    return report_view(store.get_record("reports",pointer.get("report_id",""),{"status":"not_run","metrics":{},"trades":[]}))


@app.get("/api/learning/model")
def learning_model():
    return json_safe(ml_learning.status())


@app.post("/api/learning/train",status_code=202)
def train_learning_model():
    if ml_learning.lock.locked(): raise HTTPException(409,detail="Model training is already running")
    report=last_report()
    identifier="manual-"+uuid.uuid4().hex
    def train():
        try: ml_learning.train(report,identifier)
        except Exception as exc:
            store.put_record("ml_state","latest",{"status":"TRAINING_FAILED","run_id":identifier,"error":type(exc).__name__})
    threading.Thread(target=train,name="paper-model-training",daemon=True).start()
    return {"run_id":identifier,"status":"QUEUED","note":"New backtest jobs run automatic training and full replay where supported"}


# ──────────────────────────────────────────────────────────────
# LLM Analysis Endpoints
# ──────────────────────────────────────────────────────────────

class LLMMarketRequest(BaseModel):
    include_market_data: bool = True
    include_option_chain: bool = True
    include_recent_trades: int = 20


class LLMFailureRequest(BaseModel):
    trade_ids: list[str] | None = None
    lookback_days: int = 30
    min_pnl: float = 0  # negative = losses only


class LLMHypothesisRequest(BaseModel):
    include_market_analysis: bool = True
    include_failure_analysis: bool = True


class LLMTradeRequest(BaseModel):
    trade_id: str


@app.get("/api/llm/status")
def llm_status():
    return {
        "enabled": settings.llm_enabled,
        "configured": bool(settings.openrouter_api_key),
        "model": settings.openrouter_model if settings.llm_enabled else None,
        "analysts_llm_enhanced": analysts.get("llm_client") is not None,
    }


@app.post("/api/llm/analyze/market")
def llm_analyze_market(request: LLMMarketRequest):
    if not analysts.get("llm_client"):
        raise HTTPException(503, detail="LLM not configured. Set OPENROUTER_API_KEY and enable llm_enabled in .env")
    market_analyst = analysts["market"]
    state = {}
    if request.include_market_data:
        state["market_snapshot"] = market_data.snapshot()
    if request.include_option_chain:
        try:
            state["option_chain"] = {s: gateway.chain(s) for s in ("NIFTY", "SENSEX")}
        except Exception:
            state["option_chain"] = {}
    if request.include_recent_trades:
        recent = store.list_records("trades", request.include_recent_trades)
        state["recent_trades"] = recent
    state["session"] = session_state()
    return json_safe(market_analyst.analyze(state))


@app.post("/api/llm/analyze/failures")
def llm_analyze_failures(request: LLMFailureRequest):
    if not analysts.get("llm_client"):
        raise HTTPException(503, detail="LLM not configured")
    failure_analyst = analysts["failure"]
    trades = store.list_records("trades", 200)
    if request.trade_ids:
        trades = [t for t in trades if t.get("id") in request.trade_ids]
    else:
        cutoff = (now_ist() - timedelta(days=request.lookback_days)).isoformat()
        trades = [t for t in trades if t.get("exit_ts", "") >= cutoff and (t.get("pnl", 0) <= request.min_pnl)]
    return json_safe(failure_analyst.analyze(trades))


@app.post("/api/llm/generate/hypotheses")
def llm_generate_hypotheses(request: LLMHypothesisRequest):
    if not analysts.get("llm_client"):
        raise HTTPException(503, detail="LLM not configured")
    hypothesis_gen = analysts["hypothesis"]
    analysis = {}
    if request.include_market_analysis:
        market_state = {"market_snapshot": market_data.snapshot(), "session": session_state()}
        analysis["market_analysis"] = analysts["market"].analyze(market_state)
    if request.include_failure_analysis:
        recent_trades = store.list_records("trades", 100)
        losing = [t for t in recent_trades if t.get("pnl", 0) < 0]
        analysis["failure_analysis"] = analysts["failure"].analyze(losing)
    analysis["strategy_params"] = {
        "max_trade_risk_rupees": settings.max_trade_risk_rupees,
        "daily_loss_limit_rupees": settings.daily_loss_limit_rupees,
        "entry_cutoff": settings.entry_cutoff,
        "session_exit": settings.session_exit,
        "max_open_positions": settings.max_open_positions,
        "strategy_version": settings.strategy_version,
    }
    return json_safe(hypothesis_gen.generate(analysis))


@app.post("/api/llm/analyze/trade")
def llm_analyze_trade(request: LLMTradeRequest):
    if not analysts.get("llm_client"):
        raise HTTPException(503, detail="LLM not configured")
    trade_analyst = analysts["trade"]
    trade = store.get_record("trades", request.trade_id)
    if not trade:
        raise HTTPException(404, detail="Trade not found")
    return json_safe(trade_analyst.analyze(trade))


def redacted(value):
    if isinstance(value,dict): return {k:redacted(v) for k,v in value.items()}
    if isinstance(value,list): return [redacted(v) for v in value]
    if isinstance(value,str):
        for secret in (settings.dhan_access_token,settings.dhan_client_id):
            if secret: value=value.replace(secret,"[redacted]")
    return value


@app.get("/api/mode")
def mode():
    return {"mode":"paper","live_available":False,"live_trading_enabled":False,
            "reason":"Paper-only implementation; live orders are disabled server-side"}


@app.post("/api/mode")
def set_mode(request:ModeRequest):
    if request.mode=="live": raise HTTPException(409,detail=mode()["reason"])
    return mode()


@app.get("/api/health")
def health():
    runtime=execution_health(engine,paper)
    return json_safe(redacted({"app":"healthy" if runtime["healthy"] else "degraded",**mode(),"runtime":runtime,"calendar":calendar_info(now_ist().date()),"engine":engine.status,"broker":paper.health(),"market_data":market_data.snapshot()}))


@app.get("/api/risk")
def risk():
    account=paper.snapshot()
    return {"halted":account["halted"],"reason":account["halt_reason"],"max_trade_risk_rupees":settings.max_trade_risk_rupees,
        "daily_loss_limit_rupees":settings.daily_loss_limit_rupees,"max_correlated_risk_rupees":settings.max_correlated_risk_rupees,
        "hard_daily_halt_rupees":settings.hard_daily_halt_rupees,"max_open_positions":settings.max_open_positions,
        "session_start":settings.session_start,"entry_cutoff":settings.entry_cutoff,"session_exit":settings.session_exit,"daily_target":settings.daily_profit_target,
        "target_is_guaranteed":False,"target_basis":settings.daily_profit_target_basis,"plan_policy":plan_policy.describe(),
        "remaining_loss_allocation":account.get("remaining_loss_allocation"),"loss_ledger":account.get("loss_ledger")}


@app.get("/api/market/observations/{identifier}")
def recorded_observation(identifier:str):
    observation=quote_recorder.read(identifier)
    if observation is None: raise HTTPException(404,detail="Observation is not durably recorded; it may be queued, missing or dropped")
    return observation


@app.get("/api/learning/forward")
def forward_learning():
    return {**forward_comparison.status(),"sessions":store.list_records("forward_sessions",100),
            "scope":"Paired daily reference account with the same starting state; not an additive trading account"}


@app.get("/api/implementation")
def implementation_status():
    latest=next((r for r in store.list_records("reports",100) if r.get("strategy_version")=="orb-retest-v1"),None)
    return {"specification":"NIFTY_SENSEX_Implementation_Plan.md","phase":"Baseline replay / execution integration",
        "entries_ready":False,"paper_entries_available":True,"paper_entries_default_paused":not settings.paper_autostart,
        "paper_evidence_collection":settings.paper_collect_evidence,
        "baseline_status":"IMPLEMENTED_ORB_RETEST_V1","plan_backtest_status":latest.get("status") if latest else "NOT_RUN",
        "execution_validation":"BLOCKED_DATA","live_available":False,
        "plan_agents":plan_agent_capabilities(),
        "implemented":["Persisted non-replenishing paper loss allocation", "Atomic one-position/one-lot paper admission",
                       "Cash reserve, entry/loss limits and cooldown", "Gross profit lock and fee-aware liquidation triggers",
                       "Weekly/drawdown review locks", "Learning candidates require review; no automatic deployment",
                       "Causal ORB retest baseline and fixed-contract minute replay with structural protection"],
        "remaining":["Forward-paper evidence and complete shared execution validation",
                     "Dated calendar/event validation, historical contracts/fees and fixed-contract quote recording",
                     "Greek/IV scenario eligibility and field-specific observation ages",
                     "All-opportunity labels, walk-forward adaptive replay and reviewed champion registry",
                     "Execution fault/load tests and required independent/forward-paper evidence"],
        "historical_candles":"Rolling minute data supports preliminary research, not two-second executable quote replay",
        "legacy_runs":"Saved paper-v4 / rolling-research results are not backtests of this implementation plan"}


@app.post("/api/paper/control")
def paper_control(request:PaperControl):
    paper.control(enabled=request.enabled)
    return paper.snapshot()


@app.post("/api/halt")
def halt():
    paper.control(halted=True,reason="Manual paper halt; exits remain active")
    return risk()


@app.post("/api/resume")
def resume():
    account=paper.snapshot()
    if account.get("loss_ledger",{}).get("lock_reason"):
        raise HTTPException(409,detail="Plan risk/profit lock remains active; session reset or a separate reviewed recovery is required")
    if account["session_pnl"]<=-min(settings.daily_loss_limit_rupees,settings.hard_daily_halt_rupees):
        raise HTTPException(409,detail="Daily loss limit cannot be overridden within the same session")
    if not account["valuation_complete"]: raise HTTPException(409,detail="Fresh held-contract quotes required before resuming")
    paper.control(halted=False)
    if hasattr(engine,"status"): engine.status["error"]=None
    return risk()


@app.get("/api/positions")
def positions(): return json_safe(paper.positions())


@app.get("/api/paper/trades")
def paper_trades(): return {"trades":store.list_records("trades",1000),"episodes":store.list_records("episodes",1000)}


@app.get("/api/dashboard")
def dashboard():
    events=event_bus.recent(80); learned=store.learning_snapshot(); account=paper.snapshot()
    # Reports are fetched by ID, not overwritten by every two-second market refresh.
    result={**mode(),"generated_at":now_ist().isoformat(),"market":market_data.snapshot(),"account":account,
        "engine":dict(engine.status),"risk":risk(),"events":events,"implementation":implementation_status(),"ml_learning":learning_model(),
        "strategies":engine.describe_strategies() if hasattr(engine,"describe_strategies") else None,
        "pipelines":{symbol:pipeline_from_events(events,symbol) for symbol in ("NIFTY","SENSEX")},
        "agent_metrics":agent_metrics_from_events(events,learning=learned),"active_policies":store.active_learning_policies(),
        "learning_candidates":store.list_records("learning_candidates",100),
        "jobs":store.list_records("jobs",10),"latest_report":store.get_record("backtest","latest",{}),
        "autonomous_agent":autonomous_agent.get_status() if autonomous_agent.running else {"running": False},
        "defaults":{"capital":settings.paper_capital,"risk_per_trade":settings.max_trade_risk_rupees,
            "daily_loss_limit":settings.daily_loss_limit_rupees,"correlated_risk_limit":settings.max_correlated_risk_rupees}}
    result["learning_monitor"] = learning_monitor.status()
    result["account"].pop("consumed_signals",None)
    return json_safe(redacted(result))


@app.get("/api/learning/monitor/history")
def learning_monitor_history():
    return {"changes": store.list_records("learning_monitor_history", 100)}


@app.get("/api/learning/monitor")
def learning_monitor_status():
    return json_safe(learning_monitor.status())


@app.get("/api/agents")
def agents(): return {"metrics":agent_metrics_from_events(event_bus.recent(250),learning=store.learning_snapshot())}


@app.get("/api/strategies")
def strategies():
    return json_safe(redacted(engine.describe_strategies() if hasattr(engine,"describe_strategies") else
        {"version":"orb-retest-v1","reason":"Single ORB baseline selected"}))


@app.get("/api/learning")
def learning():
    candidates=store.list_records("learning_candidates",100)
    return {**store.learning_snapshot(),"runs":store.list_records("learning_runs",30),
            "candidates":candidates,
            "active_policies":store.active_learning_policies(),"policy_audit":store.list_records("policy_audit",30)}


@app.post("/api/learning/candidates/{candidate_key}/review")
def review_learning_candidate(candidate_key:str,request:LearningReview):
    candidate=store.get_record("learning_candidates",candidate_key)
    if not candidate: raise HTTPException(404,detail="Unknown learning candidate")
    if candidate.get("validation_status") not in {"AWAITING_REVIEW"}:
        raise HTTPException(409,detail="Learning candidate has already been reviewed")
    stamp=now_ist().isoformat(); next_session=(now_ist().date()+timedelta(days=1)).isoformat()
    reviewed={**candidate,"reviewed_at":stamp,"reviewed_by":request.reviewed_by,"review_reason":request.reason}
    if request.action=="reject":
        reviewed["validation_status"]="REJECTED_BY_REVIEW"
        store.put_record("learning_candidates",candidate_key,reviewed)
        store.put_record("policy_audit",f"review:{candidate_key}",{"candidate_key":candidate_key,"status":"REJECTED_BY_REVIEW","timestamp":stamp,"reviewed_by":request.reviewed_by,"reason":request.reason})
        return reviewed
    reviewed.update(validation_status="PROMOTED",effective_from=next_session)
    # The policy JSON is intentionally copied only after human review. The plan
    # has no learned risk, sizing, stop or target parameters to promote.
    store.record_learning([],[{"agent":candidate["agent"],"version":int(candidate["version"]),"policy":reviewed,"updated_at":stamp}])
    store.put_record("learning_candidates",candidate_key,reviewed)
    store.put_record("policy_audit",f"review:{candidate_key}",{"candidate_key":candidate_key,"status":"PROMOTED","timestamp":stamp,"effective_from":next_session,"reviewed_by":request.reviewed_by,"reason":request.reason})
    return reviewed


@app.get("/api/decisions")
def decisions(limit:int=80): return {"events":store.list_records("events",max(1,min(limit,250)))}


@app.get("/api/backtest/contracts")
def contracts():
    try:
        return {"underlyings":gateway.underlyings(),"year_ranges":[1,2,3,4,5],"data_resolution":1,
                "selection":"automatic_non_atm","expiry_selection":"automatic"}
    except Exception as exc: raise HTTPException(502,detail=redacted(str(exc))) from exc


@app.get("/api/backtest/datasets")
def datasets():
    return {"datasets":[dataset_metadata(p) for p in sorted((ROOT/"data").glob("*.csv"))]}


@app.post("/api/backtest/run",status_code=202)
def run_backtest(request:BacktestRequest):
    end=request.to_date or (now_ist().date()-timedelta(days=1))
    if end>=now_ist().date(): raise HTTPException(422,detail="Use completed sessions ending before today")
    start=resolve_backtest_start(end,request.from_date,request.days,request.years)
    if start>end or start<(pd.Timestamp(end)-pd.DateOffset(years=5)).date():
        raise HTTPException(422,detail="Select an ordered date range of at most five years")
    requested_start=start
    range_note=None
    if request.source=="dhan" and request.years==5 and request.from_date is None and request.days is None:
        archive_start=(pd.Timestamp(now_ist().date())-pd.DateOffset(years=5)).date()
        if start<archive_start:
            start=archive_start
            range_note=f"Requested start {requested_start}; rolling history begins {start}. The earlier date is unavailable, not a zero-return session."
    config={"source":request.source,"symbols":["NIFTY","SENSEX"] if request.underlying=="PARALLEL" else [request.underlying],
        "underlying":request.underlying,"from":str(start),"to":str(end),"years":request.years,"days":request.days,
        "capital":request.capital,"risk_per_trade":request.risk_per_trade,"dataset":request.dataset,
        "requested_from":str(requested_start),"range_note":range_note,"daily_target":settings.daily_profit_target,
        "strategy_mode":request.strategy_mode,
        "estimate_missing_exits":request.estimate_missing_exits,"estimate_haircut":request.estimate_haircut,
        "daily_loss_limit":request.daily_loss_limit,"correlated_risk_limit":request.correlated_risk_limit,
        "interval":1,"strategy_version":"orb-retest-v1","selection":"automatic_non_atm",
        "entry_cutoff":settings.entry_cutoff,"session_exit":settings.session_exit,
        "history_cache_only":request.history_cache_only,"strategy_scope":"implementation_plan_baseline"}
    if request.source=="csv" and not request.dataset: raise HTTPException(422,detail="Select a sourced contract dataset")
    try: return jobs.start(config)
    except ValueError as exc: raise HTTPException(409,detail=str(exc)) from exc


@app.get("/api/backtest/jobs")
def list_jobs(): return {"jobs":store.list_records("jobs",50)}


@app.get("/api/backtest/cache")
def backtest_cache(): return store.cache_summary()


@app.get("/api/backtest/history")
def backtest_history():
    return {"jobs":[history_row(job,store.get_record("reports",job["report_id"]) if job.get("report_id") else None)
                    for job in store.list_records("jobs",50)],"limit":50}


@app.post("/api/backtest/cache/download",status_code=202)
def download_backtest_history(extend_atm6:bool=False):
    today=now_ist().date()
    config={"source":"dhan","symbols":["NIFTY","SENSEX"],"download_only":True,
            "requested_from":"2021-01-01",
            "from":str((pd.Timestamp(today)-pd.DateOffset(years=5)).date()),
            "to":str(today-timedelta(days=1)),"interval":1,"expiry_codes":[1,2,3],
            "strike_offsets":["ATM",*[(f"ATM{n:+d}") for n in range(-4,5) if n]],
            "scope":"Index candles and weekly/monthly CALL/PUT rolling options: expiry codes 1/2/3, ATM through ATM±4 for every bucket; OHLC, volume, OI, IV, strike and spot where returned",
            "source_boundary":"Dhan rolling expired-options endpoint supports up to five years; requested archive starts at the derived five-year boundary and reports any older 2021 dates as unavailable"}
    if extend_atm6:
        from .backtest.jobs import ARCHIVE_EXTENSION_OFFSETS,ARCHIVE_FIELDS
        config.update(expiry_codes=[1],strike_offsets=list(ARCHIVE_EXTENSION_OFFSETS),
            fields=[field for field in ARCHIVE_FIELDS if field!="iv"],
            scope="ATM±6 archive extension: near expiry (code 1), WEEK/MONTH CALL/PUT, offsets -6/-5/+5/+6. Existing ATM±4 cache retained. IV is optional and not required for candle reuse.")
    try: return jobs.start(config)
    except ValueError as exc: raise HTTPException(409,detail=str(exc)) from exc


@app.post("/api/backtest/cache/extend-atm6",status_code=202)
def extend_backtest_history():
    return download_backtest_history(extend_atm6=True)


@app.get("/api/backtest/jobs/{identifier}")
def get_job(identifier:str):
    job=store.get_record("jobs",identifier)
    if not job: raise HTTPException(404,detail="Unknown backtest job")
    return job


@app.get("/api/backtest/archives/{identifier}")
def get_archive_manifest(identifier:str):
    manifest=store.get_record("history_archives",identifier)
    if not manifest: raise HTTPException(404,detail="Unknown historical archive")
    return manifest


@app.post("/api/backtest/jobs/{identifier}/cancel")
def cancel_job(identifier:str):
    try: return jobs.cancel(identifier)
    except KeyError: raise HTTPException(404,detail="Unknown backtest job")


@app.get("/api/backtest/report")
def latest_report(): return last_report()


@app.get("/api/backtest/reports/{identifier}")
def get_report(identifier:str):
    report=store.get_record("reports",identifier)
    if not report: raise HTTPException(404,detail="Unknown report")
    return report_view(report)


@app.websocket("/api/ws")
async def websocket(ws:WebSocket):
    if ws.headers.get("origin") and ws.headers["origin"] not in ORIGINS:
        await ws.close(code=1008); return
    await ws.accept()
    try:
        async for item in event_bus.subscribe(): await ws.send_json(json_safe(redacted(item)))
    except (WebSocketDisconnect,RuntimeError,asyncio.CancelledError): pass


# ──────────────────────────────────────────────────────────────
# Autonomous Agent Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/api/agent/status")
def agent_status():
    return json_safe(autonomous_agent.get_status())


@app.post("/api/agent/control")
def agent_control(request: PaperControl):
    if request.enabled:
        autonomous_agent.start()
    else:
        autonomous_agent.stop()
    return autonomous_agent.get_status()


@app.get("/api/agent/state")
def agent_state():
    return json_safe({
        "session_date": autonomous_agent.state.session_date,
        "total_trades": autonomous_agent.state.total_trades,
        "winning_trades": autonomous_agent.state.winning_trades,
        "losing_trades": autonomous_agent.state.losing_trades,
        "net_pnl": autonomous_agent.state.net_pnl,
        "gross_pnl": autonomous_agent.state.gross_pnl,
        "max_drawdown": autonomous_agent.state.max_drawdown,
        "daily_target_hit": autonomous_agent.state.daily_target_hit,
        "daily_loss_limit_hit": autonomous_agent.state.daily_loss_limit_hit,
        "last_model_retrain": autonomous_agent.state.last_model_retrain,
        "strategy_stats": autonomous_agent.strategy_stats,
        "dynamic_params": autonomous_agent.dynamic_params,
    })


@app.post("/api/agent/retrain")
def agent_retrain():
    autonomous_agent._retrain_models()
    return {"status": "triggered", "last_retrain": autonomous_agent.state.last_model_retrain}
