"""Chronological, shared-cash replay. Every position retains a fixed contract ID."""
from dataclasses import dataclass,field
from datetime import timedelta
import math
import uuid
import pandas as pd
from ..pipeline import DecisionPipeline,finite,execution_context,plan_protection,plan_exit
from ..expectancy import CostModel
from ..session import local_time,session_state
from .metrics import metrics
from ..risk import available_risk,PlanRiskPolicy
from ..setups import opening_range_retest
from ..ai import extract_features, MLTradeQualityModel, scope
from ..adaptive_exit import update_exit, VERSION as ADAPTIVE_EXIT_VERSION


@dataclass
class BacktestConfig:
    initial_capital: float=30000
    risk_per_trade: float=300
    daily_loss_limit: float=850
    correlated_risk_limit: float=300
    max_positions: int=1
    cooldown_bars: int=3
    daily_target: float=1200
    entry_cutoff: str="14:30"
    exit_at: str="15:10"
    trade_from: str=""
    learning_policies: dict=field(default_factory=dict)
    plan_policy: PlanRiskPolicy | None=None
    horizon_minutes: int=10
    reward_multiple: float=2.
    adaptive_exits: bool=False
    ml_artifact: dict | None=None
    min_stop: float=0.
    invalidation_buffer: float=0.


class BacktestEngine:
    def __init__(self,cfg=None):
        self.cfg=cfg or BacktestConfig()

    def run(self,df,cancel=None,progress=None):
        cfg=self.cfg
        policy=cfg.plan_policy
        pipeline=DecisionPipeline(cfg.learning_policies)
        if "symbol" not in df: df=df.assign(symbol="UNKNOWN")
        x=pipeline.features(df)
        cash=cfg.initial_capital; positions={}; pending={}; trades=[]; curve=[]; daily=[]; errors=[]
        day=None; baseline=cash; halted=False; cooldown={}; last_quotes={}; closed_count=0
        openings={}; records=x.to_dict("records") if not x.empty else []
        plan_candidates={}; option_history={}; consumed=set(); opportunities=[]
        if policy:
            for (session,symbol),frame in x.groupby(["session","symbol"]):
                for candidate in opening_range_retest(frame,frame.timestamp.max()+timedelta(minutes=1),all_candidates=True):
                    plan_candidates[(candidate["timestamp"],symbol)]=candidate
        ledger={"loss_spend":0.,"losses":0,"entries":0,"last_exit":None,"lock_reason":None}
        gross_realized=0.; equity_peak=cash; weekly_pnl=0.; week=None
        grouped={}
        for row in records: grouped.setdefault(row["timestamp"],[]).append(row)
        if not records or "option_quotes" not in x:
            return self._result([],[],[],[],["Contract-specific option candles, historical lot sizes and dated charges are required"],pipeline)
        if not any(r.get("option_quotes") for r in records):
            return self._result([],[],[],[],["No contract-specific option candles"],pipeline)
        for r in records:
            for q in r.get("option_quotes") or []:
                if not q.get("identity_verified") or any(k not in q for k in ("contract_id","expiry","strike","lot_size","tick_size","is_atm","charge_schedule")):
                    return self._result([],[],[],[],["Unverified contract identity or historical charges"],pipeline)

        def close_position(cid,q,stamp,reason,reference):
            nonlocal cash,closed_count,gross_realized
            p=positions[cid]
            # One adverse exchange tick is an explicit execution assumption, not a fabricated quote.
            tick=float(p["tick_size"])
            price=max(tick,round(math.floor((reference-tick+1e-10)/tick)*tick,8))
            fees=CostModel.historical(p,price,p["qty"],"sell",stamp)
            gross=(price-p["entry"])*p["qty"]
            pnl=gross-p["entry_charges"]["total"]-fees["total"]
            cash+=price*p["qty"]-fees["total"]
            trade={**p,"id":str(uuid.uuid4()),"exit":price,"exit_ts":stamp,"exit_premium":price,
                   "entry_premium":p["entry"],"quantity":p["qty"],"gross_pnl":gross,
                   "outcome_observed_at":stamp+timedelta(minutes=1),
                   "costs":p["entry_charges"]["total"]+fees["total"],"exit_charges":fees,"pnl":pnl,
                   "reason":reason,"quality":"verified","source":"historical_contract_candles",
                   "holding_minutes":(stamp-p["entry_ts"]).total_seconds()/60,
                   "fill_model":"next_bar_open_one_adverse_tick; stop_first_if_ambiguous"}
            trades.append(trade); closed_count+=1
            gross_realized+=gross
            if policy:
                ledger["loss_spend"]+=max(0.,-pnl)
                ledger["losses"]+=int(pnl<0)
                ledger["last_exit"]=pd.Timestamp(stamp).isoformat()
            cooldown[p["symbol"]]=pd.Timestamp(stamp).to_pydatetime()+timedelta(minutes=cfg.cooldown_bars)
            del positions[cid]

        for index,(stamp,rows) in enumerate(sorted(grouped.items())):
            if cancel and cancel(): raise InterruptedError("Cancelled")
            if progress and index%1000==0: progress(index,len(grouped))
            date=str(stamp.date())
            if cfg.trade_from and date<cfg.trade_from: continue
            if date!=day:
                if day is not None:
                    value=cash+sum(p["mark"]*p["qty"] for p in positions.values())
                    daily.append({"date":day,"pnl":value-baseline,"trades":closed_count})
                    weekly_pnl+=value-baseline
                if positions:
                    errors.append(f"{day}: position could not be closed from observed same-contract data")
                    break
                day=date; baseline=cash; halted=False; closed_count=0; pending={}
                if policy:
                    current_week=stamp.isocalendar()[:2]
                    if current_week!=week: weekly_pnl=0.; week=current_week
                    sticky="DRAWDOWN" if ledger["lock_reason"]=="DRAWDOWN" else ("WEEKLY_LOSS" if ledger["lock_reason"]=="WEEKLY_LOSS" and current_week==week else None)
                    ledger={"loss_spend":0.,"losses":0,"entries":0,"last_exit":None,"lock_reason":sticky}
                    gross_realized=0.; halted=bool(sticky)
            quotes={q["contract_id"]:q for r in rows for q in (r.get("option_quotes") or []) if q.get("contract_id")}
            last_quotes=quotes
            state=session_state(stamp,cutoff=cfg.entry_cutoff,exit_at=cfg.exit_at)
            for symbol,(signal,selected) in list(pending.items()):
                del pending[symbol]
                if state!="ENTRY_WINDOW" or halted or len(positions)>=cfg.max_positions: continue
                if policy and (positions or policy.entry_veto(ledger,stamp)): continue
                if any(p["symbol"]==symbol for p in positions.values()): continue
                q=quotes.get(selected["contract_id"])
                if not q or not finite(q.get("open")) or q["open"]<=0:
                    errors.append(f"{stamp}: next-bar quote missing for selected contract"); continue
                if any(str(q.get(k))!=str(selected.get(k)) for k in ("symbol","strike","expiry","lot_size","tick_size","option_type")):
                    errors.append(f"{stamp}: selected contract identity changed before entry"); continue
                if (stamp-pd.Timestamp(signal["timestamp"])).total_seconds()!=60: continue
                price=float(q["open"])+float(q["tick_size"]); lot=int(q["lot_size"])
                if policy:
                    if str(q["expiry"])[:10]<=date: continue
                    try:
                        signal=plan_protection(signal,q,selected.get("retest_quote"),price,cfg.reward_multiple,cfg.horizon_minutes,cfg.min_stop)
                    except ValueError as exc:
                        opportunities.append({"signal_id":signal["id"],"timestamp":stamp,"status":"REJECTED","reason":str(exc)})
                        continue
                open_risk=sum(p["risk_rupees"] for p in positions.values())
                same_risk=sum(p["risk_rupees"] for p in positions.values() if p["option_type"]==signal["option_type"])
                equity=cash+sum(p["mark"]*p["qty"] for p in positions.values())
                budget=available_risk(cfg.risk_per_trade,cfg.daily_loss_limit,equity-baseline,open_risk,cfg.correlated_risk_limit,same_risk)
                if policy: budget=min(policy.trade_risk,policy.remaining(ledger,open_risk))
                max_lots=max(0,min(int(cash//(price*lot)),int(max(budget,0)//(price*signal["stop_percent"]*lot))))
                if policy: max_lots=min(1,max_lots)
                filled=None
                for lots in range(max_lots,0,-1):
                    qty=lots*lot
                    try:
                        buy=CostModel.historical(q,price,qty,"buy",stamp)
                        exit_price=max(float(q["tick_size"]),price*(1-signal["stop_percent"])-float(q["tick_size"]))
                        sell=CostModel.historical(q,exit_price,qty,"sell",stamp)
                    except ValueError as exc:
                        errors.append(str(exc)); break
                    risk=(price-exit_price)*qty+buy["total"]+sell["total"]
                    debit=price*qty+buy["total"]
                    if risk<=budget and debit<=cash and (not policy or (debit<=policy.premium_limit and cash-debit>=policy.cash_reserve)):
                        filled=(qty,buy,risk); break
                if not filled: continue
                qty,buy,risk=filled
                if cfg.adaptive_exits: signal["exit_policy"]=ADAPTIVE_EXIT_VERSION
                feature_contract={**selected,"ask":price}
                entry_features=extract_features(signal.get("feature_row",{}),signal,feature_contract,stamp)
                model_signal={**signal,"symbol":symbol,"entry_features":entry_features}
                if cfg.ml_artifact and scope(model_signal)==cfg.ml_artifact["scope"]:
                    if MLTradeQualityModel(cfg.ml_artifact).predict(entry_features)<cfg.ml_artifact["threshold"]: continue
                contexts={**signal["agent_contexts"],"Option Selector":selected["option_context"],
                          "EV":"uncalibrated","Risk":"shared_portfolio" if positions else "one_position","Execution":execution_context(stamp)}
                if any(not pipeline.context_allowed(a,context) for a,context in contexts.items()): continue
                cash-=price*qty+buy["total"]
                positions[q["contract_id"]]={**q,"qty":qty,"entry":price,"entry_ts":stamp,"entry_charges":buy,
                    "stop":price*(1-signal["stop_percent"]),"target":price*(1+signal["target_percent"]),
                    "risk_rupees":risk,"mark":price,"setup":signal["setup"],"regime":signal["regime"],
                    "agent_contexts":contexts,"policy_versions":signal["policy_versions"],"mae":0,"mfe":0}
                positions[q["contract_id"]].update(entry_features=entry_features,
                    strategy_version=signal.get("strategy_version"),option_atr=signal.get("option_atr"))
                if policy:
                    positions[q["contract_id"]].update(stop=signal["stop_price"],target=signal["target_price"],
                        invalidation=signal["invalidation"],horizon_minutes=signal["horizon_minutes"],
                        invalidation_buffer=cfg.invalidation_buffer,
                        exit_policy=signal["exit_policy"],protection_evidence=signal["protection_evidence"],signal_id=signal["id"])
                    ledger["entries"]+=1
                    opportunities.append({"signal_id":signal["id"],"timestamp":stamp,"status":"FILLED",
                                          "contract_id":q["contract_id"],"risk_rupees":risk})
                for agent in ("EV","Risk","Execution"):
                    pipeline.stage(agent,symbol,"PASS" if agent!="EV" else "OBSERVATION","Historical paper simulation",contexts[agent])
            for cid,p in list(positions.items()):
                q=quotes.get(cid)
                if not q or not all(finite(q.get(k)) and q[k]>0 for k in ("open","high","low","close")):
                    errors.append(f"{stamp}: held contract data gap"); continue
                # Reject metadata drift even if a supplied data source reused a contract ID.
                if any(str(q.get(k))!=str(p.get(k)) for k in ("strike","expiry","lot_size","option_type")):
                    errors.append(f"{stamp}: contract identity changed"); continue
                p["mark"]=float(q["close"])
                p["mae"]=min(p["mae"],(q["low"]-p["entry"])*p["qty"])
                p["mfe"]=max(p["mfe"],(q["high"]-p["entry"])*p["qty"])
                if policy:
                    # Bar data cannot establish a two-second path. Stop wins intrabar
                    # ambiguity; structural/time exits use the later completed close.
                    underlying=next((r["close"] for r in rows if r["symbol"]==p["symbol"]),None)
                    completed=stamp+timedelta(minutes=1)
                    if halted: close_position(cid,q,stamp,"RISK_HALT",q["open"])
                    elif stamp.strftime("%H:%M")>=cfg.exit_at: close_position(cid,q,stamp,"SESSION_EXIT",q["open"])
                    elif q["low"]<=p["stop"]: close_position(cid,q,stamp,"STOP",min(p["stop"],q["open"]))
                    else:
                        if cfg.adaptive_exits:
                            exit_cost=CostModel.historical(p,q["close"],p["qty"],"sell",completed)["total"]
                            update_exit(p,float(q["close"]),completed,exit_cost,{"timestamp":str(stamp),"high":q["high"],"low":q["low"]})
                        reason=plan_exit(p,completed,bid=q["close"],underlying=underlying,close_start=cfg.exit_at)
                        if reason: close_position(cid,q,completed,reason,q["close"])
                        elif q["high"]>=p["target"]: close_position(cid,q,stamp,"TARGET",p["target"])
                elif state=="EXIT_ONLY": close_position(cid,q,stamp,"SESSION_EXIT",q["open"])
                elif q["low"]<=p["stop"]: close_position(cid,q,stamp,"STOP",min(p["stop"],q["open"]))
                elif q["high"]>=p["target"]: close_position(cid,q,stamp,"TARGET",p["target"])
            value=cash+sum(p["mark"]*p["qty"] for p in positions.values())
            if policy:
                try:
                    liquidation=value-sum(CostModel.historical(p,max(p["tick_size"],p["mark"]-p["tick_size"]),p["qty"],"sell",stamp)["total"]+p["tick_size"]*p["qty"] for p in positions.values())
                except ValueError as exc:
                    errors.append(str(exc)); halted=True; liquidation=None
                if liquidation is not None:
                    equity_peak=max(equity_peak,liquidation)
                    gross=gross_realized+sum((p["mark"]-p["tick_size"]-p["entry"])*p["qty"] for p in positions.values())
                    lock=("DAILY_LOSS" if liquidation-baseline<=-policy.loss_allocation else
                          "DRAWDOWN" if liquidation-equity_peak<=-policy.max_drawdown else
                          "WEEKLY_LOSS" if weekly_pnl+liquidation-baseline<=-policy.weekly_loss else
                          ("NET_TARGET" if policy.target_basis == "net" else "GROSS_TARGET") if policy.target_reached(gross, liquidation-baseline) else None)
                    if lock:
                        ledger["lock_reason"]=lock; halted=True; pending={}
                        for cid,p in list(positions.items()):
                            if cid in quotes: close_position(cid,quotes[cid],stamp,"RISK_HALT",quotes[cid]["close"])
                        value=cash+sum(p["mark"]*p["qty"] for p in positions.values())
            if value-baseline<=-cfg.daily_loss_limit:
                halted=True; pending={}
                for cid,p in list(positions.items()):
                    if cid in quotes: close_position(cid,quotes[cid],stamp,"DAILY_LOSS_LIMIT",quotes[cid]["close"])
                value=cash+sum(p["mark"]*p["qty"] for p in positions.values())
            curve.append({"timestamp":stamp,"value":value})
            for row in rows:
                for q in row.get("option_quotes") or []: option_history[(q["contract_id"],stamp.isoformat())]=q
            if state!="ENTRY_WINDOW" or halted: continue
            for row in rows:
                symbol=row["symbol"]
                if cooldown.get(symbol,stamp)>stamp or any(p["symbol"]==symbol for p in positions.values()): continue
                opening_key=(date,symbol)
                if "09:15"<=stamp.strftime("%H:%M")<"09:30":
                    openings.setdefault(opening_key,[]).append(row)
                opening=openings.get(opening_key,[])
                signal=(pipeline.plan_candidate(plan_candidates.get((stamp.isoformat(),symbol)),symbol) if policy else
                        pipeline.signal(row,max((r["high"] for r in opening),default=None),min((r["low"] for r in opening),default=None),len(opening)))
                if not signal: continue
                signal["feature_row"]=row
                if policy:
                    if signal["id"] in consumed: continue
                    consumed.add(signal["id"])
                    veto=policy.entry_veto(ledger,stamp+timedelta(minutes=1))
                    opportunities.append({**signal,"status":"REJECTED" if veto else "CANDIDATE","reason":veto})
                    if veto: continue
                selected=pipeline.option_candidates(signal,row.get("option_quotes") or [],cash,stamp,historical=True)
                for candidate in selected:
                    lot=candidate["lot_size"]; price=candidate["close"]+candidate["tick_size"]
                    try:
                        if policy:
                            if str(candidate["expiry"])[:10]<=date: continue
                            retest_quote=option_history.get((candidate["contract_id"],signal["retest_timestamp"]))
                            from ..indicators import atr as option_atr
                            previous_bars=[{**v,"timestamp":t} for (cid,t),v in option_history.items() if cid==candidate["contract_id"] and pd.Timestamp(t)<=pd.Timestamp(signal["retest_timestamp"])]
                            if len(previous_bars)>=14:
                                history=pd.DataFrame(previous_bars).sort_values("timestamp")
                                signal["option_atr"]=float(option_atr(history).iloc[-1])
                            signal=plan_protection(signal,candidate,retest_quote,price,cfg.reward_multiple,cfg.horizon_minutes,cfg.min_stop)
                            candidate={**candidate,"retest_quote":retest_quote}
                        buy=CostModel.historical(candidate,price,lot,"buy",stamp)
                        exit_price=max(candidate["tick_size"],price*(1-signal["stop_percent"])-candidate["tick_size"])
                        sell=CostModel.historical(candidate,exit_price,lot,"sell",stamp)
                    except ValueError as exc:
                        errors.append(str(exc)); continue
                    if price*lot+buy["total"]<=cash and (price-exit_price)*lot+buy["total"]+sell["total"]<=cfg.risk_per_trade:
                        pending[symbol]=(signal,candidate); break
        if positions and not errors and curve:
            stamp=curve[-1]["timestamp"]
            for cid,p in list(positions.items()):
                if cid in last_quotes: close_position(cid,last_quotes[cid],stamp,"DATA_END",last_quotes[cid]["close"])
            curve[-1]["value"]=cash+sum(p["mark"]*p["qty"] for p in positions.values())
        if day is not None:
            daily.append({"date":day,"pnl":cash+sum(p["mark"]*p["qty"] for p in positions.values())-baseline,"trades":closed_count})
        result=self._result(trades,curve,daily,list(positions.values()),errors,pipeline)
        if policy:
            result.update(opportunities=opportunities,loss_ledger=ledger,
                          strategy_version="orb-retest-v1",risk_policy=policy.describe(),
                          fidelity="preliminary_fixed_contract_minute",deployment_ready=False,
                          evidence_status="BASELINE_RESEARCH_NOT_VALIDATED_EDGE")
        return result

    def _result(self,trades,curve,daily,unresolved,errors,pipeline):
        values=[self.cfg.initial_capital,*[p["value"] for p in curve]]
        summary=metrics(trades,pd.Series(values),daily,self.cfg.daily_target)
        valid=not errors and not unresolved
        if not valid:
            summary["partial_realized_pnl"]=summary["total_pnl"]
            for key in ("total_pnl","average_daily_pnl","target_day_rate","profit_factor","expectancy","win_rate"):
                summary[key]=None
            summary["profit_factor_status"]="DATA_BLOCKED"
        return {"trades":trades,"equity":pd.Series(values),"curve":curve,"daily":daily,"metrics":summary,
                "unresolved":unresolved,"quality":"verified" if valid else "incomplete",
                "issues":list(dict.fromkeys(errors))[:50],"agent_counts":pipeline.counts}
