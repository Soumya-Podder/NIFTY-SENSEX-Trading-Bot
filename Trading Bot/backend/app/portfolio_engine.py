"""Three paper hypotheses, one selector, one atomic portfolio authority."""
from datetime import timedelta
import hashlib
import json
import math
import threading
import time
import pandas as pd
from .paper_engine import PaperEngine
from .strategy_portfolio import STRATEGIES, PORTFOLIO_VERSION, evaluate_strategies, rank_opportunities, regime_strategy_policy
from .pipeline import plan_protection, execution_context
from .expectancy import ExpectancyEngine
from .session import now_ist, quote_is_fresh
from .telemetry.decision_trace import event
from .ai import LearningService, extract_features
from .adaptive_exit import VERSION as ADAPTIVE_EXIT_VERSION
from .specialist_agents import assess_specialists


class MultiStrategyPaperEngine(PaperEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.protection_requests={}; self.protection_results={}
        self.audit_keys={}; self.entry_wakeup=threading.Event()
        self.learning=LearningService(self.store)
        self.ml_frozen={}
        self.status["portfolio"]={"version":PORTFOLIO_VERSION,"strategies":list(STRATEGIES),
            "evidence":"UNVALIDATED_PAPER","evaluations":[],"offers":[],"selected":None,
            "reason":"Waiting for session","selection_rule":"Supported net evidence first; then the day's regime-compatible strategy order, net target reward / all-in risk and spread. No profit probability is claimed.",
            "day_regime":None,"regime_strategy_order":list(regime_strategy_policy("TRANSITION"))}

    def _freeze_policies(self,now):
        day=str(now.date())
        if self.policy_day==day: return
        key=day+":"+PORTFOLIO_VERSION
        frozen=self.store.get_record("session_models",key)
        if frozen is None:
            specification=json.dumps(STRATEGIES,sort_keys=True)
            frozen={"session":day,"policies":{},"strategy_version":PORTFOLIO_VERSION,
                "strategies":list(STRATEGIES),"hash":hashlib.sha256(specification.encode()).hexdigest(),
                "frozen_at":now.isoformat(),"validation":"UNVALIDATED_PAPER"}
            self.store.put_record("session_models",key,frozen)
        self.pipeline.policies={}; self.policy_day=day; self.status["frozen_model"]=frozen
        self.ml_frozen=self.learning.freeze(now)
        self.status["ml_session"]=self.ml_frozen
        with self.lock: self.protection_requests.clear(); self.protection_results.clear()

    def start(self):
        if self.threads: return
        super().start()
        for name,target in (("paper-selector",self._entry_loop),("paper-protection",self._protection_loop)):
            thread=threading.Thread(name=name,target=target,daemon=True)
            self.threads.append(thread); thread.start()

    def evaluate_entries(self,frames,quotes,now):
        # The shared exit heartbeat does not wait for historical/fee requests.
        self.entry_wakeup.set()

    def _data_loop(self,only_symbol=None):
        while not self.stop_event.is_set():
            now=now_ist()
            warmup=self._session() in {"PREOPEN","ENTRY_WINDOW","MANAGE_ONLY"} and "09:10"<=now.strftime("%H:%M")<self.settings.session_exit
            if warmup:
                for symbol in ((only_symbol,) if only_symbol else ("NIFTY","SENSEX")):
                    try:
                        generation=getattr(self.gateway,"credential_generation",0)
                        day=now.date()
                        frame=self.gateway.candles(symbol,day-timedelta(days=7),day+timedelta(days=1))
                        frame=frame[frame.timestamp+pd.Timedelta(minutes=1)<=pd.Timestamp(now_ist())]
                        chain=self.gateway.chain(symbol,exclude_expiry_day=True)
                        cash=self.broker.snapshot()["cash"]
                        affordable=[c for c in chain if c.get("ltp") and 0<float(c["ltp"])*c["lot_size"]<cash]
                        # Both directions get a subscription allocation; one direction
                        # cannot crowd the other out of the shared top-24 list.
                        chosen=[]
                        for side in ("CALL","PUT"):
                            candidates=[c for c in affordable if c["option_type"]==side]
                            candidates.sort(key=lambda c:(abs(abs(c.get("delta") or 0)-.5),-float(c.get("oi") or 0)))
                            chosen.extend(candidates[:12])
                        if generation!=getattr(self.gateway,"credential_generation",0): continue
                        with self.lock:
                            self.frames[symbol]=frame
                            self.contracts=[c for c in self.contracts if c["symbol"]!=symbol]+chosen
                        self.status.setdefault("data_symbols",{})[symbol]={"updated_at":now_ist().isoformat(),
                            "last_bar":str(frame.timestamp.max()) if not frame.empty else None,"rows":len(frame),
                            "chain_contracts":len(chain),"subscribed_candidates":len(chosen),"error":None}
                        self.status["data_error"]=None
                    except Exception as exc:
                        self.status.setdefault("data_symbols",{})[symbol]={"error":self._safe_error(exc),"updated_at":now_ist().isoformat()}
                        self.status["data_error"]=self._safe_error(exc)
            self.stop_event.wait(10)

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
            if stamp+pd.Timedelta(minutes=1)>pd.Timestamp(now_ist()): raise ValueError("Protection candle is not completed")
            bars=self.gateway.contract_candles(contract,start,end)
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
            result={"candle":{**candle,**contract,"source":"dhan_contract_minute","requested_from":start,"requested_to":end},
                "generation":request["generation"]}
        except Exception as exc:
            result={"candle":None,"reason":self._safe_error(exc),"generation":request["generation"],"retry_after":time.monotonic()+10}
        with self.lock:
            if request["generation"]==getattr(self.gateway,"credential_generation",0): self.protection_results[key]=result

    def _protection_loop(self):
        while not self.stop_event.is_set():
            with self.lock:
                request=next(iter(self.protection_requests.items()),None)
                if request: self.protection_requests.pop(request[0],None)
            if request:
                key,value=request
                if self._signal_fresh(value["signal"],now_ist()): self.prepare_protection(key,value)
            else: self.stop_event.wait(.25)

    @staticmethod
    def _signal_fresh(signal,now):
        age=(pd.Timestamp(now)-pd.Timestamp(signal["timestamp"])).total_seconds()
        return 60<=age<=125

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

    def _gate(self,signal,state,reason,**details):
        key=signal["id"]
        self.store.put_record("strategy_opportunities",key,{**signal,"status":state,"reason":reason,
            "evaluated_at":now_ist().isoformat(),**details})
        fingerprint=(state,reason)
        if self.audit_keys.get(key)!=fingerprint:
            self.publish(event("Option Selector" if state=="WAITING_DATA" else "Risk",signal["symbol"],
                "WAITING" if state=="WAITING_DATA" else "REJECTED",reason,strategy_id=signal["strategy_id"],signal_id=key))
            self.audit_keys[key]=fingerprint

    def _prepare_offer(self,signal,contract,account,outcomes,now):
        generation=getattr(self.gateway,"credential_generation",0)
        candle,reason=self._request_protection(signal,contract)
        if candle is None: return None,reason
        s=plan_protection(signal,contract,candle,contract["ask"],horizon_minutes=signal["horizon_minutes"])
        s.update(exit_policy=ADAPTIVE_EXIT_VERSION,option_atr=candle.get("option_atr"))
        s["entry_features"]=extract_features(signal.get("feature_row",{}),s,contract,now)
        quality=self.learning.score(s,self.ml_frozen)
        s["ml_quality"]=quality
        if not quality["allowed"]:
            probability=quality.get("probability")
            return None,(f"ML Quality Gate: {probability:.1%} below {quality['threshold']:.1%}" if probability is not None else "ML Quality Gate: "+quality["status"])
        qty=contract["lot_size"]; price=contract["ask"]
        stop_cost=self.broker.cost.quote(contract,price,s["stop_price"],qty)["total"]
        target_cost=self.broker.cost.quote(contract,price,s["target_price"],qty)["total"]
        buy_cost=self.broker.cost.quote(contract,price,0,qty)["total"]
        risk=(price-s["stop_price"]+price-contract["bid"])*qty+stop_cost
        reward=(s["target_price"]-price)*qty-target_cost
        specialists=assess_specialists(s,contract,now,risk=risk,reward=reward,
                                       max_quote_age=self.settings.max_quote_age_seconds)
        s={**s,"specialist_agents":specialists["agents"],
           "agent_scores":{name:row.get("status") for name,row in specialists["agents"].items()},
           "orchestrator_decision":specialists["decision"],
           "adversarial_warnings":specialists["agents"].get("Adversarial Agent",{}).get("warnings",[])}
        if specialists["vetoes"]:
            return None,"Specialist veto: "+"; ".join(specialists["vetoes"])
        budget=min(self.broker.policy.trade_risk,self.broker.policy.remaining(account["loss_ledger"],account["open_risk_rupees"]))
        if risk<=0 or risk>budget: return None,"One-lot all-in stop risk exceeds remaining budget"
        if price*qty+buy_cost>min(self.broker.policy.premium_limit,account["cash"]-self.broker.policy.cash_reserve):
            return None,"Premium and charges breach available cash or reserve"
        if reward/risk<1: return None,"Net target reward is less than all-in stop risk"
        matched=[t for t in outcomes if t.get("portfolio_version")==PORTFOLIO_VERSION and
            t.get("strategy_id")==s["strategy_id"] and t.get("strategy_version")==s["strategy_version"] and
            t.get("setup")==s["setup"] and t.get("regime")==s["regime"] and
            pd.Timestamp(t["exit_ts"])<pd.Timestamp(now)]
        ev=ExpectancyEngine().evaluate_net(matched)
        if ev["reason"]=="Insufficient independent net-outcome evidence" and self.settings.paper_collect_evidence:
            ev={**ev,"status":"OBSERVATION","reason":"Unvalidated paper evidence collection; no estimated profit probability"}
        if ev["status"]=="REJECTED": return None,ev["reason"]
        return {"signal":s,"contract":contract,"risk":risk,"net_reward":reward,"net_reward_risk":reward/risk,
            "ev":ev,"generation":generation},None

    def portfolio_cycle(self):
        now=now_ist(); self._freeze_policies(now)
        state=self.status["portfolio"]; state["checked_at"]=now.isoformat()
        state["selected"]=None;state["offers"]=[]
        if self._session()!="ENTRY_WINDOW":
            state["reason"]=self._session()
            state["evaluations"]=[{**spec,"symbol":symbol,"status":"WAITING","reason":self._session(),"checked_at":now.isoformat(),"evidence":"UNVALIDATED_PAPER"}
                for symbol in ("NIFTY","SENSEX") for spec in STRATEGIES]
            return
        account=self.broker.snapshot()
        if not account["enabled"] or account["halted"] or not account["valuation_complete"]:
            state["reason"]="Paper entries paused, halted or awaiting position valuation"; return
        veto=self.broker.policy.entry_veto(account["loss_ledger"],now)
        admission_block=veto or ("Shared account already has an open position" if account["positions"] else None)
        with self.lock: frames=dict(self.frames)
        quotes=self._quotes(); signals=[]; evaluations=[]
        for symbol in ("NIFTY","SENSEX"):
            found,rows=evaluate_strategies(frames.get(symbol),now,symbol)
            signals.extend(found); evaluations.extend(rows)
            self.scan_wait(symbol,"Evaluating strategy candidates" if found else rows[0]["reason"],now,
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
            state["regime_strategy_order"]=list(regime_strategy_policy(day_regime))
        if admission_block:
            state["reason"]=admission_block
            for signal in signals: self._gate(signal,"NOT_SELECTED",admission_block)
            return
        outcomes=self.store.list_records("episodes",10000)
        offers=[]; seen=set(account["consumed_signals"])
        for signal in signals:
            if signal["id"] in seen: continue
            options=[q for q in quotes.values() if q["symbol"]==signal["symbol"] and quote_is_fresh(q,now,self.settings.max_quote_age_seconds)]
            if self.market:
                underlying=self.market.snapshot().get("symbols",{}).get(signal["symbol"],{})
                if not quote_is_fresh(underlying,now,self.settings.max_quote_age_seconds):
                    self._gate(signal,"WAITING_DATA","Fresh index quote unavailable"); continue
                if options:
                    universe=options[0].get("strike_universe")
                    if not universe:
                        self._gate(signal,"WAITING_DATA","Complete strike universe unavailable for ATM exclusion"); continue
                    atm=min(universe,key=lambda x:abs(x-underlying["ltp"]))
                    options=[{**q,"is_atm":q["strike"]==atm} for q in options]
            candidates=self.pipeline.option_candidates(signal,options,account["cash"],now,self.settings.max_spread_pct)
            if not candidates:
                self._gate(signal,"WAITING_DATA","No eligible non-ATM contract with fresh executable depth"); continue
            reasons=[]; signal_offers=[]
            for c in candidates[:3]:
                try: offer,reason=self._prepare_offer(signal,c,account,outcomes,now)
                except Exception as exc: offer,reason=None,self._safe_error(exc)
                if offer: signal_offers.append(offer)
                elif reason: reasons.append({"contract_id":c["contract_id"],"reason":reason})
            offers.extend(signal_offers)
            if not signal_offers:
                self._gate(signal,"WAITING_DATA" if any("candle" in r["reason"].lower() for r in reasons) else "REJECTED",
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
        self.store.put_record("strategy_selections",comparison,{"evaluated_at":now.isoformat(),"version":PORTFOLIO_VERSION,
            "offers":state["offers"],"rule":state["selection_rule"]})
        for offer in ranked:
            if self._execute_offer(offer):
                for other in ranked:
                    if other["signal"]["id"]!=offer["signal"]["id"]:
                        self._gate(other["signal"],"NOT_SELECTED","Another eligible opportunity was selected for the shared account")
                return

    @staticmethod
    def _offer_view(o):
        return {"signal_id":o["signal"]["id"],"strategy":o["signal"]["strategy_name"],"symbol":o["signal"]["symbol"],
            "contract_id":o["contract"]["contract_id"],"risk":o["risk"],"net_reward_at_target":o["net_reward"],
            "net_reward_risk":o["net_reward_risk"],"evidence":o["ev"]["status"],"samples":o["ev"].get("samples",0),
            "ml_quality":o["signal"].get("ml_quality"),"exit_policy":o["signal"].get("exit_policy"),
            "orchestrator_decision":o["signal"].get("orchestrator_decision"),
            "specialist_agents":o["signal"].get("specialist_agents",{}),
            "adversarial_warnings":o["signal"].get("adversarial_warnings",[])}

    def _execute_offer(self,offer):
        now=now_ist(); s=offer["signal"]; c=offer["contract"]
        if self.stop_event.is_set() or self._session()!="ENTRY_WINDOW" or not self._signal_fresh(s,now): return False
        if getattr(self.gateway,"credential_provider",None): self.gateway.refresh_credentials()
        if offer["generation"]!=getattr(self.gateway,"credential_generation",0): return False
        latest=self._quotes().get(c["contract_id"],{})
        if not quote_is_fresh(latest,now,self.settings.max_quote_age_seconds): return False
        if any(latest.get(k)!=c.get(k) for k in ("contract_id","expiry","strike","lot_size","option_type")): return False
        if latest.get("ask")!=c["ask"] or latest.get("bid")!=c["bid"]:
            self._gate(s,"WAITING_DATA","Option price changed; repricing before selection"); return False
        if self.market:
            under=self.market.snapshot().get("symbols",{}).get(s["symbol"],{})
            if not quote_is_fresh(under,now,self.settings.max_quote_age_seconds): return False
            invalid=s["invalidation"]; spot=under.get("ltp")
            if spot is None or (spot<=invalid if s["option_type"]=="CALL" else spot>=invalid):
                self._gate(s,"REJECTED","Underlying has invalidated the setup"); return False
            if c.get("strike_universe") and c["strike"]==min(c["strike_universe"],key=lambda x:abs(x-spot)):
                self._gate(s,"REJECTED","Contract became ATM before entry"); return False
            target=s.get("underlying_target")
            if target is not None and (spot>=target if s["option_type"]=="CALL" else spot<=target):
                self._gate(s,"REJECTED","Underlying target was already reached before entry"); return False
        mode="paper_observation" if offer["ev"]["status"]=="OBSERVATION" else "supported_net_evidence"
        s={**s,"risk_rupees":offer["risk"],"evidence_mode":mode,"selection_evidence":self._offer_view(offer)}
        s["agent_contexts"]={**s["agent_contexts"],"Option Selector":c["option_context"],"EV":mode,
                             "Risk":"shared_portfolio","Execution":execution_context(now),
                             **{name.replace(" Agent", ""):row.get("status") for name,row in (s.get("specialist_agents") or {}).items()}}
        try:
            order=self.broker.place_order(contract=c,quote={**c,**latest},quantity=c["lot_size"],signal=s,now=now)
        except Exception as exc:
            self._gate(s,"REJECTED",self._safe_error(exc)); return False
        for agent in ("Scanner","Regime","Setup","Confirmation","Option Selector","EV","Risk"):
            self.publish(event(agent,s["symbol"],offer["ev"]["status"] if agent=="EV" else "PASS",
                offer["ev"]["reason"] if agent=="EV" else s["strategy_name"]+": entry checks passed",strategy_id=s["strategy_id"],signal_id=s["id"]))
        self.publish(event("Execution",s["symbol"],"FILLED","Paper BUY: "+s["strategy_name"],evaluation=order))
        self.store.put_record("strategy_opportunities",s["id"],{**s,"status":"SELECTED","order_id":order["id"],"evaluated_at":now.isoformat()})
        self.status["portfolio"].update(selected=self._offer_view(offer),last_selected={**self._offer_view(offer),"at":now.isoformat()},reason="Paper position opened")
        self.status["entry_error"]=None
        return True

    def describe_strategies(self):
        episodes=[t for t in self.store.list_records("episodes",10000) if t.get("portfolio_version")==PORTFOLIO_VERSION]
        stats=[]
        for spec in STRATEGIES:
            trades=[t for t in episodes if t.get("strategy_id")==spec["id"] and t.get("strategy_version")==spec["version"]]
            values=[float(t["pnl"]) for t in trades]
            stats.append({**spec,"closed_trades":len(trades),"wins":sum(v>0 for v in values),
                "losses":sum(v<0 for v in values),"net_pnl":sum(values),"estimated_costs":sum(float(t.get("costs",0)) for t in trades),
                "mean_net_pnl":sum(values)/len(values) if values else None,
                "validation":"UNVALIDATED_PAPER","source":"Executed paper positions only; candidates are not fills"})
        return {**self.status["portfolio"],"performance":stats,
            "opportunities":self.store.list_records("strategy_opportunities",30),
            "historical_scope":"Existing Backtest Lab reports test the ORB baseline, not this combined selector"}
