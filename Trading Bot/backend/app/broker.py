import uuid
import threading
import math
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from .session import now_ist, local_time, quote_is_fresh, session_state

class PaperBroker:
    def __init__(self,store=None,capital=30000,cost=None,max_quote_age=2,clock=now_ist,entry_cutoff="14:30",policy=None,notifier=None,option_screen_limits=None):
        self.store=store; self.cost=cost; self.max_quote_age=max_quote_age
        self.clock=clock
        self.entry_cutoff=entry_cutoff
        self.policy=policy
        self.notifier=notifier
        self.option_screen_limits=option_screen_limits
        self.lock=threading.RLock()
        self.persistence_error=None
        self._committed_state=None
        self.state=(store.get_record("paper","account") if store else None) or {
            "initial_capital":capital,"cash":capital,"positions":[],"realized_pnl":0,
            "charges":0,"session_date":str(local_time(self.clock()).date()),"session_start_equity":capital,
            "peak_equity":capital,"max_drawdown":0,"enabled":True,"halted":False,"halt_reason":None,
            "consumed_signals":[]}
        if policy and "loss_ledger" not in self.state:
            day=self.state["session_date"]
            episodes=[t for t in store.list_records("episodes",100000) if str(t.get("exit_ts",""))[:10]==day] if store else []
            orders=[o for o in store.list_records("orders",100000) if str(o.get("timestamp",""))[:10]==day and o.get("side")=="BUY"] if store else []
            trades=[t for t in store.list_records("trades",100000) if str(t.get("exit_ts",""))[:10]==day] if store else []
            self.state["loss_ledger"]={"loss_spend":sum(max(0,-t["pnl"]) for t in episodes),
                "losses":sum(t["pnl"]<0 for t in episodes),"entries":len(orders),
                "gross_realized":sum(t["gross_pnl"] for t in trades),
                "last_exit":max((t["exit_ts"] for t in episodes),default=None),"lock_reason":None}
        self.state.setdefault("daily_results",{})
        self._persist()

    def _notify(self,message):
        if self.notifier:
            try: self.notifier.notify(message)
            except Exception: pass

    def _persist(self,*records):
        try:
            if self.store: self.store.save_bundle([("paper","account",self.state),*records])
        except Exception as exc:
            if self._committed_state is not None:
                self.state=deepcopy(self._committed_state)
            self.persistence_error=type(exc).__name__
            raise
        self._committed_state=deepcopy(self.state)
        self.persistence_error=None

    def health(self): return {"healthy":self.persistence_error is None,"mode":"paper","simulated_execution":True,"persistence_error":self.persistence_error,
        "fill_model":"Observed top ask entry / top bid exit, bounded by displayed quantity; partial exits supported",
        "live_performance_validated":False,
        "fill_limitations":["No queue priority, submission latency, competing depth consumption or market impact model",
            "Receipt age does not prove exchange book freshness; simulated P&L is unvalidated paper observation"]}

    def recover_persistence(self):
        """Retry the committed account write; never reconstruct or invent a fill."""
        with self.lock:
            if self.persistence_error: self._persist()
            return self.persistence_error is None

    def positions(self):
        with self.lock: return {"quantity":sum(p["qty"] for p in self.state["positions"]),"positions":[dict(p) for p in self.state["positions"]]}

    def snapshot(self):
        with self.lock:
            positions=[dict(p) for p in self.state["positions"]]
            equity=self.state["cash"]+sum(p["mark"]*p["qty"] for p in positions)
            unrealized=sum((p["mark"]-p["entry"])*p["qty"]-p["entry_charges_remaining"] for p in positions)
            liquidation_complete=all(not p.get("stale",True) and p.get("exit_cost_estimate") is not None and p.get("executable_quantity",0)>=p["qty"] for p in positions)
            exit_costs=sum(p.get("exit_cost_estimate") or 0 for p in positions)
            extra={}
            if self.policy:
                ledger=dict(self.state["loss_ledger"])
                extra={"loss_ledger":ledger,"remaining_loss_allocation":self.policy.remaining(ledger,sum(p["risk_rupees"] for p in positions)),
                    "gross_session_pnl":ledger["gross_realized"]+sum((p["mark"]-p["entry"])*p["qty"] for p in positions),
                    "premium_committed":sum(p["entry"]*p["qty"] for p in positions),"plan_policy":self.policy.describe()}
            return {**self.state,**extra,"positions":positions,"equity":equity,"unrealized_pnl":unrealized,
                    "liquidation_pnl":equity-self.state["session_start_equity"]-exit_costs if liquidation_complete else None,
                    "liquidation_equity":equity-exit_costs if liquidation_complete else None,"liquidation_complete":liquidation_complete,
                    "session_pnl":equity-self.state["session_start_equity"],
                    "open_risk_rupees":sum(p["risk_rupees"] for p in positions),"open_positions":len(positions),
                    "valuation_complete":all(not p.get("stale",True) for p in positions)}

    def control(self,enabled=None,halted=None,reason=None):
        with self.lock:
            if enabled is not None: self.state["enabled"]=enabled
            if halted is not None:
                if not halted and self.policy and self.state["loss_ledger"].get("lock_reason"):
                    raise ValueError("A plan risk/profit lock cannot be cleared by Resume")
                self.state["halted"]=halted; self.state["halt_reason"]=reason if halted else None
            self._persist()

    def engine_error_halt(self,recover=False):
        """Only the recovered execution loop may clear its own technical halt."""
        reason="Paper engine error; exits remain active"
        with self.lock:
            if recover:
                if self.persistence_error or self.state["positions"] or self.state.get("halt_reason")!=reason:
                    return False
                if self.policy and self.state["loss_ledger"].get("lock_reason"): return False
                self.control(halted=False)
                return True
            if not self.state["halted"]: self.control(halted=True,reason=reason)
            return False

    def new_session(self,now=None):
        day=str(local_time(now or now_ist()).date())
        with self.lock:
            if day!=self.state["session_date"]:
                if self.state["positions"]:
                    self.control(halted=True,reason="Previous session position needs an observed exit quote")
                    return
                self.state["daily_results"][self.state["session_date"]]=self.state["cash"]-self.state["session_start_equity"]
                self.state["session_date"]=day
                self.state["session_start_equity"]=self.state["cash"]
                self.state["consumed_signals"]=[]
                if self.policy:
                    previous=self.state["loss_ledger"].get("lock_reason")
                    self.state["loss_ledger"]={"loss_spend":0,"losses":0,"entries":0,"gross_realized":0,"last_exit":None,"lock_reason":previous if previous in {"WEEKLY_LOSS_PAUSE","DRAWDOWN_PAUSE"} else None}
                    if previous and not self.state["loss_ledger"]["lock_reason"]:
                        self.state["halted"]=False; self.state["halt_reason"]=None
                self._persist()

    def mark(self,quotes,now=None):
        with self.lock:
            for p in self.state["positions"]:
                q=quotes.get(p["contract_id"],{})
                p["stale"]=not quote_is_fresh(q,now,self.max_quote_age) or not math.isfinite(float(q.get("bid",0))) or q.get("bid",0)<=0
                if not p["stale"] and q.get("bid",0)>0:
                    p["mark"]=float(q["bid"]); p["mark_timestamp"]=q["timestamp"]
                    p["executable_quantity"]=q.get("bid_qty",0)
                    from .adaptive_exit import update_exit
                    update_exit(p, p["mark"], now or self.clock(), q.get("exit_cost_estimate"))
                    if self.policy: p["exit_cost_estimate"]=q.get("exit_cost_estimate")
                    move=(p["mark"]-p["entry"])*p["qty"]
                    p["mae"]=min(p.get("mae",0),move); p["mfe"]=max(p.get("mfe",0),move)
                    if self.policy and p.get("exit_cost_estimate") is not None:
                        net_path=move-p["entry_charges_remaining"]-p["exit_cost_estimate"]
                        p["net_mae"]=max(p.get("net_mae",0),-net_path,0)
                        p["net_mfe"]=max(p.get("net_mfe",0),net_path,0)
            snap=self.snapshot()
            if snap["valuation_complete"]:
                self.state["peak_equity"]=max(self.state["peak_equity"],snap["equity"])
                self.state["max_drawdown"]=min(self.state["max_drawdown"],snap["equity"]-self.state["peak_equity"])
            if self.policy and snap["liquidation_complete"]:
                ledger=self.state["loss_ledger"]; reason=None
                self.state["liquidation_peak"]=max(self.state.get("liquidation_peak",self.state["initial_capital"]),snap["liquidation_equity"])
                date=local_time(now or self.clock()).date(); monday=str(date-timedelta(days=date.weekday()))
                week_pnl=sum(pnl for day,pnl in self.state["daily_results"].items() if monday<=day<str(date))+snap["liquidation_pnl"]
                if snap["liquidation_pnl"]<=-self.policy.loss_allocation: reason="DAILY_FLATTEN"
                elif snap["liquidation_equity"]-self.state["liquidation_peak"]<=-self.policy.max_drawdown: reason="DRAWDOWN_PAUSE"
                elif week_pnl<=-self.policy.weekly_loss: reason="WEEKLY_LOSS_PAUSE"
                elif self.policy.target_reached(snap["gross_session_pnl"], snap["liquidation_pnl"]):
                    reason="NET_PROFIT_LOCK" if self.policy.target_basis == "net" else "GROSS_PROFIT_LOCK"
                if reason and not ledger.get("lock_reason"):
                    ledger["lock_reason"]=reason; self.state.update(halted=True,halt_reason=reason)
            if self.persistence_error or self.state != self._committed_state:
                self._persist()

    def place_order(self,*,contract,quote,quantity,signal,now=None):
        if getattr(self.cost,"paper",False):
            with self.cost.cached_only():
                return self._place_order(contract=contract,quote=quote,quantity=quantity,signal=signal,now=now)
        return self._place_order(contract=contract,quote=quote,quantity=quantity,signal=signal,now=now)

    def _place_order(self,*,contract,quote,quantity,signal,now=None):
        now=local_time(now or now_ist())
        with self.lock:
            if self.persistence_error: raise ValueError("Paper entries paused: account persistence recovery required")
            if self.state["halted"] or not self.state["enabled"]: raise ValueError("Paper entries paused")
            if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Outside paper entry window")
            if not contract.get("identity_verified") or str(contract.get("expiry",""))[:10]<str(now.date()):
                raise ValueError("Contract identity or expiry is invalid")
            if quote.get("contract_id")!=contract.get("contract_id"): raise ValueError("Quote belongs to another contract")
            if signal["id"] in self.state["consumed_signals"]: raise ValueError("Duplicate signal")
            if any(p["symbol"]==contract["symbol"] for p in self.state["positions"]): raise ValueError("Position already open for index")
            if not quote_is_fresh(quote,now,self.max_quote_age): raise ValueError("Stale option quote")
            lot=int(contract["lot_size"])
            if quantity<=0 or quantity%lot: raise ValueError("Invalid lot multiple")
            if self.policy:
                veto=self.policy.entry_veto(self.state["loss_ledger"],now)
                if veto: raise ValueError(veto)
                if self.state["positions"]: raise ValueError("Plan permits one position across both indices")
                if quote.get("bid_qty",0)<quantity: raise ValueError("Insufficient observed bid depth for sized position")
                if str(contract["expiry"])[:10]==str(now.date()): raise ValueError("Plan v1 excludes expiry-day entries")
            price=float(quote.get("ask",0))
            if not math.isfinite(price) or price<=0 or quote.get("ask_qty",0)<quantity:
                raise ValueError("Insufficient observed ask liquidity for a full paper fill")
        # Fee HTTP must never hold the account lock needed by protective exits.
        fee=self.cost.quote(contract,price,0,quantity)
        stop=signal.get("stop_price"); target=signal.get("target_price")
        round_trip=self.cost.quote(contract,price,stop,quantity)["total"] if (self.policy or self.option_screen_limits) and isinstance(stop,(float,int)) and 0<stop<price else None
        target_cost=self.cost.quote(contract,price,target,quantity)["total"] if self.option_screen_limits and isinstance(target,(float,int)) and target>price else None
        with self.lock:
            if self.persistence_error or self.state["halted"] or not self.state["enabled"]:
                raise ValueError("Paper entries paused while estimating charges")
            if signal["id"] in self.state["consumed_signals"] or (self.policy and self.state["positions"]) or any(p["symbol"]==contract["symbol"] for p in self.state["positions"]):
                raise ValueError("Account changed while estimating charges")
            if self.policy:
                veto=self.policy.entry_veto(self.state["loss_ledger"],self.clock())
                if veto: raise ValueError(veto)
            if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Quote expired while estimating charges")
            if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Entry cutoff passed while estimating charges")
            debit=price*quantity+fee["total"]
            if debit>self.state["cash"]: raise ValueError("Insufficient paper cash including charges")
            stop=signal.get("stop_price"); target=signal.get("target_price")
            if not isinstance(stop,(float,int)) or not math.isfinite(stop) or not 0<stop<price:
                raise ValueError("A predeclared market-derived premium stop is required; percentage fallback is disabled")
            if not isinstance(target,(float,int)) or not math.isfinite(target) or target<=price:
                raise ValueError("A predeclared premium target is required")
            if self.policy:
                from decimal import Decimal
                if Decimal(str(target))-Decimal(str(price)) < 2*(Decimal(str(price))-Decimal(str(stop))):
                    raise ValueError("Plan requires a predeclared target with at least 2:1 nominal reward/risk")
                planned_risk=(price-stop+max(0,price-float(quote["bid"])))*quantity+round_trip
                if not math.isfinite(planned_risk) or planned_risk<=0 or planned_risk>self.policy.risk_budget(self.state["loss_ledger"],quantity//lot):
                    raise ValueError("All-in stop risk exceeds remaining plan allocation")
                if debit>min(self.state["initial_capital"],self.policy.premium_limit) or self.state["cash"]-debit<self.policy.cash_reserve:
                    raise ValueError("Plan premium commitment or cash reserve exceeded")
                if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Quote expired during atomic risk admission")
                if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Entry cutoff passed during atomic risk admission")
                signal={**signal,"risk_rupees":planned_risk}
            if self.option_screen_limits is not None:
                from .option_screen import assess, net_economics, VERSION
                max_spread, min_net_rr = self.option_screen_limits
                final_screen=assess({**contract,**quote},signal,self.clock(),max_spread=max_spread,max_quote_age=self.max_quote_age)
                if final_screen["status"]!="PASS": raise ValueError("Option screen: "+"; ".join(final_screen["reasons"]))
                economics=net_economics(price,float(quote["bid"]),stop,target,quantity,
                    round_trip,
                    target_cost)
                if economics["net_reward_risk"]<min_net_rr:
                    raise ValueError("Net target reward/risk below configured minimum")
                if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Quote expired during option screen admission")
                if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Entry cutoff passed during option screen admission")
                final_screen=assess({**contract,**quote},signal,self.clock(),max_spread=max_spread,max_quote_age=self.max_quote_age)
                if final_screen["status"]!="PASS": raise ValueError("Option screen expired during cost calculation")
                contract={**contract,"option_screen":final_screen,"option_screen_version":VERSION}
                signal={**signal,"option_screen_version":VERSION,"entry_economics":economics}
            if signal.get("decision_policy_version"):
                from .specialist_agents import assess_specialists, VERSION as REVIEW_VERSION
                if signal["decision_policy_version"]!=REVIEW_VERSION:
                    raise ValueError("Unsupported specialist decision policy")
                limits=self.option_screen_limits or (.02,1.)
                decision=assess_specialists(signal,{**contract,**quote},self.clock(),risk=signal["risk_rupees"],
                    reward=signal.get("entry_economics",{}).get("net_reward"),max_quote_age=self.max_quote_age,
                    max_spread=limits[0],min_net_reward_risk=limits[1])
                if decision["vetoes"]:
                    raise ValueError("Specialist evidence expired or conflicted during atomic admission: "+", ".join(decision["vetoes"]))
            identifier=str(uuid.uuid4())
            p={**contract,"id":identifier,"contract_id":contract["contract_id"],"qty":quantity,
               "entry_quote_observation_id":quote.get("observation_id"),
               "entry":price,"entry_ts":now.isoformat(),"entry_charges":fee,
               "entry_charges_remaining":fee["total"],"mark":float(quote["bid"]),"stale":False,
               "stop":float(stop),"target":float(target),
               "risk_rupees":signal["risk_rupees"],"setup":signal["setup"],"regime":signal["regime"],
               "agent_contexts":signal["agent_contexts"],"policy_versions":signal.get("policy_versions",{}),
               "signal_id":signal["id"],"quality":"verified","source":"paper_live_quotes","mae":0,"mfe":0}
            if str(signal.get("portfolio_version","")).startswith("autonomous-paper"):
                p["quality"]="unvalidated_paper_observation"
            # Preserve the complete decision evidence on the durable position
            # and final episode. Required specialist checks gate entry; losing
            # episodes must retain the exact matrix and adversarial challenge
            # that preceded the Risk Sentinel decision for later forensics.
            p.update({k:signal.get(k) for k in (
                "specialist_agents", "agent_scores", "orchestrator_decision",
                "adversarial_warnings", "market_context", "market_structure", "outcome_estimate", "option_screen_version", "entry_economics",
                "decision_policy_version", "decision_review", "sizing_policy_version") if k in signal})
            if self.policy:
                p.update({k:signal.get(k) for k in ("invalidation","horizon_minutes","exit_policy","protection_evidence","strategy_version")})
                p["evidence_mode"]=signal.get("evidence_mode","paper_observation")
                p.update({k:signal.get(k) for k in ("strategy_id","strategy_name","portfolio_version","underlying_target","selection_evidence")})
                p.update({k:signal.get(k) for k in ("entry_features","ml_quality","option_atr")})
                p["initial_stop"]=p["stop"]
                p["risk_per_unit"]=price-stop+max(0,price-float(quote["bid"]))
                p["risk_charge_reserve"]=round_trip
            order={"id":identifier,"side":"BUY","status":"FILLED","price":price,"quantity":quantity,
                   "quote_observation_id":quote.get("observation_id"),
                   "contract_id":p["contract_id"],"timestamp":now.isoformat(),"charges":fee,
                   "fill_model":"observed_ask_full_depth","mode":"paper"}
            self.state["cash"]-=debit; self.state["charges"]+=fee["total"]
            self.state["positions"].append(p); self.state["consumed_signals"].append(signal["id"])
            if self.policy: self.state["loss_ledger"]["entries"]+=1
            self._persist(("orders",identifier,order))
            current_pnl=self.snapshot()["session_pnl"]
            self._notify(f"PAPER ENTRY CONFIRMED · {p['symbol']} {p.get('option_type','')}\n{p.get('strike','')} · Qty {quantity}\nEntry: ₹{price:,.2f}\nCurrent session P&L: ₹{current_pnl:,.2f}\nEstimated charges: ₹{fee['total']:,.2f}\nRisk: ₹{p['risk_rupees']:,.2f}")
            return order

    def request_management_exit(self,position_id,reason):
        with self.lock:
            position=next((p for p in self.state["positions"] if p["id"]==position_id),None)
            if position and not position.get("adaptive_exit_request"):
                position["adaptive_exit_request"]=reason
                self._persist()

    def request_exit(self,position_id,reason,now=None):
        with self.lock:
            position=next((p for p in self.state["positions"] if p["id"]==position_id),None)
            if position and not position.get("exit_request"):
                position["exit_request"]={"position_id":position_id,"reason":reason,
                    "first_requested_at":local_time(now or self.clock()).isoformat(),"attempts":0,
                    "status":"PENDING","remaining_quantity":position["qty"]}
                self._persist(("exit_requests",position_id,dict(position["exit_request"])))

    def close(self,position_id,quote,reason,now=None):
        """Persist exit intent before attempting a fill; resume the original reason."""
        now=local_time(now or self.clock())
        with self.lock:
            p=next((p for p in self.state["positions"] if p["id"]==position_id),None)
            if not p: return None
            request=p.setdefault("exit_request",{"position_id":position_id,"reason":reason,
                "first_requested_at":now.isoformat(),"attempts":0,"status":"PENDING"})
            request.update(attempts=request["attempts"]+1,last_attempt_at=now.isoformat(),remaining_quantity=p["qty"])
            self._persist(("exit_requests",position_id,dict(request)))
            preview=dict(p)
            exit_reason=request["reason"]
        # A legacy position may lack a cached exit prequote. Fetch its fee
        # without holding the ledger lock; the fill rechecks quantity and age.
        try:
            prepared=None
            if quote and quote.get("contract_id")==preview["contract_id"]:
                lot=int(preview["lot_size"])
                qty=min(preview["qty"],int(quote.get("bid_qty",0))//lot*lot)
                if qty>0 and float(quote.get("bid",0))>0:
                    fast=getattr(self.cost,"fast_exit_estimate",None)
                    fee=fast(preview,qty) if fast else None
                    if fee is None: fee=self.cost.quote(preview,0,float(quote["bid"]),qty)
                    prepared=(qty,fee)
            return self._close_fill(position_id,quote,exit_reason,now,prepared_fee=prepared)
        except Exception as exc:
            with self.lock:
                p=next((p for p in self.state["positions"] if p["id"]==position_id),None)
                if p:
                    failures=p["exit_request"].setdefault("failure_history",[])
                    failures.append({"at":self.clock().isoformat(),"type":type(exc).__name__,
                        "reason":str(exc)[:300],"bid":quote.get("bid") if quote else None,
                        "quote_timestamp":quote.get("timestamp") if quote else None})
                    del failures[:-8]
                    p["exit_request"].update(last_error=str(exc)[:300],status="PENDING")
                    self.state.update(halted=True,halt_reason="Exit pending: waiting for executable depth or persistence recovery")
                    self._persist(("exit_requests",position_id,dict(p["exit_request"])))
            raise

    def _close_fill(self,position_id,quote,reason,now=None,*,prepared_fee=None):
        now=local_time(now or now_ist())
        with self.lock:
            p=next((p for p in self.state["positions"] if p["id"]==position_id),None)
            if not p: return None
            if not quote: raise ValueError("Exit pending: waiting for fresh held-contract depth")
            if quote.get("contract_id")!=p["contract_id"]: raise ValueError("Exit quote belongs to another contract")
            if not quote_is_fresh(quote,now,self.max_quote_age): raise ValueError("Exit pending: no fresh executable bid")
            if p.get("last_exit_quote")==quote.get("timestamp"): return None
            lot=int(p["lot_size"]); available=int(quote.get("bid_qty",0))//lot*lot
            qty=min(p["qty"],available); price=float(quote.get("bid",0))
            if qty<=0 or not math.isfinite(price) or price<=0: raise ValueError("Exit pending: insufficient bid depth")
            if not prepared_fee or prepared_fee[0]!=qty:
                raise ValueError("Exit pending: quantity changed during fee preparation")
            fee=prepared_fee[1]
            if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Exit quote expired while estimating charges")
            allocated=p["entry_charges_remaining"]*qty/p["qty"]
            gross=(price-p["entry"])*qty; net=gross-allocated-fee["total"]
            final_net=float(p.get("episode_totals",{}).get("pnl",0))+net
            p["mae"]=min(float(p.get("mae",0)),final_net)
            p["mfe"]=max(float(p.get("mfe",0)),final_net)
            identifier=str(uuid.uuid4())
            trade={**p,"id":identifier,"position_id":p["id"],"quantity":qty,"qty":qty,
                   "exit_quote_observation_id":quote.get("observation_id"),
                   "entry_premium":p["entry"],"exit":price,"exit_premium":price,"exit_ts":now.isoformat(),
                   "gross_pnl":gross,"costs":allocated+fee["total"],"pnl":net,"reason":reason,
                   "exit_charges":fee,"allocated_entry_charges":allocated,
                   "costs_estimated":bool(fee.get("estimated") or p["entry_charges"].get("estimated")),
                   "estimated_exit":False,
                   "paper_research_only":str(p.get("portfolio_version","")).startswith("autonomous-paper"),
                   "learning_eligible":not bool(fee.get("estimated") or p["entry_charges"].get("estimated")),
                   "holding_minutes":(now-local_time(p["entry_ts"])).total_seconds()/60,
                   "fill_model":"observed_bid_with_depth","partial":qty<p["qty"]}
            order={"id":identifier,"side":"SELL","status":"FILLED","price":price,"quantity":qty,
                   "quote_observation_id":quote.get("observation_id"),
                   "contract_id":p["contract_id"],"timestamp":now.isoformat(),"charges":fee,"mode":"paper"}
            self.state["cash"]+=qty*price-fee["total"]
            self.state["charges"]+=fee["total"]; self.state["realized_pnl"]+=net
            remaining=p["qty"]-qty
            if not self.policy: p["risk_rupees"]*=remaining/p["qty"]
            elif "risk_per_unit" in p:
                p["risk_rupees"]=p["risk_per_unit"]*remaining+p["risk_charge_reserve"] if remaining else 0
            p["qty"]=remaining; p["entry_charges_remaining"]-=allocated; p["last_exit_quote"]=quote["timestamp"]
            records=[("orders",identifier,order),("trades",identifier,trade)]
            p["exit_request"].update(status="PARTIAL" if remaining else "COMPLETED",remaining_quantity=remaining,
                last_error=None,last_fill_at=now.isoformat())
            trade["exit_request"]=dict(p["exit_request"])
            if fee.get("estimated"): trade["quality"]="paper_estimated_costs"
            records.append(("exit_requests",position_id,dict(p["exit_request"])))
            episode=p.get("episode_totals",{"pnl":0,"costs":0,"gross_pnl":0,"quantity":0,"exit_fills":0})
            for key,value in (("pnl",net),("costs",trade["costs"]),("gross_pnl",gross),("quantity",qty),("exit_fills",1)):
                episode[key]+=value
            p["episode_totals"]=episode
            if not remaining:
                self.state["positions"].remove(p)
                records.append(("episodes",p["id"],{**trade,**episode,"id":p["id"],"partial":False}))
                if self.policy:
                    ledger=self.state["loss_ledger"]
                    ledger["loss_spend"]+=max(0,-episode["pnl"])
                    ledger["losses"]+=int(episode["pnl"]<0); ledger["last_exit"]=now.isoformat()
            if self.policy: self.state["loss_ledger"]["gross_realized"]+=gross
            if (not self.state["positions"] and self.state["halted"]
                    and str(self.state.get("halt_reason") or "").startswith("Exit pending:")
                    and not (self.policy and self.state["loss_ledger"].get("lock_reason"))):
                self.state["halted"]=False
                self.state["halt_reason"]=None
            self._persist(*records)
            current_pnl=self.snapshot()["session_pnl"]
            self._notify(f"PAPER EXIT CONFIRMED · {p['symbol']} {p.get('option_type','')}\nQty {qty} · Exit: ₹{price:,.2f}\nReason: {reason}\nTrade net P&L: ₹{net:,.2f}\nCurrent session P&L: ₹{current_pnl:,.2f}\nCharges: ₹{trade['costs']:,.2f}")
            if self.policy and not remaining:
                try: self.mark({},now)
                except Exception:
                    # The fill above is durable. A later valuation failure is
                    # exposed by health and must not masquerade as a failed fill.
                    pass
            return trade

class DhanBroker:
    def __init__(self,client_id="",access_token="",live_enabled=False):
        self.client_id=client_id; self.access_token=access_token; self.live_enabled=live_enabled; self._dhan=None
    @property
    def configured(self): return bool(self.client_id and self.access_token)
    def connect(self):
        if not self.configured: raise RuntimeError("Dhan credentials not configured")
        from dhanhq import DhanContext,dhanhq
        self._dhan=dhanhq(DhanContext(self.client_id,self.access_token)); return True
    def health(self): return {"healthy":self._dhan is not None,"configured":self.configured,"mode":"live" if self.live_enabled else "disabled"}
    def validate_access(self):
        if not self.configured: return {"valid":False,"reason":"credentials_not_configured"}
        try:
            from dhanhq import DhanLogin
            profile=DhanLogin(self.client_id).user_profile(self.access_token)
            details=profile.get("data", {}) if isinstance(profile,dict) and isinstance(profile.get("data"),dict) else profile
            valid=isinstance(details,dict) and (profile.get("status") == "success" or
                bool(details.get("dhanClientId") and details.get("tokenValidity")))
            return {"valid":valid,"reason":None if valid else "profile_check_failed",
                    "data_plan":details.get("dataPlan") if isinstance(details,dict) else None,
                    "data_validity":details.get("dataValidity") if isinstance(details,dict) else None}
        except Exception as exc:
            return {"valid":False,"reason":str(exc)}
    def positions(self):
        if not self._dhan: self.connect()
        return self._dhan.get_positions()
    def place_order(self,**kwargs):
        raise RuntimeError("This application is paper-only; live order placement is not implemented")
