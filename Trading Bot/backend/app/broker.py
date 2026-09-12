import uuid
import threading
import math
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from .session import now_ist, local_time, quote_is_fresh, session_state

class PaperBroker:
    def __init__(self,store=None,capital=30000,cost=None,max_quote_age=2,clock=now_ist,entry_cutoff="14:30",policy=None):
        self.store=store; self.cost=cost; self.max_quote_age=max_quote_age
        self.clock=clock
        self.entry_cutoff=entry_cutoff
        self.policy=policy
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

    def health(self): return {"healthy":self.persistence_error is None,"mode":"paper","simulated_execution":True,"persistence_error":self.persistence_error}

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
                if reason and not ledger.get("lock_reason"): ledger["lock_reason"]=reason; self.state.update(halted=True,halt_reason=reason)
            self._persist()

    def place_order(self,*,contract,quote,quantity,signal,now=None):
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
                if self.state["positions"] or quantity!=lot: raise ValueError("Plan v1 permits one position and one lot across both indices")
                if str(contract["expiry"])[:10]==str(now.date()): raise ValueError("Plan v1 excludes expiry-day entries")
            price=float(quote.get("ask",0))
            if not math.isfinite(price) or price<=0 or quote.get("ask_qty",0)<quantity:
                raise ValueError("Insufficient observed ask liquidity for a full paper fill")
            fee=self.cost.quote(contract,price,0,quantity)
            if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Quote expired while estimating charges")
            if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Entry cutoff passed while estimating charges")
            debit=price*quantity+fee["total"]
            if debit>self.state["cash"]: raise ValueError("Insufficient paper cash including charges")
            if self.policy:
                stop=signal.get("stop_price"); target=signal.get("target_price")
                if not isinstance(stop,(float,int)) or not math.isfinite(stop) or not 0<stop<price:
                    raise ValueError("Plan requires a predeclared structural premium stop; percentage fallback is not allowed")
                if not isinstance(target,(float,int)) or not math.isfinite(target) or target-price<2*(price-stop):
                    raise ValueError("Plan requires a predeclared target with at least 2:1 nominal reward/risk")
                round_trip=self.cost.quote(contract,price,stop,quantity)["total"]
                planned_risk=(price-stop+max(0,price-float(quote["bid"])))*quantity+round_trip
                if not math.isfinite(planned_risk) or planned_risk<=0 or planned_risk>min(self.policy.trade_risk,self.policy.remaining(self.state["loss_ledger"])):
                    raise ValueError("One-lot all-in stop risk exceeds remaining plan allocation")
                if debit>self.policy.premium_limit or self.state["cash"]-debit<self.policy.cash_reserve:
                    raise ValueError("Plan premium commitment or cash reserve exceeded")
                if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Quote expired during atomic risk admission")
                if session_state(self.clock(),cutoff=self.entry_cutoff)!="ENTRY_WINDOW": raise ValueError("Entry cutoff passed during atomic risk admission")
                signal={**signal,"risk_rupees":planned_risk}
            identifier=str(uuid.uuid4())
            p={**contract,"id":identifier,"contract_id":contract["contract_id"],"qty":quantity,
               "entry":price,"entry_ts":now.isoformat(),"entry_charges":fee,
               "entry_charges_remaining":fee["total"],"mark":float(quote["bid"]),"stale":False,
               "stop":signal["stop_price"] if self.policy else price*(1-signal["stop_percent"]),
               "target":signal["target_price"] if self.policy else price*(1+signal["target_percent"]),
               "risk_rupees":signal["risk_rupees"],"setup":signal["setup"],"regime":signal["regime"],
               "agent_contexts":signal["agent_contexts"],"policy_versions":signal.get("policy_versions",{}),
               "signal_id":signal["id"],"quality":"verified","source":"paper_live_quotes","mae":0,"mfe":0}
            if self.policy:
                p.update({k:signal.get(k) for k in ("invalidation","horizon_minutes","exit_policy","protection_evidence","strategy_version")})
                p["evidence_mode"]=signal.get("evidence_mode","paper_observation")
                p.update({k:signal.get(k) for k in ("strategy_id","strategy_name","portfolio_version","underlying_target","selection_evidence")})
                p.update({k:signal.get(k) for k in ("entry_features","ml_quality","option_atr")})
                p["initial_stop"]=p["stop"]
            order={"id":identifier,"side":"BUY","status":"FILLED","price":price,"quantity":quantity,
                   "contract_id":p["contract_id"],"timestamp":now.isoformat(),"charges":fee,
                   "fill_model":"observed_ask_full_depth","mode":"paper"}
            self.state["cash"]-=debit; self.state["charges"]+=fee["total"]
            self.state["positions"].append(p); self.state["consumed_signals"].append(signal["id"])
            if self.policy: self.state["loss_ledger"]["entries"]+=1
            self._persist(("orders",identifier,order))
            return order

    def close(self,position_id,quote,reason,now=None):
        now=local_time(now or now_ist())
        with self.lock:
            p=next((p for p in self.state["positions"] if p["id"]==position_id),None)
            if not p: return None
            if quote.get("contract_id")!=p["contract_id"]: raise ValueError("Exit quote belongs to another contract")
            if not quote_is_fresh(quote,now,self.max_quote_age): raise ValueError("Exit pending: no fresh executable bid")
            if p.get("last_exit_quote")==quote.get("timestamp"): return None
            lot=int(p["lot_size"]); available=int(quote.get("bid_qty",0))//lot*lot
            qty=min(p["qty"],available); price=float(quote.get("bid",0))
            if qty<=0 or not math.isfinite(price) or price<=0: raise ValueError("Exit pending: insufficient bid depth")
            fee=self.cost.quote(p,0,price,qty)
            if not quote_is_fresh(quote,self.clock(),self.max_quote_age): raise ValueError("Exit quote expired while estimating charges")
            allocated=p["entry_charges_remaining"]*qty/p["qty"]
            gross=(price-p["entry"])*qty; net=gross-allocated-fee["total"]
            identifier=str(uuid.uuid4())
            trade={**p,"id":identifier,"position_id":p["id"],"quantity":qty,"qty":qty,
                   "entry_premium":p["entry"],"exit":price,"exit_premium":price,"exit_ts":now.isoformat(),
                   "gross_pnl":gross,"costs":allocated+fee["total"],"pnl":net,"reason":reason,
                   "exit_charges":fee,"allocated_entry_charges":allocated,
                   "holding_minutes":(now-local_time(p["entry_ts"])).total_seconds()/60,
                   "fill_model":"observed_bid_with_depth","partial":qty<p["qty"]}
            order={"id":identifier,"side":"SELL","status":"FILLED","price":price,"quantity":qty,
                   "contract_id":p["contract_id"],"timestamp":now.isoformat(),"charges":fee,"mode":"paper"}
            self.state["cash"]+=qty*price-fee["total"]
            self.state["charges"]+=fee["total"]; self.state["realized_pnl"]+=net
            remaining=p["qty"]-qty
            if not self.policy: p["risk_rupees"]*=remaining/p["qty"]
            p["qty"]=remaining; p["entry_charges_remaining"]-=allocated; p["last_exit_quote"]=quote["timestamp"]
            records=[("orders",identifier,order),("trades",identifier,trade)]
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
            self._persist(*records)
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
            valid=isinstance(profile,dict) and profile.get("status") == "success"
            details=profile.get("data", {}) if isinstance(profile,dict) and isinstance(profile.get("data"),dict) else profile
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
