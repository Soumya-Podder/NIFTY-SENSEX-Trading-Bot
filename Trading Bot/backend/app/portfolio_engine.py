"""Three paper hypotheses, one selector, one atomic portfolio authority."""
from datetime import timedelta
import hashlib
import json
import copy
import math
import threading
import time
from contextlib import nullcontext
import pandas as pd
from .paper_engine import PaperEngine
from .strategy_portfolio import STRATEGIES, PORTFOLIO_VERSION, evaluate_strategies, rank_opportunities, regime_strategy_policy, closed_session
from .pipeline import plan_protection, execution_context, CandidateRejected, CandidateDataUnavailable
from .expectancy import ExpectancyEngine, CostModel
from .session import now_ist, quote_is_fresh
from .telemetry.decision_trace import event
from .ai import LearningService, extract_features
from .adaptive_exit import VERSION as ADAPTIVE_EXIT_VERSION
from .specialist_agents import assess_specialists, waiting_agents, VERSION as REVIEW_VERSION
from .option_screen import VERSION as SCREEN_VERSION, assess as assess_option, describe as describe_screen, net_economics
from .market_context import CHAIN_FIELDS, build_context, chain_window, decision_context, unavailable
from .market_structure import analyze_structure, structure_evidence
from .outcome_evidence import outcome_scope, summarize_outcomes
from .risk import size_plan_order, SIZING_VERSION


class MultiStrategyPaperEngine(PaperEngine):
    version=PORTFOLIO_VERSION
    strategy_specs=STRATEGIES
    full_chain_context=False

    def _now(self):
        return self.execution_clock() if self.execution_clock else now_ist()

    def evaluate_market(self,frame,now,symbol,structure):
        return evaluate_strategies(frame,now,symbol,structure)

    def strategy_order(self,regime):
        return regime_strategy_policy(regime)

    def plan_candidate(self,signal,contract,candle):
        return plan_protection(signal,contract,candle,contract["ask"],horizon_minutes=signal["horizon_minutes"])

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.protection_requests={}; self.protection_results={}
        self.fee_requests={}; self.fee_retry_after={}
        self.pending_signals={}
        self.candle_repair_after={}
        self.audit_keys={}; self.entry_wakeup=threading.Event()
        self.learning=LearningService(self.store)
        self.ml_frozen={}
        self.status["market_context"]={}
        self.status["market_structure"]={}
        self.status["outcome_estimates"]={}
        self.outcome_records=self.store.list_records("market_outcomes",10000)
        for snapshot in reversed(self.store.list_records("market_structure",100)):
            self.status["market_structure"][snapshot["symbol"]]={**snapshot,"status":"STALE","reason":"Retained observation; awaiting current session candles"}
        for symbol in ("NIFTY","SENSEX"):
            history=[r for r in self.outcome_records if r.get("scope",{}).get("symbol")==symbol]
            if history:
                latest=max(history,key=lambda r:r["entry_at"])
                self.status["outcome_estimates"][symbol]={**summarize_outcomes(history,latest["scope"],self._now()),
                    "as_of":latest["entry_at"],"source":"LAST_HISTORICAL_SCOPE"}
        self.status["portfolio"]={"version":self.version,"strategies":list(self.strategy_specs),
            "evidence":"UNVALIDATED_PAPER","evaluations":[],"offers":[],"selected":None,"reviews":{},
            "reason":"Waiting for session","selection_rule":"Supported net evidence first; then the day's regime-compatible strategy order, net target reward / all-in risk and spread. No profit probability is claimed.",
            "day_regime":None,"regime_strategy_order":list(self.strategy_order("TRANSITION")),
            "option_screen":describe_screen(self.settings.max_spread_pct,self.settings.min_net_reward_risk)}

    def _freeze_policies(self,now):
        day=str(now.date())
        if self.policy_day==day: return
        key=day+":"+self.version+":"+SCREEN_VERSION+":"+REVIEW_VERSION+":"+SIZING_VERSION
        frozen=self.store.get_record("session_models",key)
        if frozen is None:
            specification=json.dumps({"strategies":self.strategy_specs,"option_screen":self.status["portfolio"]["option_screen"],"decision_policy_version":REVIEW_VERSION,"sizing_policy_version":SIZING_VERSION},sort_keys=True)
            frozen={"session":day,"policies":{},"strategy_version":self.version,
                "strategies":list(self.strategy_specs),"hash":hashlib.sha256(specification.encode()).hexdigest(),
                "frozen_at":now.isoformat(),"validation":"UNVALIDATED_PAPER",
                "option_screen":self.status["portfolio"]["option_screen"],"decision_policy_version":REVIEW_VERSION,"sizing_policy_version":SIZING_VERSION}
            self.store.put_record("session_models",key,frozen)
        self.pipeline.policies={}; self.policy_day=day; self.status["frozen_model"]=frozen
        self.ml_frozen=self.learning.freeze(now)
        self.status["ml_session"]=self.ml_frozen
        with self.lock:
            self.protection_requests.clear(); self.protection_results.clear(); self.pending_signals.clear()
            self.fee_requests.clear(); self.fee_retry_after.clear()

    def start(self):
        if any(thread.is_alive() for thread in self.threads): return
        super().start()
        for name,target in (("paper-selector",self._entry_loop),("paper-protection-preparation",self._preparation_loop),
                            ("paper-context-nifty",lambda:self._context_loop("NIFTY")),
                            ("paper-context-sensex",lambda:self._context_loop("SENSEX"))):
            self._start_worker(name,target)

    def _context_loop(self,only_symbol=None):
        # Advisory downloads never run in the execution/exit heartbeat.
        while not self.stop_event.is_set():
            now=self._now()
            if self._session() in {"PREOPEN","ENTRY_WINDOW","MANAGE_ONLY"} and "09:10"<=now.strftime("%H:%M")<self.settings.session_exit:
                for symbol in ((only_symbol,) if only_symbol else ("NIFTY","SENSEX")):
                    if self.stop_event.is_set(): break
                    try:
                        self.collect_market_context(symbol)
                        self.status.setdefault("context_errors",{}).pop(symbol,None)
                    except Exception as exc:
                        self.status.setdefault("context_errors",{})[symbol]=self._safe_error(exc)
            self.stop_event.wait(15)

    def collect_market_context(self,symbol):
        self.outcome_records=self.store.list_records("market_outcomes",10000)
        self.gateway.refresh_credentials()
        generation=self.gateway.credential_generation
        errors={}; rows=[]; contract={}; frame=pd.DataFrame()
        try:
            chain=self.gateway.chain(symbol,exclude_expiry_day=True,include_atm=True)
            self._update_chain_contracts(symbol,chain,generation)
            rows,reason=(chain,None) if self.full_chain_context else chain_window(chain,symbol)
            if reason: errors["positioning"]=reason
        except Exception as exc:
            errors["positioning"]=self._safe_error(exc)
            with self.lock:
                self.status.setdefault("data_symbols",{}).setdefault(symbol,{})["chain_error"]=errors["positioning"]
        try: contract,frame=self.gateway.futures_candles(symbol,self._now())
        except Exception as exc: errors["futures"]=self._safe_error(exc)
        self.gateway.refresh_credentials()
        if generation!=self.gateway.credential_generation: return
        now=self._now()
        # Persist only data fields, never client/configuration objects. These
        # inputs reproduce the as-observed context, including incomplete data.
        rows=[{key:c.get(key) for key in CHAIN_FIELDS} for c in rows]
        inputs={"symbol":symbol,"captured_at":now.isoformat(),"chain":rows,"futures_contract":contract,
                "chain_scope":"FULL_RETURNED_FIXED_CONTRACT_CHAIN" if self.full_chain_context else "ATM_PLUS_MINUS_5",
                "futures_candles":json.loads(frame.to_json(orient="records",date_format="iso")),"errors":errors}
        identifier=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:24]
        context=build_context(symbol,rows,contract,frame,now,self.settings.session_exit,full_chain=self.full_chain_context)
        for key,reason in errors.items(): context[key]=unavailable(reason)
        context.update(snapshot_id=identifier,credential_generation=generation)
        self.store.save_bundle([("market_context_inputs",identifier,inputs),
                                ("market_context",identifier,context)])
        with self.lock: self.status["market_context"][symbol]=context

    def context_at(self,symbol,now,horizon_minutes=10):
        with self.lock: snapshot=self.status["market_context"].get(symbol)
        return decision_context(snapshot,now,getattr(self.gateway,"credential_generation",0),horizon_minutes)

    def evaluate_entries(self,frames,quotes,now):
        # The shared exit heartbeat does not wait for historical/fee requests.
        self.entry_wakeup.set()

    def _data_loop(self,only_symbol=None):
        while not self.stop_event.is_set():
            now=self._now()
            warmup=self._session() in {"PREOPEN","ENTRY_WINDOW","MANAGE_ONLY"} and "09:10"<=now.strftime("%H:%M")<self.settings.session_exit
            if warmup:
                for symbol in ((only_symbol,) if only_symbol else ("NIFTY","SENSEX")):
                    try:
                        self.refresh_symbol_data(symbol,refresh_chain=False)
                    except Exception as exc:
                        previous=self.status.setdefault("data_symbols",{}).get(symbol,{})
                        self.status["data_symbols"][symbol]={**previous,"candle_status":"ERROR","candle_error":self._safe_error(exc),
                            "error":self._safe_error(exc),"updated_at":self._now().isoformat()}
                        self.status["data_error"]=self._safe_error(exc)
            self.stop_event.wait(10)

    def refresh_symbol_data(self,symbol,*,refresh_chain=True):
        self.gateway.refresh_credentials()
        generation=getattr(self.gateway,"credential_generation",0)
        now=self._now(); day=now.date()
        frame=self.gateway.candles(symbol,day-timedelta(days=7),day+timedelta(days=1),cache_seconds=10)
        _,reason=closed_session(frame,self._now())
        repairable={"Completed candle is stale","Missing or duplicate session candles","Waiting for today's completed candles"}
        health=self.status.setdefault("data_symbols",{}).get(symbol,{})
        if health.get("session")!=str(day): health={"session":str(day),"repair_attempts":0,"repair_successes":0}
        health={**health,"repair_error":None,"candle_error":None}
        health.setdefault("repair_attempts",0); health.setdefault("repair_successes",0)
        repair_key=(symbol,str(day),generation)
        if reason in repairable and time.monotonic()>=self.candle_repair_after.get(repair_key,0):
            self.candle_repair_after={k:v for k,v in self.candle_repair_after.items() if k[1]==str(day) and k[2]==generation}
            self.candle_repair_after[repair_key]=time.monotonic()+30
            health["repair_attempts"]+=1
            try:
                observed=self.gateway.candles(symbol,day,day+timedelta(days=1),cache_seconds=0)
                frame=pd.concat([frame,observed],ignore_index=True).drop_duplicates("timestamp",keep="last").sort_values("timestamp")
                _,reason=closed_session(frame,self._now())
                if reason is None: health["repair_successes"]+=1
            except Exception as exc:
                health["repair_error"]=self._safe_error(exc)
        if generation!=getattr(self.gateway,"credential_generation",0): return
        frame=frame[frame.timestamp+pd.Timedelta(minutes=1)<=pd.Timestamp(self._now())]
        structure=analyze_structure(frame,self._now(),symbol)
        health.update(updated_at=self._now().isoformat(),last_bar=str(frame.timestamp.max()) if not frame.empty else None,
            rows=len(frame),candle_status="READY" if reason is None else "WAITING",candle_reason=reason,
            credential_generation=generation)
        # Publish completed index data before the slower, independent chain request.
        with self.lock:
            self.frames[symbol]=frame
            self.status["market_structure"][symbol]=structure
            self.status["data_symbols"][symbol]=health
        self.entry_wakeup.set()
        if structure.get("as_of"):
            self.store.put_record("market_structure",symbol+":"+structure["as_of"],structure)
        if not refresh_chain:
            health["error"]=health.get("repair_error") or reason
            self.status["data_error"]=next((h.get("error") for h in self.status["data_symbols"].values() if h.get("error")),None)
            self.store.put_record("data_health",str(day)+":"+symbol,health)
            return
        try:
            chain=self.gateway.chain(symbol,exclude_expiry_day=True,include_atm=True)
            if generation!=getattr(self.gateway,"credential_generation",0): return
            self._update_chain_contracts(symbol,chain,generation)
        except Exception as exc:
            health["chain_error"]=self._safe_error(exc)
        health["error"]=health.get("chain_error") or health.get("repair_error") or reason
        self.status["data_error"]=next((h.get("error") for h in self.status["data_symbols"].values() if h.get("error")),None)
        self.store.put_record("data_health",str(day)+":"+symbol,health)

    def _update_chain_contracts(self,symbol,chain,generation):
        if generation!=getattr(self.gateway,"credential_generation",0): return
        cash=self.broker.snapshot()["cash"]
        affordable=[c for c in chain if c.get("ltp") and 0<float(c["ltp"])*c["lot_size"]<cash]
        chosen=[]
        for side in ("CALL","PUT"):
            candidates=[c for c in affordable if c["option_type"]==side]
            candidates.sort(key=lambda c:(abs(abs(c.get("delta") or 0)-.5),-float(c.get("oi") or 0)))
            chosen.extend(candidates[:12])
        with self.lock:
            self.contracts=[c for c in self.contracts if c["symbol"]!=symbol]+chosen
            self.status.setdefault("data_symbols",{}).setdefault(symbol,{}).update(
                chain_contracts=len(chain),subscribed_candidates=len(chosen),chain_error=None,chain_updated_at=self._now().isoformat())
        self.entry_wakeup.set()

    def _safe_error(self,exc):
        text=str(exc)
        for secret in (self.settings.dhan_client_id,self.settings.dhan_access_token):
            if secret: text=text.replace(secret,"[redacted]")
        return text[:250]

    def _request_protection(self,signal,contract):
        key=(signal["id"],contract["contract_id"])
        with self.lock:
            result=self.protection_results.get(key)
            generation=getattr(self.gateway,"credential_generation",0)
            if result and result.get("generation")==generation:
                if result.get("candle"): return result["candle"],None
                if time.monotonic()<result["retry_after"]: return None,result["reason"]
            self.protection_requests[key]={"signal":dict(signal),"contract":dict(contract),"generation":generation}
        return None,"Waiting for the selected contract's completed protection candle"

    def prepare_protection(self,key,request):
        signal=request["signal"]; contract=request["contract"]
        stamp=pd.Timestamp(signal["retest_timestamp"])
        # A narrow timestamp request was observed to omit the requested boundary
        # candle. Fetch the bounded contract session, then require an exact match.
        # Later candles never participate in the stop calculation.
        start=str(stamp.date())
        end=str((stamp+pd.Timedelta(days=1)).date())
        try:
            if stamp+pd.Timedelta(minutes=1)>pd.Timestamp(self._now()): raise ValueError("Protection candle is not completed")
            with self.lock: retry=key in self.protection_results and not self.protection_results[key].get("candle")
            bars=(self.gateway.contract_candles(contract,start,end,cache_seconds=0) if retry else
                  self.gateway.contract_candles(contract,start,end))
            matches=bars[bars.timestamp==stamp]
            if len(matches)!=1: raise ValueError("Provider has not returned the exact selected-contract protection minute")
            candle=matches.iloc[0].to_dict()
            from .indicators import atr
            history=bars[bars.timestamp<=stamp].sort_values("timestamp")
            candle["option_atr"]=float(atr(history).iloc[-1]) if len(history)>=14 else None
            if not all(math.isfinite(float(candle[k])) and float(candle[k])>0 for k in ("open","high","low","close")):
                raise ValueError("Invalid protection OHLC")
            if candle["low"]>min(candle["open"],candle["close"]) or candle["high"]<max(candle["open"],candle["close"]):
                raise ValueError("Inconsistent protection OHLC")
            result={"candle":{**contract,**candle,"source":"dhan_contract_minute","requested_from":start,"requested_to":end},
                "generation":request["generation"]}
        except Exception as exc:
            result={"candle":None,"reason":self._safe_error(exc),"generation":request["generation"],"retry_after":time.monotonic()+10}
        with self.lock:
            if request["generation"]==getattr(self.gateway,"credential_generation",0): self.protection_results[key]=result

    def _queue_fee(self,signal,contract,buy,sell,qty,window,transaction):
        key=(signal["id"],contract["contract_id"],buy,sell,qty,window,transaction)
        with self.lock:
            if time.monotonic()>=self.fee_retry_after.get(key,0):
                self.fee_requests[key]={"signal":dict(signal),"contract":dict(contract),"buy":buy,"sell":sell,
                    "qty":qty,"window":window,"transaction":transaction,"generation":getattr(self.gateway,"credential_generation",0)}

    def prepare_fee(self,key,request):
        if (not self._signal_fresh(request["signal"],self._now()) or
            request["generation"]!=getattr(self.gateway,"credential_generation",0)): return
        try:
            self.broker.cost._broker_quote(request["contract"],request["buy"],request["sell"],
                request["qty"],request["window"],request["transaction"])
            self.status["fee_preparation_error"]=None
        except Exception as exc:
            self.status["fee_preparation_error"]=self._safe_error(exc)
            with self.lock: self.fee_retry_after[key]=time.monotonic()+10
        self.entry_wakeup.set()

    def _preparation_loop(self):
        while not self.stop_event.is_set():
            with self.lock:
                request=next(iter(self.protection_requests.items()),None)
                if request: self.protection_requests.pop(request[0],None)
                fee=next(iter(self.fee_requests.items()),None)
                if fee: self.fee_requests.pop(fee[0],None)
            if request:
                key,value=request
                if self._signal_fresh(value["signal"],self._now()): self.prepare_protection(key,value)
            if fee: self.prepare_fee(*fee)
            if not request and not fee: self.stop_event.wait(.25)

    @staticmethod
    def _signal_fresh(signal,now):
        age=(pd.Timestamp(now)-pd.Timestamp(signal["timestamp"])).total_seconds()
        # A closed one-minute setup remains actionable for at most three
        # completed bars. Every attempted fill still rechecks invalidation,
        # target, current depth, costs and risk against fresh observations.
        return 60<=age<=185

    def _entry_loop(self):
        while not self.stop_event.is_set():
            try:
                self.portfolio_cycle()
                self.status["selector_error"]=None
            except Exception as exc:
                self.status["selector_error"]=self._safe_error(exc)
                self.status["portfolio"]["reason"]="Selector error; entries withheld, exit management continues"
            self.entry_wakeup.wait(2); self.entry_wakeup.clear()

    def _quotes(self):
        with self.lock: quotes=dict(self.quotes)
        if self.market: quotes.update(self.market.executable_quotes())
        return quotes

    def _execution_snapshot(self,symbol):
        if self.market and hasattr(self.market,"execution_snapshot"):
            snap=self.market.execution_snapshot(symbol)
            # A reconnect clears the executable feed cache. A prior worker copy
            # cannot stand in for a book missing from the current connection.
            return snap.get("underlying",{}),snap.get("options",{})
        underlying=(self.market.snapshot().get("symbols",{}).get(symbol,{}) if self.market else {})
        return underlying,{k:v for k,v in self._quotes().items() if v.get("symbol")==symbol}

    def _gate(self,signal,state,reason,**details):
        latest=self.status["portfolio"]["reviews"].get(signal["symbol"],{})
        review=copy.deepcopy(latest if latest.get("signal_id")==signal["id"] else signal.get("decision_review") or {})
        review.setdefault("checks",{})["selection_or_admission"]={"status":"BLOCKED","reason":reason}
        if details.get("risk_veto") and review.get("agents"):
            review["agents"]["Risk Sentinel"].update(status="VETO",evidence=reason)
        self._record_review(signal,{},review,self._now(),"WAIT",reason,"BLOCKED")
        key=signal["id"]
        self.store.put_record("strategy_opportunities",key,{**signal,"status":state,"reason":reason,
            "evaluated_at":self._now().isoformat(),"decision_review":review,**details})
        fingerprint=(state,reason)
        if self.audit_keys.get(key)!=fingerprint:
            self.publish(event("Option Selector" if state=="WAITING_DATA" else "Risk",signal["symbol"],
                "WAITING" if state=="WAITING_DATA" else "REJECTED",reason,strategy_id=signal["strategy_id"],signal_id=key))
            self.audit_keys[key]=fingerprint

    def _record_review(self,signal,contract,review,now,decision,reason,phase="REVIEWED"):
        review["market_structure"]=signal.get("market_structure",{})
        review["outcome_estimate"]=signal.get("outcome_estimate",{})
        review.update(version=REVIEW_VERSION,symbol=signal["symbol"],signal_id=signal.get("id"),
            strategy_id=signal.get("strategy_id"),contract_id=contract.get("contract_id",review.get("contract_id")),
            decision=decision,reason=reason,phase=phase,evaluated_at=now.isoformat(),
            evidence_mode="UNVALIDATED_PAPER",authority="PAPER_CANDIDATE_ONLY_ATOMIC_RISK_GATE_REQUIRED")
        agents=review.setdefault("agents",waiting_agents(reason))
        agents["Orchestrator"].update(status=decision,evidence=reason,evaluated_at=now.isoformat())
        review["unavailable_context"]=[name for name,row in agents.items() if row["status"]=="DATA_UNAVAILABLE"]
        review["coverage"]={"evaluated":sum(row["status"] not in {"NOT_EVALUATED","PENDING","POST_TRADE"} for row in agents.values()),
            "available":sum(row["status"] in {"PASS","OBSERVATION","CALL","PUT"} for row in agents.values()),"total":len(agents)}
        self.status["portfolio"]["reviews"][signal["symbol"]]=copy.deepcopy(review)
        # Preserve changed decisions/bar reviews; unchanged polling updates one record.
        identity=[str(now.date()),signal["symbol"],signal.get("id"),review.get("contract_id"),review.get("bar_at"),decision,reason,phase]
        key=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
        self.store.put_record("decision_reviews",key,review)
        if self.audit_keys.get("review:"+signal["symbol"])!=key:
            for name,row in agents.items():
                if row["status"] not in {"NOT_EVALUATED","PENDING","POST_TRADE"}:
                    self.publish(event(name,signal["symbol"],row["status"],row.get("task",name),
                        signal_id=signal.get("id"),evaluation=row))
            self.audit_keys["review:"+signal["symbol"]]=key

    def _current_signal(self,signal,now):
        with self.lock: frame=self.frames.get(signal["symbol"])
        _,rows=self.evaluate_market(frame,now,signal["symbol"],self.status["market_structure"].get(signal["symbol"],{}))
        row=next((r for r in rows if r["id"]==signal["strategy_id"]),{})
        if not row.get("feature_row") or not row.get("regime"):
            return None,row.get("reason","Current completed-bar evidence unavailable")
        regime=row["regime"]
        return {**signal,"feature_row":row["feature_row"],"regime":regime,
            "market_structure":structure_evidence(self.status["market_structure"].get(signal["symbol"],{}),signal["option_type"],now),
            "setup_regime":signal.get("setup_regime",signal.get("regime")),
            "agent_contexts":{**signal.get("agent_contexts",{}),"Regime":regime},
            "regime_priority":self.strategy_order(regime).get(signal["strategy_id"],99)},None

    def _prepare_offer(self,signal,contract,account,outcomes,now):
        review={"agents":waiting_agents("Earlier mandatory gate has not cleared"),"checks":{}}
        try:
            cost=self.broker.cost
            # The existing preparation worker performs fee HTTP. The selector
            # ranks ready offers without waiting for other contracts' network calls.
            defer=bool(self.threads) and isinstance(cost,CostModel) and cost.paper and not cost.cache_only.get()
            context=cost.cached_only(on_missing=lambda *args:self._queue_fee(signal,*args)) if defer else nullcontext()
            with context:
                offer,reason=self._assess_offer(signal,contract,account,outcomes,now,review)
        except CandidateRejected as exc:
            reason=self._safe_error(exc)
            review["checks"]["protection_plan"]={"status":"BLOCKED","reason":reason}
            self._record_review(signal,contract,review,now,"WAIT",reason,
                "WAITING_DATA" if isinstance(exc,CandidateDataUnavailable) else "BLOCKED")
            return None,reason
        except Exception as exc:
            if isinstance(exc,ValueError) and str(exc)=="Waiting for broker fee preparation":
                review["checks"]["broker_fees"]={"status":"BLOCKED","reason":str(exc)}
                self._record_review(signal,contract,review,now,"WAIT",str(exc),"WAITING_DATA")
                return None,str(exc)
            self._record_review(signal,contract,review,now,"WAIT",self._safe_error(exc),"ERROR")
            raise
        self._record_review(signal,contract,review,now,signal["option_type"] if offer else "WAIT",
            reason or "Eligible paper candidate; ranking and atomic risk admission still required", "CANDIDATE" if offer else "BLOCKED")
        if offer:
            offer["signal"]["decision_review"]=copy.deepcopy(review)
            offer["signal"]["specialist_agents"]=copy.deepcopy(review["agents"])
            offer["signal"]["agent_scores"]={name:row["status"] for name,row in review["agents"].items()}
        return offer,reason

    def _assess_offer(self,signal,contract,account,outcomes,now,review):
        def check(name,passed,reason,**evidence):
            review["checks"][name]={"status":"PASS" if passed else "BLOCKED","reason":reason,**evidence}
            return passed
        if self.threads:
            from .runtime_health import execution_health
            health=execution_health(self,self.broker,now)
            age=health["heartbeat_age_seconds"]
            if not check("workers",age is not None and 0<=age<=15 and not health["dead_workers"] and health["broker"]["healthy"],
                         "Exit heartbeat, worker liveness and broker persistence",evidence=health):
                return None,"Required paper workers or exit heartbeat are unavailable"
        admission=self.broker.policy.entry_veto(account["loss_ledger"],now)
        account_ok=account["enabled"] and not account["halted"] and account["valuation_complete"] and not account["positions"]
        if not check("session_and_account",self._session()=="ENTRY_WINDOW" and account_ok and not admission,
                     admission or "Entry session, valuation, shared position cap and account controls"):
            review["agents"]["Risk Sentinel"].update(status="VETO",evidence=admission or "Account/session unavailable")
            return None,admission or "Account/session unavailable for paper entry"
        current,reason=self._current_signal(signal,now)
        if not check("completed_bars",current is not None and self._signal_fresh(signal,now),reason or "Causal current candles and unexpired setup"):
            return None,reason or "Setup expired before candidate review"
        signal=current
        review["bar_at"]=signal["feature_row"].get("timestamp")
        generation=getattr(self.gateway,"credential_generation",0)
        if self.market:
            _,books=self._execution_snapshot(signal["symbol"])
            latest=books.get(contract["contract_id"])
            if latest:
                if any(latest.get(k)!=contract.get(k) for k in ("contract_id","expiry","strike","lot_size","option_type")):
                    return None,"Contract identity changed during candidate review"
                contract={**contract,**latest}
            now=self._now()
        screen=assess_option(contract,signal,now,max_spread=self.settings.max_spread_pct,
                             max_quote_age=self.settings.max_quote_age_seconds)
        if not check("option_screen",screen["status"]=="PASS","; ".join(screen["reasons"]),evidence=screen):
            return None,"Option screen: "+"; ".join(screen["reasons"])
        contract={**contract,"option_screen":screen,"option_screen_version":SCREEN_VERSION,"spread_pct":screen["spread_pct"]}
        candle,reason=self._request_protection(signal,contract)
        if not check("protection_candle",candle is not None,reason or "Exact selected contract completed candle"):
            return None,reason
        s=self.plan_candidate(signal,contract,candle)
        s["option_screen_version"]=SCREEN_VERSION
        s["decision_policy_version"]=REVIEW_VERSION
        s["market_context"]=self.context_at(signal["symbol"],now,signal["horizon_minutes"])
        s.update(exit_policy=ADAPTIVE_EXIT_VERSION,option_atr=candle.get("option_atr"))
        s["outcome_estimate"]=summarize_outcomes(self.outcome_records,outcome_scope({**s,"entry":contract["ask"]}),now)
        self.status["outcome_estimates"][signal["symbol"]]={**s["outcome_estimate"],"as_of":now.isoformat(),"signal_id":signal["id"]}
        s["entry_features"]=extract_features(signal.get("feature_row",{}),s,contract,now)
        quality=self.learning.score(s,self.ml_frozen)
        s["ml_quality"]=quality
        if not check("learned_filter",quality["allowed"],quality["status"],evidence=quality):
            probability=quality.get("probability")
            return None,(f"ML Quality Gate: {probability:.1%} below {quality['threshold']:.1%}" if probability is not None else "ML Quality Gate: "+quality["status"])
        sizing=size_plan_order(self.broker.policy,account,contract,s["stop_price"],self.broker.cost)
        check("quantity",sizing is not None,"Whole lots within cash, depth and remaining risk",sizing=sizing)
        # Review one-lot evidence even when admission cannot fund a lot; it is
        # explanatory only and cannot reach execution without valid sizing.
        qty=sizing["quantity"] if sizing else contract["lot_size"]; price=contract["ask"]
        s["sizing_policy_version"]=SIZING_VERSION
        stop_cost=sizing["stop_cost"] if sizing else self.broker.cost.quote(contract,price,s["stop_price"],qty)["total"]
        target_cost=self.broker.cost.quote(contract,price,s["target_price"],qty)["total"]
        buy_cost=sizing["buy_cost"] if sizing else self.broker.cost.quote(contract,price,0,qty)["total"]
        economics=net_economics(price,contract["bid"],s["stop_price"],s["target_price"],qty,stop_cost,target_cost)
        risk=economics["risk"]; reward=economics["net_reward"]
        s["entry_economics"]=economics
        specialists=assess_specialists(s,contract,now,risk=risk,reward=reward,
                                       max_quote_age=self.settings.max_quote_age_seconds,
                                       max_spread=self.settings.max_spread_pct,min_net_reward_risk=self.settings.min_net_reward_risk)
        review["agents"]=specialists["agents"]
        check("specialist_evidence",not specialists["vetoes"],"; ".join(specialists["vetoes"]) or "Required specialist evidence passed")
        s={**s,"specialist_agents":specialists["agents"],
           "agent_scores":{name:row.get("status") for name,row in specialists["agents"].items()},
           "orchestrator_decision":specialists["decision"],
           "adversarial_warnings":specialists["agents"].get("Adversarial Agent",{}).get("warnings",[])}
        if specialists["vetoes"]:
            details=[]
            for name in specialists["vetoes"]:
                row=specialists["agents"].get(name,{})
                evidence=row.get("warnings") or row.get("evidence") or []
                if not isinstance(evidence,list): evidence=[evidence]
                details.append(name+(" ("+", ".join(map(str,evidence))+")" if evidence else ""))
            return None,"Specialist veto: "+"; ".join(details)
        budget=self.broker.policy.risk_budget(account["loss_ledger"],qty//contract["lot_size"],account["open_risk_rupees"])
        if not sizing:
            review["agents"]["Risk Sentinel"].update(status="VETO",evidence=review["checks"]["quantity"])
            return None,"No whole lot fits current cash, liquidity and risk allocation"
        if not check("risk_budget",0<risk<=budget,"Sized all-in stop risk versus remaining budget",risk=risk,budget=budget):
            review["agents"]["Risk Sentinel"].update(status="VETO",evidence=review["checks"]["risk_budget"])
            return None,"All-in stop risk exceeds remaining budget"
        if not check("cash",price*qty+buy_cost<=min(self.broker.policy.premium_limit,account["cash"]-self.broker.policy.cash_reserve),"Premium, charges and cash reserve"):
            review["agents"]["Risk Sentinel"].update(status="VETO",evidence=review["checks"]["cash"])
            return None,"Premium and charges breach available cash or reserve"
        if reward/risk<self.settings.min_net_reward_risk: return None,"Net target reward/risk below configured minimum"
        matched=[t for t in outcomes if t.get("portfolio_version")==self.version and
            t.get("sizing_policy_version")==SIZING_VERSION and
            t.get("decision_policy_version")==REVIEW_VERSION and
            t.get("option_screen_version")==SCREEN_VERSION and
            t.get("strategy_id")==s["strategy_id"] and t.get("strategy_version")==s["strategy_version"] and
            t.get("setup")==s["setup"] and t.get("regime")==s["regime"] and
            pd.Timestamp(t["exit_ts"])<pd.Timestamp(now)]
        ev=ExpectancyEngine().evaluate_net(matched)
        if ev["reason"]=="Insufficient independent net-outcome evidence" and self.settings.paper_collect_evidence:
            ev={**ev,"status":"OBSERVATION","reason":"Unvalidated paper evidence collection; no estimated profit probability"}
        if not check("net_expectancy",ev["status"]!="REJECTED",ev["reason"],evidence=ev): return None,ev["reason"]
        review["agents"]["Risk Sentinel"].update(status="PASS",evidence="Preflight passed; broker rechecks the current ledger atomically at fill")
        return {"signal":s,"contract":contract,"risk":risk,"net_reward":reward,"net_reward_risk":reward/risk,
            "ev":ev,"generation":generation,"quantity":qty},None

    def portfolio_cycle(self):
        now=self._now(); self._freeze_policies(now)
        state=self.status["portfolio"]; state["checked_at"]=now.isoformat()
        state["selected"]=None;state["offers"]=[]
        if self._session()!="ENTRY_WINDOW":
            state["reason"]=self._session()
            state["evaluations"]=[{**spec,"symbol":symbol,"status":"WAITING","reason":self._session(),"checked_at":now.isoformat(),"evidence":"UNVALIDATED_PAPER"}
                for symbol in ("NIFTY","SENSEX") for spec in self.strategy_specs]
            for symbol in ("NIFTY","SENSEX"):
                self._record_review({"symbol":symbol},{},{},now,"WAIT",state["reason"],"MONITORING")
            return
        account=self.broker.snapshot()
        if getattr(self,"entry_readiness",None):
            ready=self.entry_readiness()
            if not ready["entry_ready"]:
                state["reason"]="; ".join(ready["entry_blockers"])
                state["evaluations"]=[{**spec,"symbol":symbol,"status":"WAITING","reason":state["reason"],"checked_at":now.isoformat(),"evidence":"UNVALIDATED_PAPER"}
                    for symbol in ("NIFTY","SENSEX") for spec in self.strategy_specs]
                for symbol in ("NIFTY","SENSEX"):
                    self._record_review({"symbol":symbol},{},{},now,"WAIT",state["reason"],"BLOCKED")
                return
        if not account["enabled"] or account["halted"] or not account["valuation_complete"]:
            state["reason"]="Paper entries paused, halted or awaiting position valuation"
            for symbol in ("NIFTY","SENSEX"):
                self._record_review({"symbol":symbol},{},{},now,"WAIT",state["reason"],"BLOCKED")
            return
        veto=self.broker.policy.entry_veto(account["loss_ledger"],now)
        admission_block=veto or ("Shared account already has an open position" if account["positions"] else None)
        with self.lock: frames=dict(self.frames)
        signals=[]; evaluations=[]
        for symbol in ("NIFTY","SENSEX"):
            found,rows=self.evaluate_market(frames.get(symbol),now,symbol,self.status["market_structure"].get(symbol,{}))
            with self.lock:
                for signal in found:
                    signal["market_context"]=self.context_at(symbol,now,signal["horizon_minutes"])
                    self.pending_signals[signal["id"]]=signal
                self.pending_signals={key:value for key,value in self.pending_signals.items()
                                      if self._signal_fresh(value,now)}
                pending=[value for value in self.pending_signals.values() if value["symbol"]==symbol]
            signals.extend(pending); evaluations.extend(rows)
            if not pending or admission_block:
                self._record_review({"symbol":symbol},{},{},now,"WAIT",admission_block or rows[0]["reason"],"MONITORING")
            self.scan_wait(symbol,"Evaluating strategy candidates" if pending else rows[0]["reason"],now,
                last_bar=rows[0].get("last_bar"))
        state["evaluations"]=evaluations
        regimes=[row.get("regime") for row in evaluations if row.get("regime")]
        if regimes:
            # Deterministic majority classification is only a preference for
            # ranking. Every strategy remains evaluated and risk gates remain
            # independent of this field.
            from collections import Counter
            day_regime=Counter(regimes).most_common(1)[0][0]
            state["day_regime"]=day_regime
            state["regime_strategy_order"]=list(self.strategy_order(day_regime))
        if admission_block:
            state["reason"]=admission_block
            for signal in signals: self._gate(signal,"NOT_SELECTED",admission_block)
            return
        outcomes=self.store.list_records("episodes",10000)
        offers=[]; seen=set(account["consumed_signals"])
        for signal in signals:
            if signal["id"] in seen: continue
            underlying,symbol_quotes=self._execution_snapshot(signal["symbol"])
            now=self._now()
            options=[q for q in symbol_quotes.values() if quote_is_fresh(q,now,self.settings.max_quote_age_seconds)]
            if self.market:
                if not quote_is_fresh(underlying,now,self.settings.underlying_quote_age_seconds):
                    self._gate(signal,"WAITING_DATA","Fresh index quote unavailable"); continue
                if options:
                    universe=options[0].get("strike_universe")
                    if not universe:
                        self._gate(signal,"WAITING_DATA","Complete strike universe unavailable for strike context"); continue
                    atm=min(universe,key=lambda x:abs(x-underlying["ltp"]))
                    options=[{**q,"is_atm":q["strike"]==atm} for q in options]
            candidates=self.pipeline.option_candidates(signal,options,account["cash"],now,self.settings.max_spread_pct,buyer_screen=True)
            if not candidates:
                screens=self.pipeline.last_option_screens
                reason="No candidate with fresh executable depth" if not screens else "; ".join(screens[0]["reasons"]) or "Contract identity or cash check failed"
                self._gate(signal,"WAITING_DATA" if not screens or any(c["missing_data"] for c in screens) else "REJECTED",
                           reason,option_screens=screens); continue
            reasons=[]; signal_offers=[]
            for c in candidates[:3]:
                now=self._now()
                try: offer,reason=self._prepare_offer(signal,c,account,outcomes,now)
                except Exception as exc: offer,reason=None,self._safe_error(exc)
                if offer: signal_offers.append(offer)
                elif reason: reasons.append({"contract_id":c["contract_id"],"reason":reason,
                    "phase":state["reviews"].get(signal["symbol"],{}).get("phase")})
            offers.extend(signal_offers)
            if not signal_offers:
                self._gate(signal,"WAITING_DATA" if any(r.get("phase")=="WAITING_DATA" or "candle" in r["reason"].lower() or r["reason"]=="Waiting for broker fee preparation" for r in reasons) else "REJECTED",
                    reasons[0]["reason"] if reasons else "No eligible contract",contract_results=reasons)
        ranked=rank_opportunities(offers)
        state["offers"]=[self._offer_view(o) for o in ranked]
        if not ranked:
            state["reason"]="No eligible opportunity after data, protection, cost and risk checks" if signals else "No confirmed strategy setup"
            return
        state["reason"]="Candidates ranked; rechecking the best available offer"
        # Retain the complete ranked comparison, not merely the winner, once
        # per signal/contract set so historical decisions remain reviewable.
        comparison=hashlib.sha256(json.dumps([(o["signal"]["id"],o["contract"]["contract_id"]) for o in ranked]).encode()).hexdigest()[:24]
        self.store.put_record("strategy_selections",comparison,{"evaluated_at":now.isoformat(),"version":self.version,
            "offers":state["offers"],"rule":state["selection_rule"]})
        for offer in ranked:
            if self._execute_offer(offer):
                for other in ranked:
                    if other["signal"]["id"]!=offer["signal"]["id"]:
                        self._gate(other["signal"],"NOT_SELECTED","Another eligible opportunity was selected for the shared account")
                return
        state["reason"]="Final revalidation blocked every ranked candidate"

    @staticmethod
    def _offer_view(o):
        return {"signal_id":o["signal"]["id"],"strategy":o["signal"]["strategy_name"],"symbol":o["signal"]["symbol"],
            "contract_id":o["contract"]["contract_id"],"quantity":o.get("quantity"),"risk":o["risk"],"net_reward_at_target":o["net_reward"],
            "net_reward_risk":o["net_reward_risk"],"evidence":o["ev"]["status"],"samples":o["ev"].get("samples",0),
            "ml_quality":o["signal"].get("ml_quality"),"exit_policy":o["signal"].get("exit_policy"),
            "market_structure":o["signal"].get("market_structure"),"outcome_estimate":o["signal"].get("outcome_estimate"),
            "orchestrator_decision":o["signal"].get("orchestrator_decision"),
            "specialist_agents":o["signal"].get("specialist_agents",{}),
            "option_screen":o["contract"].get("option_screen"),"entry_economics":o["signal"].get("entry_economics"),
            "adversarial_warnings":o["signal"].get("adversarial_warnings",[])}

    def _execute_offer(self,offer):
        cached_only=getattr(self.broker.cost,"cached_only",None)
        if cached_only:
            try:
                with cached_only(): return self._execute_prepared_offer(offer)
            except ValueError as exc:
                if str(exc)!="Fresh broker fee reserve required before final paper admission": raise
                self._gate(offer["signal"],"WAITING_DATA",str(exc)); return False
        return self._execute_prepared_offer(offer)

    def _execute_prepared_offer(self,offer):
        s=offer["signal"]; c=offer["contract"]
        now=self._now()
        if self.stop_event.is_set() or self._session()!="ENTRY_WINDOW" or not self._signal_fresh(s,now):
            self._gate(s,"REJECTED","Session ended, engine stopped or setup expired before fill"); return False
        if getattr(self.gateway,"credential_provider",None): self.gateway.refresh_credentials()
        if offer["generation"]!=getattr(self.gateway,"credential_generation",0):
            self._gate(s,"WAITING_DATA","Credentials rotated; fresh candidate data required"); return False
        under,symbol_quotes=self._execution_snapshot(s["symbol"])
        now=self._now()
        latest=symbol_quotes.get(c["contract_id"],{})
        if not quote_is_fresh(latest,now,self.settings.max_quote_age_seconds):
            self._gate(s,"WAITING_DATA","Final executable quote is stale or unavailable"); return False
        if any(latest.get(k)!=c.get(k) for k in ("contract_id","expiry","strike","lot_size","option_type")):
            self._gate(s,"REJECTED","Contract identity changed before fill"); return False
        final_screen=assess_option(latest,s,now,max_spread=self.settings.max_spread_pct,max_quote_age=self.settings.max_quote_age_seconds)
        if final_screen["status"]!="PASS":
            self._gate(s,final_screen["status"],"Final option screen: "+"; ".join(final_screen["reasons"])); return False
        c={**c,**latest,"option_screen":final_screen,"spread_pct":final_screen["spread_pct"]}
        # Greeks can change even when premium does not. Rebuild the evidence,
        # features and economics against the final observed contract snapshot.
        refreshed,reason=self._prepare_offer(s,c,self.broker.snapshot(),
            self.store.list_records("episodes",10000),now)
        if not refreshed:
            self._gate(s,"WAITING_DATA",reason or "Current quote is not executable"); return False
        offer=refreshed; s=offer["signal"]; c=offer["contract"]
        now=self._now()
        if self.stop_event.is_set() or self._session()!="ENTRY_WINDOW" or not self._signal_fresh(s,now):
            self._gate(s,"REJECTED","Entry authorization expired during final review"); return False
        if offer["generation"]!=getattr(self.gateway,"credential_generation",0):
            self._gate(s,"WAITING_DATA","Credentials rotated during final review"); return False
        if self.market:
            under,_=self._execution_snapshot(s["symbol"])
            now=self._now()
            if not quote_is_fresh(under,now,self.settings.underlying_quote_age_seconds):
                self._gate(s,"WAITING_DATA","Final index quote is stale or unavailable"); return False
            invalid=s["invalidation"]; spot=under.get("ltp")
            if spot is None or (spot<=invalid if s["option_type"]=="CALL" else spot>=invalid):
                self._gate(s,"REJECTED","Underlying has invalidated the setup"); return False
            target=s.get("underlying_target")
            if target is not None and (spot>=target if s["option_type"]=="CALL" else spot<=target):
                self._gate(s,"REJECTED","Underlying target was already reached before entry"); return False
        # Final review can outlive the two-second depth window. Take the
        # current book immediately before virtual admission; PaperBroker
        # recalculates liquidity, charges, risk and the option screen on it.
        _,books=self._execution_snapshot(s["symbol"])
        latest=books.get(c["contract_id"],{})
        now=self._now()
        if not quote_is_fresh(latest,now,self.settings.max_quote_age_seconds):
            self._gate(s,"WAITING_DATA","Final executable quote expired during review"); return False
        if any(latest.get(k)!=c.get(k) for k in ("contract_id","expiry","strike","lot_size","option_type")):
            self._gate(s,"REJECTED","Contract identity changed during review"); return False
        mode="paper_observation" if offer["ev"]["status"]=="OBSERVATION" else "supported_net_evidence"
        s={**s,"risk_rupees":offer["risk"],"evidence_mode":mode,"selection_evidence":self._offer_view(offer)}
        s["agent_contexts"]={**s["agent_contexts"],"Option Selector":c["option_context"],"EV":mode,
                             "Risk":"shared_portfolio","Execution":execution_context(now),
                             **{name.replace(" Agent", ""):row.get("status") for name,row in (s.get("specialist_agents") or {}).items()}}
        try:
            now=self._now()
            order=self.broker.place_order(contract=c,quote={**c,**latest},quantity=offer["quantity"],signal=s,now=now)
        except Exception as exc:
            self._gate(s,"REJECTED",self._safe_error(exc),risk_veto=True); return False
        for agent in ("Scanner","Regime","Setup","Confirmation","Option Selector","EV","Risk"):
            self.publish(event(agent,s["symbol"],offer["ev"]["status"] if agent=="EV" else "PASS",
                offer["ev"]["reason"] if agent=="EV" else s["strategy_name"]+": entry checks passed",strategy_id=s["strategy_id"],signal_id=s["id"]))
        self.publish(event("Execution",s["symbol"],"FILLED","Paper BUY: "+s["strategy_name"],evaluation=order))
        self._record_review(s,c,copy.deepcopy(s["decision_review"]),now,s["option_type"],"Paper entry filled after atomic risk admission","FILLED")
        self.store.put_record("strategy_opportunities",s["id"],{**s,"status":"SELECTED","order_id":order["id"],"evaluated_at":now.isoformat()})
        with self.lock: self.pending_signals.pop(s["id"],None)
        self.status["portfolio"].update(selected=self._offer_view(offer),last_selected={**self._offer_view(offer),"at":now.isoformat()},reason="Paper position opened")
        self.status["entry_error"]=None
        return True

    def describe_strategies(self):
        episodes=[t for t in self.store.list_records("episodes",10000) if t.get("portfolio_version")==self.version]
        stats=[]
        for spec in self.strategy_specs:
            trades=[t for t in episodes if t.get("strategy_id")==spec["id"] and t.get("strategy_version")==spec["version"]]
            values=[float(t["pnl"]) for t in trades]
            stats.append({**spec,"closed_trades":len(trades),"wins":sum(v>0 for v in values),
                "losses":sum(v<0 for v in values),"net_pnl":sum(values),"estimated_costs":sum(float(t.get("costs",0)) for t in trades),
                "mean_net_pnl":sum(values)/len(values) if values else None,
                "validation":"UNVALIDATED_PAPER","source":"Executed paper positions only; candidates are not fills"})
        return {**self.status["portfolio"],"performance":stats,
            "data_health":copy.deepcopy(self.status.get("data_symbols",{})),
            "market_context":{symbol:self.context_at(symbol,self._now()) for symbol in ("NIFTY","SENSEX")},
            "opportunities":self.store.list_records("strategy_opportunities",30),
            "historical_scope":"Earlier candle reports do not validate the current Delta and midpoint-spread buying screen"}
