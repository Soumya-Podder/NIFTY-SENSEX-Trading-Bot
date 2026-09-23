import threading
import time
import math
from datetime import timedelta
import pandas as pd
from .pipeline import DecisionPipeline,execution_context,plan_protection,plan_exit
from .risk import RiskEngine,available_risk
from .expectancy import ExpectancyEngine
from .session import now_ist, session_state, quote_is_fresh
from .telemetry.decision_trace import event, AGENT_ORDER
from .telemetry.event_bus import event_bus


class PaperEngine:
    def __init__(self,settings,store,gateway,broker,market=None):
        self.settings=settings; self.store=store; self.gateway=gateway; self.broker=broker
        self.market=market
        self.stop_event=threading.Event(); self.lock=threading.RLock(); self.threads=[]
        self.quotes={}; self.contracts=[]; self.frames={}; self.processed={}; self.last_status=None
        self.protections={}; self.policy_day=None
        self.status={"state":"STARTING","last_cycle":None,"error":None,"session":"PREOPEN"}
        self.status["scans"]={}
        self.wait_reasons={}
        self.last_credential_generation=-1

        self.pipeline=DecisionPipeline(store.active_learning_policies(),self.publish)
        self.risk=RiskEngine(settings.max_trade_risk_rupees,settings.daily_loss_limit_rupees,
                             settings.hard_daily_halt_rupees,settings.max_open_positions)

    def _freeze_policies(self,now):
        day=str(now.date())
        if self.policy_day==day: return
        frozen=self.store.get_record("session_models",day)
        if frozen is None:
            import hashlib,json
            policies=self.store.active_learning_policies()
            frozen={"session":day,"policies":policies,"strategy_version":"orb-retest-v1",
                    "hash":hashlib.sha256(json.dumps(policies,sort_keys=True).encode()).hexdigest(),
                    "frozen_at":now.isoformat()}
            self.store.put_record("session_models",day,frozen)
        self.pipeline.policies=frozen["policies"]; self.policy_day=day
        self.status["frozen_model"]=frozen

    def publish(self,item):
        self.store.record_event(item); event_bus.publish(item)
        symbol=item.get("symbol")
        if symbol in {"NIFTY","SENSEX"}:
            self.status["scans"].setdefault(symbol,{}).update(stage=item["agent"],reason=item["summary"],status=item["status"],decision_at=item["timestamp"])

    def start(self):
        if self.threads: return
        for name,target in (("paper-nifty",lambda:self._data_loop("NIFTY")),("paper-sensex",lambda:self._data_loop("SENSEX")),("paper-quotes",self._quote_loop),("paper-engine",self._loop),("paper-feedback",self._feedback_loop),("paper-feed-watch",self._feed_watch)):
            thread=threading.Thread(name=name,target=target,daemon=True); self.threads.append(thread); thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads: thread.join(timeout=2)

    def _session(self):
        return session_state(start=self.settings.session_start,cutoff=self.settings.entry_cutoff,exit_at=self.settings.session_exit)

    def _feed_watch(self):
        while not self.stop_event.is_set():
            try:
                if self.market and hasattr(self.market,"reconnect_if_idle"):
                    self.market.reconnect_if_idle()
                self.status["feed_watch_error"]=None
            except Exception as exc: self.status["feed_watch_error"]=type(exc).__name__+": waiting to reconnect market feed"
            self.stop_event.wait(2)

    def _feedback_loop(self):
        # Validation can take minutes. Never hold up another position's exit while
        # waiting for a learning lock; completed episodes are the durable queue.
        from .telemetry.agent_metrics import learn_from_outcomes
        while not self.stop_event.is_set():
            try:
                for episode in self.store.pending_paper_feedback():
                    if self.stop_event.is_set(): return
                    learn_from_outcomes([episode],"paper",self.store,run_id="paper:"+episode["id"],quality="verified")
                self.status["feedback_error"]=None
            except Exception as exc: self.status["feedback_error"]=str(exc)[:300]
            self.stop_event.wait(5)

    def _data_loop(self,only_symbol=None):
        while not self.stop_event.is_set():
            if self._session() in {"ENTRY_WINDOW","MANAGE_ONLY"}:
                try:
                    day=now_ist().date(); contracts=[]; frames={}
                    for symbol in ((only_symbol,) if only_symbol else ("NIFTY","SENSEX")):
                        frame=self.gateway.candles(symbol,day-timedelta(days=7),day+timedelta(days=1))
                        frame=frame[frame.timestamp+pd.Timedelta(minutes=1)<=pd.Timestamp(now_ist())]
                        frames[symbol]=self.pipeline.features(frame)
                        with self.lock: self.frames[symbol]=frames[symbol]
                        self.status.setdefault("data_symbols",{})[symbol]={"updated_at":now_ist().isoformat(),
                            "last_bar":str(frame.timestamp.max()) if not frame.empty else None,"rows":len(frame)}
                        chain=self.gateway.chain(symbol,exclude_expiry_day=bool(self.broker.policy))
                        cash=self.broker.snapshot()["cash"]
                        affordable=[c for c in chain if c.get("ltp") and 0<float(c["ltp"])*c["lot_size"]<cash]
                        affordable.sort(key=lambda c:abs(abs(c.get("delta") or 0)-.5))
                        contracts.extend(affordable[:24])
                        self.status["data_symbols"][symbol].update(chain_contracts=len(chain),subscribed_candidates=len(affordable[:24]))
                        with self.lock:
                            self.contracts=[c for c in self.contracts if c["symbol"]!=symbol]+affordable[:24]
                        if self.broker.policy:
                            self._freeze_policies(now_ist())
                            from .setups import opening_range_retest
                            signal=opening_range_retest(frames[symbol],now_ist())
                            if signal:
                                signal=self.pipeline.plan_candidate(signal,symbol)
                            if signal:
                                self.store.put_record("opportunities",signal["id"],{**signal,"status":"OBSERVED",
                                    "reason":"Paper admission gates still apply; this is not a fill"})
                                # Fetch only candidate-side protection inputs outside
                                # the risk/exit heartbeat. Never perform HTTP in exits.
                                for contract in [c for c in affordable[:24] if c["option_type"]==signal["option_type"]][:3]:
                                    bars=self.gateway.contract_candles(contract,day,day+timedelta(days=1))
                                    retest=bars[bars.timestamp==pd.Timestamp(signal["retest_timestamp"])]
                                    if len(retest)==1:
                                        with self.lock:
                                            self.protections[(signal["id"],contract["contract_id"])]=dict(retest.iloc[0])|contract
                    self.status["data_error"]=None
                except Exception as exc:
                    self.status["data_error"]=str(exc)[:300]
                    if only_symbol: self.status.setdefault("data_symbols",{})[only_symbol]={"error":str(exc)[:300],"updated_at":now_ist().isoformat()}
            self.stop_event.wait(10)

    def _quote_loop(self):
        while not self.stop_event.is_set():
            positions=self.broker.positions()["positions"]
            research_positions=getattr(self,"research_positions",lambda:[])()
            active=self._session() in {"ENTRY_WINDOW","MANAGE_ONLY"}
            if active or positions or research_positions:
                try:
                    with self.lock: contracts=list(self.contracts) if active else []
                    by_id={c["contract_id"]:c for c in [*contracts,*positions,*research_positions]}
                    if by_id:
                        if self.market:
                            self.market.subscribe_options(list(by_id.values()))
                            streamed=self.market.executable_quotes()
                            quotes={k:{**v,**streamed[k]} for k,v in by_id.items() if k in streamed}
                        else: quotes=self.gateway.quotes(list(by_id.values()))
                        for position in [*positions,*research_positions]:
                            q=quotes.get(position["contract_id"])
                            if q and q.get("bid",0)>0:
                                try: q["exit_cost_estimate"]=self.broker.cost.quote(position,0,q["bid"],position["qty"])["total"]
                                except Exception: q["exit_cost_estimate"]=None
                        with self.lock: self.quotes=quotes
                        self.status["quote_error"]=None
                except Exception as exc: self.status["quote_error"]=str(exc)[:300]
            self.stop_event.wait(2)

    def _loop(self):
        consecutive_errors = 0
        while not self.stop_event.is_set():
            try:
                self.cycle()
                consecutive_errors = 0
                if not self.broker.state.get("halted") or self.broker.state.get("halt_reason") != "Paper engine error; exits remain active":
                    self.status["error"] = None
            except Exception as exc:
                consecutive_errors += 1
                self.status["error"] = str(exc)[:300]
                import logging
                logging.getLogger("paper_engine").exception("Paper engine cycle error: %s", exc)
                if consecutive_errors >= 2:
                    try:
                        self.broker.control(halted=True, reason="Paper engine error; exits remain active")
                        self.publish(event("Risk", "PORTFOLIO", "REJECTED", f"Paper engine error: {str(exc)[:150]}", evaluation={"error": str(exc)[:300]}))
                    except Exception as persist_exc:
                        self.status["persistence_error"]=type(persist_exc).__name__
            self.stop_event.wait(2)

    def _refresh_runtime_credentials(self,now):
        if not getattr(self.gateway,"credential_provider",None): return
        self.gateway.refresh_credentials()
        credentials=self.gateway.credentials
        changed=self.market.refresh_credentials(*credentials) if self.market else False
        if changed or self.last_credential_generation!=self.gateway.credential_generation:
            with self.lock:
                self.quotes.clear(); self.frames.clear(); self.protections.clear(); self.processed.clear()
            # Errors produced with the previous token no longer describe the
            # current client. A new request may set a fresh error afterwards.
            self.status.pop("data_error",None)
            for symbol_status in self.status.get("data_symbols",{}).values():
                symbol_status.pop("error",None)
            self.last_credential_generation=self.gateway.credential_generation
        self.status["credentials"]={"checked_at":now.isoformat(),"generation":self.gateway.credential_generation,
            "configured":all(credentials),"source":"project .env"}

    def cycle(self):
        now=now_ist(); session=self._session()
        self._refresh_runtime_credentials(now)
        if self.broker.policy: self._freeze_policies(now)
        self.status.update(last_cycle=now.isoformat(),session=session)
        previous_day=self.broker.snapshot()["session_date"]
        self.broker.new_session(now)
        if previous_day!=str(now.date()) and self.settings.paper_autostart:
            self.broker.control(enabled=True)
        with self.lock: quotes=dict(self.quotes); frames=dict(self.frames)
        if self.market and hasattr(self.market,"executable_quotes"):
            streamed=self.market.executable_quotes()
            for cid,q in streamed.items():
                previous=quotes.get(cid,{})
                quotes[cid]={**q,"exit_cost_estimate":previous.get("exit_cost_estimate") if previous.get("bid")==q.get("bid") else None}
        try:
            self.broker.mark(quotes,now)
            self.status["persistence_error"]=None
        except Exception as exc:
            # A failed valuation write must not prevent an observed protective exit.
            # Broker rollback preserves the last durable account; entries stay blocked.
            self.status["persistence_error"]=type(exc).__name__
        account=self.broker.snapshot()
        limit=min(self.settings.daily_loss_limit_rupees,self.settings.hard_daily_halt_rupees)
        if account["session_pnl"]<=-limit:
            self.broker.control(halted=True,reason="Daily portfolio loss limit reached")
            from .telemetry.agent_metrics import rollback_policies
            rollback_policies(self.store,"Forward paper daily-loss limit reached")
        for p in list(account["positions"]):
            q=quotes.get(p["contract_id"],{})
            reason=None
            if self.broker.policy:
                fresh=quote_is_fresh(q,now,self.settings.max_quote_age_seconds)
                under=(self.market.snapshot().get("symbols",{}).get(p["symbol"],{}) if self.market else {})
                underlying=under.get("ltp") if quote_is_fresh(under,now,self.settings.max_quote_age_seconds) else None
                reason=plan_exit(p,now,bid=q.get("bid") if fresh else None,underlying=underlying,halted=self.broker.state["halted"] or bool(self.status.get("persistence_error")),close_start=self.settings.session_exit)
            elif session not in {"ENTRY_WINDOW","MANAGE_ONLY"}: reason="SESSION_EXIT"
            elif self.broker.state["halted"]: reason="RISK_HALT"
            elif quote_is_fresh(q,now,self.settings.max_quote_age_seconds):
                if q.get("bid",0)<=p["stop"]: reason="STOP"
                elif q.get("bid",0)>=p["target"]: reason="TARGET"
            if reason:
                try:
                    if not q: raise ValueError("Exit pending: waiting for fresh held-contract depth")
                    trade=self.broker.close(p["id"],q,reason,now)
                    if trade:
                        self.publish(event("Execution",p["symbol"],"FILLED",f"Paper exit: {reason}",evaluation=trade))
                        self.status["exit_error"]=None
                except Exception as exc:
                    self.status["exit_error"]=str(exc)[:300]
                    self.broker.control(halted=True,reason="Exit pending: waiting for fresh depth and broker charges")
        account=self.broker.snapshot()
        if session!="ENTRY_WINDOW" or not account["enabled"] or account["halted"] or not account["valuation_complete"]:
            self.status["state"]="HALTED" if account["halted"] else "PAUSED" if not account["enabled"] else session
            if self.last_status!=self.status["state"]:
                for symbol in ("NIFTY","SENSEX"):
                    self.publish(event("Scanner",symbol,"WAITING",self.status["state"],evaluation={"session":session}))
                self.last_status=self.status["state"]
            return
        self.status["state"]="RUNNING"; self.last_status="RUNNING"
        self.evaluate_entries(frames,quotes,now)

    def evaluate_entries(self,frames,quotes,now):
        for symbol in ("NIFTY","SENSEX"):
            with self.lock: frame=frames.get(symbol)
            if frame is None or frame.empty:
                self.scan_wait(symbol,"Waiting for completed index candles",now)
        if not self.broker.policy: self.pipeline.policies=self.store.active_learning_policies()
        for symbol,frame in frames.items():
            if frame.empty: continue
            row=frame.iloc[-1].to_dict(); stamp=row["timestamp"]
            if str(stamp.date())!=str(now.date()) or not 60<=(pd.Timestamp(now)-stamp).total_seconds()<=125:
                self.scan_wait(symbol,"Waiting for a fresh completed one-minute candle",now,last_bar=str(stamp)); continue
            if self.processed.get(symbol)==str(stamp):
                self.status["scans"].setdefault(symbol,{})["checked_at"]=now.isoformat()
                continue
            today=frame[frame.timestamp.dt.date==now.date()]
            opening=today[(today.timestamp.dt.strftime("%H:%M")>=self.settings.session_start)&(today.timestamp.dt.strftime("%H:%M")<"09:30")]
            signal=(self.pipeline.plan_signal(frame,now,symbol) if self.broker.policy else
                    self.pipeline.signal(row,opening.high.max() if len(opening) else None,opening.low.min() if len(opening) else None,len(opening)))
            self.status["scans"][symbol]={"checked_at":now.isoformat(),"last_bar":str(stamp),
                "status":"CANDIDATE" if signal else "NO_SETUP","reason":"Candidate proceeding through entry gates" if signal else "No completed ORB retest/resumption setup"}
            if not signal:
                self.processed[symbol]=str(stamp)
                self.scan_wait(symbol,"Building opening range" if now.strftime("%H:%M")<"09:30" else "No completed ORB retest/resumption setup",now,last_bar=str(stamp))
                continue
            self._enter(signal,quotes,now)

    def scan_wait(self,symbol,reason,now,**details):
        self.status["scans"][symbol]={"checked_at":now.isoformat(),"status":"WAITING","reason":reason,**details}
        key=(reason,details.get("last_bar"))
        if self.wait_reasons.get(symbol)!=key:
            self.pipeline.stage("Scanner",symbol,"WAITING",reason,**details)
            self.wait_reasons[symbol]=key

    def _enter(self,signal,quotes,now):
        symbol=signal["symbol"]; account=self.broker.snapshot()
        options=[q for q in quotes.values() if q["symbol"]==symbol and quote_is_fresh(q,now,self.settings.max_quote_age_seconds)]
        if self.market:
            underlying=self.market.snapshot().get("symbols",{}).get(symbol,{})
            if not quote_is_fresh(underlying,now,self.settings.max_quote_age_seconds) or not underlying.get("ltp"):
                self.pipeline.stage("Option Selector",symbol,"REJECTED","Fresh index quote required to exclude current ATM","stale_underlying")
                return
            if options:
                spot=float(underlying["ltp"])
                universe=options[0].get("strike_universe") or [q["strike"] for q in options]
                atm=min(universe,key=lambda strike:abs(strike-spot))
                options=[{**q,"is_atm":abs(q["strike"]-atm)<1e-8} for q in options]
        candidates=self.pipeline.option_candidates(signal,options,account["cash"],now,self.settings.max_spread_pct)
        outcomes=self.store.list_records("episodes",10000)
        for contract in candidates[:3]:
            price=contract["ask"]; lot=contract["lot_size"]
            try:
                if self.broker.policy:
                    with self.lock: retest=self.protections.get((signal["id"],contract["contract_id"]))
                    signal=plan_protection(signal,contract,retest,price)
                stop_price=signal.get("stop_price"); target_price=signal.get("target_price")
                if not isinstance(stop_price,(int,float)) or not math.isfinite(stop_price) or not 0<stop_price<price:
                    raise ValueError("No market-derived stop is available; fixed-percentage stops are disabled")
                if not isinstance(target_price,(int,float)) or not math.isfinite(target_price) or target_price<=price:
                    raise ValueError("No valid target is available")
                stop_fraction=(price-stop_price)/price
                fee=self.broker.cost.quote(contract,price,stop_price,lot)
                same_direction=sum(p["risk_rupees"] for p in account["positions"] if p["option_type"]==signal["option_type"])
                if self.broker.policy:
                    if account["positions"] or self.broker.policy.entry_veto(account["loss_ledger"],now): continue
                    quantity=lot
                else:
                    decision=self.risk.approve(price,stop_fraction,lot,account["session_pnl"],account["open_positions"],
                        cash=account["cash"],open_risk=account["open_risk_rupees"],estimated_cost=fee["total"],
                        exit_slippage=contract["ask"]-contract["bid"],correlated_risk=same_direction,
                        correlated_limit=self.settings.max_correlated_risk_rupees,halted=account["halted"])
                    if not decision.approved: continue
                    quantity=min(decision.quantity,int(contract["ask_qty"])//lot*lot)
                # Recalculate exact quantity charges; percentage estimates are not used for risk.
                fee=self.broker.cost.quote(contract,price,stop_price,quantity)
                risk=quantity*((price-stop_price)+contract["ask"]-contract["bid"])+fee["total"]
                budget=(min(self.broker.policy.trade_risk,self.broker.policy.remaining(account["loss_ledger"],account["open_risk_rupees"])) if self.broker.policy else
                        available_risk(self.settings.max_trade_risk_rupees,self.settings.daily_loss_limit_rupees,
                            account["session_pnl"],account["open_risk_rupees"],self.settings.max_correlated_risk_rupees,same_direction))
                if risk>budget: continue
                matched=[t for t in outcomes if t.get("setup")==signal["setup"] and t.get("regime")==signal["regime"]]
                ev=ExpectancyEngine().evaluate(matched,(target_price-price)*quantity,(price-stop_price)*quantity,fee["total"])
                if self.broker.policy:
                    matched=[t for t in matched if t.get("strategy_version")==signal["strategy_version"] and str(t.get("exit_ts",""))<now.isoformat()]
                    ev=ExpectancyEngine().evaluate_net(matched)
                    if (self.settings.paper_collect_evidence and ev["reason"]=="Insufficient independent net-outcome evidence"):
                        ev={**ev,"status":"OBSERVATION","reason":"Paper evidence collection; net edge is unvalidated. All execution and risk limits apply."}
                if self.broker.policy and ev["status"]=="OBSERVATION":
                    if not self.settings.paper_collect_evidence:
                        ev={**ev,"status":"REJECTED","reason":"Plan v1 requires supported positive net expectancy; research evidence is insufficient"}
                ev_context="uncalibrated" if ev["status"]=="OBSERVATION" else "positive" if ev["status"]=="PASS" else "nonpositive"
                if not self.pipeline.stage("EV",symbol,ev["status"],ev["reason"],ev_context,evidence=ev): return
                risk_context="one_position" if account["open_positions"]==0 else "shared_portfolio"
                if not self.pipeline.stage("Risk",symbol,"PASS","Cash, charges, daily and correlated risk checked",risk_context,risk_rupees=risk,quantity=quantity): return
                fill_context=execution_context(now)
                if not self.pipeline.stage("Execution",symbol,"PASS","Observed ask liquidity; simulated fill only",fill_context,spread_pct=contract["spread_pct"]): return
                signal["agent_contexts"].update({"Option Selector":contract["option_context"],"EV":ev_context,"Risk":risk_context,"Execution":fill_context})
                signal["risk_rupees"]=risk
                signal["evidence_mode"]="paper_observation" if ev["status"]=="OBSERVATION" else "supported_net_evidence"
                if getattr(self.gateway,"credential_provider",None):
                    self.gateway.refresh_credentials()
                    if self.last_credential_generation!=self.gateway.credential_generation:
                        self.scan_wait(symbol,"Credentials changed; waiting for refreshed market data",now); return
                if self.stop_event.is_set(): return
                order=self.broker.place_order(contract=contract,quote=contract,quantity=quantity,signal=signal,now=now)
                self.status["entry_error"]=None
                self.publish(event("Execution",symbol,"FILLED","Paper BUY filled at observed ask",evaluation=order))
                return
            except Exception as exc:
                self.status["entry_error"]=str(exc)[:300]
        self.pipeline.stage("Risk",symbol,"REJECTED","No contract meets total risk and cash limits","budget_exceeded")
