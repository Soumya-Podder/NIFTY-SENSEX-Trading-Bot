"""Dhan rolling candles -> fixed-strike intraday research, never verified net returns.

Expiry buckets are provisional identities, not exchange contract IDs. Today's sourced
lot sizes are explicit sizing scenarios; missing historical metadata is not invented.
"""
from collections import defaultdict
import math
import pandas as pd
from ..pipeline import DecisionPipeline, execution_context, plan_protection
from ..expectancy import CostModel
from ..ai import extract_features
from .data import _valid_bar
from .metrics import metrics
from .estimation import estimate_gap_exit
from ..risk import available_risk
from ..setups import opening_range_retest
from datetime import timedelta

FIELDS = ("open", "high", "low", "close", "volume", "oi", "strike", "spot")
OFFSETS = ("ATM", "ATM-4", "ATM-3", "ATM-2", "ATM-1", "ATM+1", "ATM+2", "ATM+3", "ATM+4")
ASSUMPTIONS = [
    "Research scenario, not verified historical net performance or broker fills.",
    "Actual strike is held across rolling offsets within one session and expiry bucket; actual expiry/security ID remains unverified.",
    "Rupee sizing uses today's Dhan-master nearest-expiry lot size, not an asserted historical lot size.",
    "Closed-bar signals enter at the next minute's observed open. Stops take priority when both barriers cross; gap stops use the worse open.",
    "No bid/ask history, fill-depth simulation, slippage or dated fees: gross results are optimistic; net P&L and charges are unavailable.",
    "Entries select from ATM +/-4; selected-strike recovery searches up to +/-10 on demand for entry and exit continuity. ATM is excluded at signal time; held strikes can pass through ATM. No missing prices are filled forward.",
    "Weekly nearest-expiry bucket is used when returned; monthly is tried only for an empty weekly response. Missing sessions are not inferred to be holidays.",
    "Base agent rules are frozen. Research outcomes are recorded but cannot promote learning policies. Shared attribution must not be summed across agents.",
]


def merge_series(book, rejected, atm, series, symbol, side, flag, offset, start, end, invalid=None, session_exit="15:10"):
    """Quarantine conflicting duplicate candles permanently, independent of fetch order."""
    stamps = series.get("timestamp", [])
    if any(len(series.get(k, [])) != len(stamps) for k in FIELDS):
        raise ValueError(f"{symbol} {side} {offset}: historical arrays have unequal lengths")
    accepted = 0
    for i, epoch in enumerate(stamps):
        stamp = pd.Timestamp(epoch, unit="s", tz="UTC").tz_convert("Asia/Kolkata")
        if not start <= str(stamp.date()) <= end: continue
        if not "09:15" <= stamp.strftime("%H:%M") <= session_exit: continue
        if stamp.second or stamp.microsecond: raise ValueError("Expected minute-start timestamps")
        raw = {k:series[k][i] for k in FIELDS}
        try:
            q = {k:float(v) for k,v in raw.items()}
            _valid_bar(q)
            if not all(math.isfinite(q[k]) and q[k] > 0 for k in ("strike", "spot")) or not math.isfinite(q["oi"]) or q["oi"] < 0:
                raise ValueError("Invalid observed strike, spot or open interest")
        except (ValueError,TypeError) as exc:
            if invalid is not None: invalid.append({"symbol":symbol,"side":side,"offset":offset,"timestamp":stamp.isoformat(),"values":raw,"reason":str(exc)})
            try:
                strike=float(raw["strike"])
                identity=f"rolling:{symbol}:{stamp.date()}:{flag}:1:{side}:{strike:g}"
                key=(stamp,symbol,identity); rejected.add(key); book.pop(key,None)
            except (ValueError,TypeError): pass
            continue
        identity = f"rolling:{symbol}:{stamp.date()}:{flag}:1:{side}:{q['strike']:g}"
        key = (stamp, symbol, identity)
        if key in rejected: continue
        existing = book.get(key)
        if existing and any(existing[k] != q[k] for k in FIELDS if k != "spot"):
            rejected.add(key); book.pop(key, None); continue
        q.update(contract_id=identity, symbol=symbol, option_type=side, expiry=None,
                 expiry_bucket=f"{flag}:1", identity_verified=False,
                 offsets=sorted(set((existing or {}).get("offsets", []) + [offset])))
        book[key] = q
        if offset == "ATM": atm[(stamp, symbol, side)].add(q["strike"])
        accepted += 1
    return accepted


class ResearchReplay:
    def __init__(self, config, settings, lots):
        self.config = config; self.settings = settings; self.lots = lots
        self.daily_limit=config.get("daily_loss_limit",settings.daily_loss_limit_rupees)
        self.correlated_limit=config.get("correlated_risk_limit",settings.max_correlated_risk_rupees)
        self.pipeline = DecisionPipeline(); self.cash = config["capital"]
        self.trades = []; self.daily = []; self.curve = []; self.gross_curve = []; self.unresolved = []
        self.settled_costs = 0.
        self.estimates=[]
        self.skipped_entries = []
        self.plan = config.get("strategy_version") == "orb-retest-v1"
        self.net = config.get("net_costs", False)
        self.stopped = False; self.coverage_incomplete = False; self.offset_switches = 0; self.skipped = 0

    def consume(self, frame, book, atm, cancel, recover=None):
        lookup = defaultdict(dict)
        for (stamp, symbol, identity), q in book.items(): lookup[(stamp, symbol)][identity] = q
        for day, session in frame.groupby(frame.timestamp.dt.strftime("%Y-%m-%d"), sort=True):
            if self.stopped: break
            positions = {}; pending = {}; opening = {}; cooldown = {}; realized = 0.; count = 0; baseline=self.cash
            plan_candidates = {}
            consumed = set()
            loss_spend=0.; losses=0; entries=0; last_exit=None
            if self.plan:
                for symbol, bars in session.groupby("symbol"):
                    for candidate in opening_range_retest(bars,bars.timestamp.max()+timedelta(minutes=1),all_candidates=True):
                        plan_candidates[(pd.Timestamp(candidate["timestamp"]),symbol)] = candidate
            rows = {(r.timestamp, r.symbol): r._asdict() for r in session.itertuples(index=False)}
            stamps = pd.date_range(f"{day} 09:15", f"{day} {self.settings.session_exit}", freq="min", tz="Asia/Kolkata")
            def close(symbol, q, price, stamp, reason):
                nonlocal realized, count, loss_spend, losses, last_exit
                p = positions.pop(symbol); pnl = (price - p["entry_premium"]) * p["quantity"]
                costs = CostModel.estimate_round_trip(p["entry_premium"], price, p["quantity"]) if self.net else None
                self.settled_costs += costs or 0.
                net_pnl = round(pnl - costs, 2) if self.net else None
                self.cash += price * p["quantity"] + p.get("cost_reserve", 0) - (costs or 0)
                trade_pnl = net_pnl if self.net else pnl
                realized += trade_pnl; count += 1
                loss_spend+=max(0.,-trade_pnl); losses+=int(trade_pnl<0); last_exit=stamp
                self.trades.append({**p, "exit_time":stamp.isoformat(), "exit_ts":stamp.isoformat(),
                    "outcome_observed_at":(stamp+timedelta(minutes=1)).isoformat(),
                    "exit_premium":price,
                    "gross_pnl":pnl, "premium_points":price-p["entry_premium"], "pnl":net_pnl,
                    "costs":costs, "reason":reason, "exit_offsets":q["offsets"],
                    "quality":"research_net" if self.net else "research",
                    "partial":False, "pnl_basis":"net" if self.net else "current_lot_gross_scenario"})
                cooldown[symbol] = stamp + timedelta(minutes=self.settings.exit_cooldown_minutes if self.plan else 3)
            for stamp in stamps:
                if cancel(): raise InterruptedError("Cancelled")
                hhmm = stamp.strftime("%H:%M")
                # Exits use only this minute of the held actual strike, never its old offset.
                for symbol, p in list(positions.items()):
                    q = lookup[(stamp, symbol)].get(p["contract_id"])
                    if q is None and recover:
                        recover(stamp, symbol, p["option_type"])
                        # Recovery can quarantine conflicts as well as add observed candles.
                        for key in list(lookup):
                            if key[1] == symbol and str(key[0].date()) == day: lookup.pop(key)
                        for (time, sym, identity), candle in book.items():
                            if sym == symbol and str(time.date()) == day: lookup[(time, sym)][identity] = candle
                        q = lookup[(stamp, symbol)].get(p["contract_id"])
                    if q is None:
                        if self.config.get("estimate_missing_exits"):
                            previous=lookup[(stamp-pd.Timedelta(minutes=1),symbol)].get(p["contract_id"])
                            prior={**previous,"observed_at":(stamp-pd.Timedelta(minutes=1)).isoformat()} if previous else None
                            estimated=estimate_gap_exit(p,stamp,prior,self.config.get("estimate_haircut",.05))
                            if estimated:
                                audit={**estimated,"symbol":symbol,"contract_id":p["contract_id"],"trade_id":p["id"]}
                                p["estimated_exit"]=audit
                                self.estimates.append(audit)
                                close(symbol,{"offsets":[]},estimated["price"],stamp,"ESTIMATED_DATA_GAP_EXIT")
                                continue
                        self.unresolved.extend({**held, "missing_at":stamp.isoformat(), "reason":"Portfolio replay stopped at a held-strike data gap"} for held in positions.values())
                        self.stopped = True; return
                    if not set(p["last_offsets"]) & set(q["offsets"]): self.offset_switches += 1
                    p["last_offsets"] = q["offsets"]; p["mark"] = q["close"]
                    if hhmm >= self.settings.session_exit: close(symbol, q, q["open"], stamp, "SESSION_EXIT")
                    elif q["open"] <= p["stop"]: close(symbol, q, q["open"], stamp, "STOP_GAP")
                    elif self.plan and (stamp-pd.Timestamp(p["entry_time"])).total_seconds()>=p["horizon_minutes"]*60:
                        close(symbol,q,q["open"],stamp,"TIME_EXIT")
                    elif self.plan and rows.get((stamp-timedelta(minutes=1),symbol)) and (
                        (rows[(stamp-timedelta(minutes=1),symbol)]["close"]<=p["invalidation"] if p["option_type"]=="CALL" else
                        rows[(stamp-timedelta(minutes=1),symbol)]["close"]>=p["invalidation"])):
                        close(symbol,q,q["open"],stamp,"STRUCTURAL_FAILURE")
                    elif q["open"] >= p["target"]: close(symbol, q, p["target"], stamp, "TARGET")
                for symbol, planned in list(pending.items()):
                    pending.pop(symbol)
                    if hhmm >= self.settings.entry_cutoff: continue
                    if self.plan and (positions or entries>=self.settings.max_entry_attempts or
                        losses>=self.settings.max_losing_trades or (last_exit is not None and stamp<last_exit+timedelta(minutes=self.settings.exit_cooldown_minutes))): continue
                    q = lookup[(stamp, symbol)].get(planned["contract_id"])
                    if q is None and recover:
                        recover(stamp, symbol, planned["signal"]["option_type"])
                        for key in list(lookup):
                            if key[1] == symbol and str(key[0].date()) == day: lookup.pop(key)
                        for (time, sym, identity), candle in book.items():
                            if sym == symbol and str(time.date()) == day: lookup[(time, sym)][identity] = candle
                        q = lookup[(stamp, symbol)].get(planned["contract_id"])
                    if not q or stamp != planned["next_time"]:
                        self.skipped += 1
                        self.coverage_incomplete = True
                        self.skipped_entries.append({**planned["signal"],"contract_id":planned["contract_id"],
                            "attempted_entry_time":stamp.isoformat(),"reason":"Selected strike has no trustworthy next-minute open after available recovery"})
                        self.pipeline.stage("Execution", symbol, "REJECTED", "Next-minute fixed-strike open unavailable", "missing_open")
                        continue
                    signal = planned["signal"]; entry = q["open"]; lot = self.lots[symbol]["lot_size"]
                    if self.plan:
                        retest=lookup[(pd.Timestamp(signal["retest_timestamp"]),symbol)].get(q["contract_id"])
                        try:
                            contract={**q,"lot_size":lot,"tick_size":self.lots[symbol]["tick_size"]}
                            signal=plan_protection(signal,contract,{**retest,"lot_size":lot} if retest else None,entry,
                                min_stop=self.config.get("min_stop", 0.),horizon_minutes=self.config.get("horizon_minutes", 10))
                        except ValueError as exc:
                            self.skipped_entries.append({**signal,"contract_id":q["contract_id"],"reason":str(exc)})
                            continue
                    risk_unit = entry * signal["stop_percent"]
                    used_risk = sum(p["risk"] for p in positions.values())
                    correlated = sum(p["risk"] for p in positions.values() if p["option_type"] == signal["option_type"])
                    open_equity=self.cash+sum(lookup[(stamp,s)][p["contract_id"]]["open"]*p["quantity"] for s,p in positions.items())
                    budget = available_risk(self.config["risk_per_trade"],self.daily_limit,open_equity-baseline,used_risk,self.correlated_limit,correlated)
                    if self.plan:
                        allocation=self.daily_limit*self.settings.planned_daily_loss_rupees/self.settings.daily_loss_limit_rupees
                        budget=min(budget,max(0.,allocation-loss_spend-used_risk))
                    qty = int(min(self.cash / (entry*lot), budget / (risk_unit*lot))) * lot
                    if self.plan: qty=min(qty,lot)
                    reserve=0.
                    if self.net:
                        while qty>=lot:
                            reserve=CostModel.estimate_round_trip(entry,entry-risk_unit,qty)
                            if entry*qty+reserve<=self.cash and risk_unit*qty+reserve<=budget:
                                break
                            qty-=lot
                        if qty<lot: reserve=0.
                    if self.plan and (entry*qty>self.config["capital"]*self.settings.max_premium_commitment_rupees/self.settings.paper_capital or
                        self.cash-entry*qty-reserve<self.config["capital"]*self.settings.cash_reserve_rupees/self.settings.paper_capital): qty=0
                    allowed = qty >= lot and len(positions) < self.settings.max_open_positions
                    self.pipeline.stage("Risk", symbol, "PASS" if allowed else "REJECTED", "Shared cash and stop-risk limits with estimated cost reserve" if self.net else "Shared cash and gross stop-risk limits (fees unknown)", "research_estimated_net_risk" if self.net else "research_gross_risk")
                    if not allowed: continue
                    self.cash -= entry*qty+reserve
                    entries+=1
                    feats = extract_features(
                        signal.get("signal_features", {}),
                        signal,
                        {**q, "ask": entry},
                        stamp
                    )
                    p = {**signal, "id":signal["id"], "contract_id":q["contract_id"], "expiry":None,
                         "strike":q["strike"], "expiry_bucket":q["expiry_bucket"], "identity_verified":False,
                         "entry_time":stamp.isoformat(), "entry_ts":stamp.isoformat(),
                         "strategy_version":self.config.get("strategy_version") or "orb-retest-v1",
                         "exit_policy":"orb-retest-v1" if self.plan else "fixed_target_stop",
                         "entry_features":feats,
                         "entry_premium":entry, "quantity":qty, "cost_reserve":reserve,
                         "lot_scenario":self.lots[symbol], "stop":entry-risk_unit,
                         "sizing_audit":{"cash_before":self.cash+entry*qty+reserve,"premium_committed":entry*qty,
                            "risk_budget":budget,"stop_risk":risk_unit*qty,"correlated_risk_before":correlated,
                            "daily_realized_before":realized,"charges_included":bool(self.net),"estimated_cost_reserve":reserve},
                         "target":entry*(1+signal["target_percent"]), "risk":risk_unit*qty+reserve,
                         "mark":q["close"], "last_offsets":q["offsets"], "entry_offsets":q["offsets"],
                         "agent_contexts":{**signal["agent_contexts"], "Option Selector":"rolling_non_atm_budget",
                            "EV":"research_net_ev", "Risk":"research_net_risk", "Execution":execution_context(stamp)}}
                    positions[symbol] = p
                    self.pipeline.stage("Execution", symbol, "PASS", "Next-minute observed open; optimistic fill assumption", execution_context(stamp))
                # Evaluate intrabar barriers only AFTER all opening fills: later proceeds
                # must not fund another index's entry at this same minute's open.
                for symbol, p in list(positions.items()):
                    q = lookup[(stamp, symbol)][p["contract_id"]]
                    if q["low"] <= p["stop"]: close(symbol, q, p["stop"], stamp, "STOP")
                    elif q["high"] >= p["target"]: close(symbol, q, p["target"], stamp, "TARGET")
                equity = self.cash + sum(p["mark"]*p["quantity"] for p in positions.values())
                self.curve.append({"timestamp":stamp.isoformat(), "value":equity})
                self.gross_curve.append({"timestamp":stamp.isoformat(), "value":equity+self.settled_costs+sum(p.get("cost_reserve",0) for p in positions.values())})
                for symbol in self.config["symbols"]:
                    row = rows.get((stamp, symbol))
                    if not row: continue
                    opening.setdefault(symbol, []).append(row)
                    bars = opening[symbol]
                    if hhmm >= self.settings.entry_cutoff or symbol in positions or stamp < cooldown.get(symbol, stamp): continue
                    if realized <= -self.daily_limit: continue
                    first = [r for r in bars if r["timestamp"].strftime("%H:%M") < "09:30"]
                    if len(first) != 15: continue
                    signal = (self.pipeline.plan_candidate(plan_candidates.get((stamp,symbol)),symbol) if self.plan else
                              self.pipeline.signal(row, max(r["high"] for r in first), min(r["low"] for r in first), len(bars)))
                    if not signal: continue
                    if signal["id"] in consumed: continue
                    consumed.add(signal["id"])
                    signal["signal_features"] = {k:row.get(k) for k in ("open","high","low","close","volume","ema9","ema21","ema50","vwap","atr","rsi","adx","relative_volume")}
                    signal["signal_features"]["timestamp"] = str(stamp.isoformat())
                    if row.get("atr") and row.get("atr") > 0:
                        if row.get("vwap") is not None:
                            signal["signal_features"]["vwap_distance_atr"] = (row.get("close", 0) - row.get("vwap", 0)) / row["atr"]
                        if row.get("ema9") is not None and row.get("ema21") is not None:
                            signal["signal_features"]["ema_slope_atr"] = (row.get("ema9", 0) - row.get("ema21", 0)) / row["atr"]
                    signal["opening_range"] = {"high":max(r["high"] for r in first),"low":min(r["low"] for r in first),"bars":len(first)}
                    atm_strikes = atm.get((stamp, symbol, signal["option_type"]), set())
                    candidates = [q for q in lookup[(stamp, symbol)].values() if q["option_type"] == signal["option_type"]
                        and any(offset in OFFSETS for offset in q["offsets"])
                        and len(atm_strikes) == 1 and q["strike"] not in atm_strikes and q["oi"] > 0 and q["volume"] > 0
                        and q["close"]*self.lots[symbol]["lot_size"] <= self.cash]
                    candidates.sort(key=lambda q:(-q["oi"], abs(q["strike"]-row["close"])))
                    self.pipeline.stage("Option Selector", symbol, "PASS" if candidates else "REJECTED", "Observed non-ATM strike and current-lot budget", "rolling_non_atm_budget")
                    if not candidates: continue
                    signal["selection_audit"] = {"candidate_count":len(candidates), "ranking":"Highest observed OI, then distance to underlying close", "selected_closed_candle":candidates[0]}
                    self.pipeline.stage("EV", symbol, "OBSERVATION", "Gross research only; net expectancy unverified", "research_no_verified_net_ev")
                    pending[symbol] = {"contract_id":candidates[0]["contract_id"], "signal":signal, "next_time":stamp+pd.Timedelta(minutes=1)}
            self.daily.append({
                "date":day,
                "pnl":realized if self.net else None,
                "gross_pnl":realized + sum(t.get("costs", 0) for t in self.trades if t["exit_time"][:10] == day) if self.net else realized,
                "trades":count
            })

    def result(self, coverage):
        result=self._result(coverage)
        if self.config.get("estimate_missing_exits"):
            # The entire account path is scenario evidence, including later trades
            # whose sizing can depend on an estimated exit. Never train on this run.
            result.update(quality="estimated_scenario",status="scenario_partial" if self.stopped or self.coverage_incomplete else "scenario_complete",
                          learning_eligible=False,source="dhan_estimated_exit_scenario_v1",
                          estimation={"method":"previous_observation_exit_v1","haircut":self.config.get("estimate_haircut",.05),
                                      "estimated_exits":len(self.estimates),"affected_trades":len(self.estimates),
                                      "events":self.estimates,"missing_entries_estimated":False,
                                      "entire_account_is_scenario":True})
            for trade in result["trades"]: trade.update(quality="estimated_scenario",learning_eligible=False)
            result["assumptions"].append("Exploratory scenario: missing held prices may cause liquidation at the preceding observed price less the configured haircut. No new entries, OI, volume, expiry identity or entire missing sessions are invented. The haircut is not a worst-case loss bound.")
        return result

    def _result(self, coverage):
        gross_trades = [{**t, "pnl":t["gross_pnl"], "costs":0} for t in self.trades]
        gross_days = [{**d, "pnl":d["gross_pnl"]} for d in self.daily]
        eval_trades = self.trades if self.net else gross_trades
        eval_days = self.daily if self.net else gross_days
        target=self.config.get("monthly_target",self.settings.monthly_profit_target)
        calculated = metrics(eval_trades, [self.config["capital"]]+[p["value"] for p in self.curve], eval_days,target)
        gross_metrics = metrics(gross_trades,[self.config["capital"]]+[p["value"] for p in self.gross_curve],gross_days,target)
        gross = calculated["total_pnl"] if not self.net else sum(t.get("gross_pnl", 0) for t in self.trades)
        net_total = calculated["total_pnl"] if self.net else None
        total_costs = sum(t.get("costs", 0) for t in self.trades) if self.net else None
        incomplete = self.stopped or self.coverage_incomplete
        calculated.update(
            total_pnl=None if (incomplete or not self.net) else net_total,
            total_charges=None if (incomplete or not self.net) else total_costs,
            target_month_rate=None,
            gross_pnl=None if incomplete else gross,
            partial_realized_gross_pnl=gross,
            average_daily_pnl=None if (incomplete or not self.net) else calculated["average_daily_pnl"],
            gross_average_daily_pnl=calculated["average_daily_pnl"] if not self.net else (sum(d.get("gross_pnl", 0) for d in self.daily)/len(self.daily) if self.daily else None)
        )
        if incomplete:
            for key in ("profit_factor", "win_rate", "expectancy", "max_drawdown", "max_drawdown_pct", "gross_average_daily_pnl", "average_monthly_pnl"):
                calculated[key] = None
            calculated["profit_factor_status"] = "INCOMPLETE"
        return {"status":"research_partial" if incomplete else "research_complete",
            "quality":"research_net" if self.net else "research",
            "replay_version":"orb-retest-rolling-v1" if self.plan else "rolling-research-v3",
            "strategy_version":self.config.get("strategy_version"),
            "fidelity":"minute_candle_current_lot_net_scenario" if self.net else "minute_candle_current_lot_gross_scenario",
            "source":"dhan_reconstructed_rolling",
            "pnl_basis":"net" if self.net else "current_lot_gross_scenario",
            "metrics":calculated,
            "trades":self.trades, "curve":self.curve, "gross_curve":self.gross_curve,
            "gross_metrics":gross_metrics if not incomplete else {}, "daily":self.daily, "unresolved":self.unresolved,
            "skipped_entries":self.skipped_entries,
            "coverage":coverage, "agent_counts":self.pipeline.counts, "assumptions":[a for a in ASSUMPTIONS if not (self.net and "net P&L and charges are unavailable" in a)] + ([
                "ORB retest entry and structural option stop use shared strategy functions; one lot, three entry attempts, two losing trades and global exit cooldown constrain the scenario.",
                "This estimates the baseline's net candle outcome with standard Indian options transaction charges (brokerage, STT, turnover, GST, stamp duty). Risk admission uses net risk accounting." if self.net else
                "This estimates the baseline's gross candle outcome. Missing historical fees, expiry-day exclusions, Greeks, validated EV, weekly/drawdown review locks and executable depth prevent full paper-policy parity. Risk admission uses gross stop risk only.",
                "Current tick size and lot size are sourced scenarios. Intrabar stop/target exits are minute-bucket timestamps, not measured execution times."
            ] if self.plan else []),
            "reconstruction":{"held_offset_switches":self.offset_switches,"missing_entry_opens":self.skipped},
            "issues":["Net current-lot scenario with estimated Dhan transaction costs in ₹." if self.net else "Gross current-lot scenario only. Historical expiry identity, lot-size history, bid/ask and dated charges are unavailable. Net P&L is not calculated."] + (["Coverage is incomplete: headline performance is withheld; completed trades are partial evidence only."] if incomplete else [])}


def dhan_plan_research(gateway,config,progress,cancel):
    """Audit the real baseline without laundering rolling offsets into contracts."""
    pipeline=DecisionPipeline(); opportunities=[]; coverage=[]; daily={}
    start=pd.Timestamp(config["from"]); end=pd.Timestamp(config["to"])+timedelta(days=1)
    frames=[]; total=max(1,math.ceil((end-start).days/29)*len(config["symbols"])); done=0
    for symbol in config["symbols"]:
        cursor=start
        while cursor<end:
            if cancel(): raise InterruptedError("Cancelled")
            stop=min(cursor+timedelta(days=29),end)
            progress(f"Plan baseline: sourced {symbol} candles {cursor.date()} to {stop.date()}",done,total)
            frame=gateway.candles(symbol,str(cursor.date()),str(stop.date()),cache_seconds=-1,cancel=cancel)
            if not frame.empty: frames.append(frame)
            coverage.append({"symbol":symbol,"probe_from":str(cursor.date()),"probe_to":str(stop.date()),
                             "candles":len(frame),"api_access":"observed" if len(frame) else "empty",
                             "note":"End-exclusive source range; exchange calendar not verified"})
            done+=1; cursor=stop
    if frames:
        features=pipeline.features(pd.concat(frames,ignore_index=True))
        for (session,symbol),frame in features.groupby(["session","symbol"]):
            if cancel(): raise InterruptedError("Cancelled")
            daily.setdefault(session,{"date":session,"pnl":None,"gross_pnl":None,"trades":None,"candidates":0})
            for candidate in opening_range_retest(frame,frame.timestamp.max()+timedelta(minutes=1),all_candidates=True):
                if candidate["available_at"][11:16]>="14:30": continue
                signal=pipeline.plan_candidate(candidate,symbol)
                if signal:
                    pipeline.stage("Option Selector",symbol,"REJECTED",
                                   "Exact historical contract identity and dated option metadata unavailable",
                                   "blocked_historical_identity")
                    opportunities.append({**signal,"status":"BLOCKED_DATA",
                        "reason":"Historical exact expiry/security ID, dated lot size and charges are not supplied by rolling option candles"})
                    daily[session]["candidates"]+=1
    return {"strategy_version":"orb-retest-v1","replay_version":"orb-retest-v1",
            "status":"data_blocked","quality":"incomplete","source":"dhan_index_candles",
            "fidelity":"underlying_candidate_audit","deployment_ready":False,
            "evidence_status":"BLOCKED_HISTORICAL_CONTRACT_METADATA_AND_FEES",
            "trades":[],"curve":[],"daily":list(daily.values()),"opportunities":opportunities,
            "coverage":coverage,"agent_counts":pipeline.counts,
            "metrics":{"total_pnl":None,"profit_factor":None,"profit_factor_status":"DATA_BLOCKED",
                       "expectancy":None,"win_rate":None,"average_daily_pnl":None,"target_day_rate":None,
                       "candidate_count":len(opportunities)},
            "issues":["Plan candidates were evaluated from actual index candles; executable historical trades cannot be established from rolling-option identity alone.",
                      "No trades/P&L were invented. Use a sourced fixed-contract dataset with dated fees for the preliminary minute replay.",
                      "Calendar/events, Greeks scenarios, quote-level execution and out-of-sample edge remain unvalidated."],
            "assumptions":["Price-only ORB retest baseline; exact completed-bar availability; no index-volume proxy.",
                           "Missing later bars do not erase earlier candidates; no candles are interpolated."]}


def dhan_research(gateway, config, progress, cancel, settings):
    start = pd.Timestamp(config["from"]); end = pd.Timestamp(config["to"])
    chunks = []; cursor = start
    while cursor <= end:
        last = min(cursor+pd.Timedelta(days=28), end)
        chunks.append((str(cursor.date()), str(last.date())))
        cursor = last+pd.Timedelta(days=1)
    underlyings = {u["symbol"]:u for u in gateway.underlyings()}
    lots = {}; frames = []; coverage = []
    for symbol in config["symbols"]:
        contracts = gateway.contracts(symbol)
        if not contracts: raise ValueError(f"No sourced current lot-size scenario for {symbol}")
        nearest = min(c["expiry"] for c in contracts)
        sizes = {c["lot_size"] for c in contracts if c["expiry"] == nearest}
        if len(sizes) != 1: raise ValueError(f"Ambiguous current lot size for {symbol}")
        lots[symbol] = {"lot_size":sizes.pop(), "source":"dhan_security_master", "expiry":nearest,
                        "observed_on":contracts[0]["metadata_observed_on"], "historical_verified":False}
        ticks={c["tick_size"] for c in contracts if c["expiry"]==nearest and c.get("tick_size")}
        if config.get("strategy_version")=="orb-retest-v1":
            if len(ticks)!=1: raise ValueError(f"Ambiguous current tick-size scenario for {symbol}")
            lots[symbol]["tick_size"]=ticks.pop()
        for a, b in chunks:
            if cancel(): raise InterruptedError("Cancelled")
            progress(f"Fetching {symbol} index candles {a} to {b}", 0, 1)
            frame = gateway.candles(symbol, a, str((pd.Timestamp(b)+pd.Timedelta(days=1)).date()), cache_seconds=-1, cancel=cancel)
            frame = frame[(frame.timestamp.dt.strftime("%Y-%m-%d") >= a) & (frame.timestamp.dt.strftime("%Y-%m-%d") <= b)] if not frame.empty else frame
            if not frame.empty: frames.append(frame)
    if not frames: raise ValueError("Dhan returned no index candles in the selected range")
    features = DecisionPipeline.features(pd.concat(frames, ignore_index=True).drop_duplicates(["timestamp", "symbol"]))
    replay = ResearchReplay({**config, "net_costs": True}, settings, lots)
    any_options = False
    total = len(chunks)*len(config["symbols"])*len(OFFSETS)*2; completed = 0
    for a, b in chunks:
        book = {}; rejected = set(); atm = defaultdict(set); invalid = []
        for symbol in config["symbols"]:
            segment = features[(features.symbol == symbol) & features.session.between(a, b)]
            if segment.empty:
                if len(pd.bdate_range(a,b)): replay.coverage_incomplete = True
                coverage.append({"symbol":symbol,"probe_from":a,"probe_to":b,"candles":0,"api_access":"no_observed_index_sessions",
                    "observed_sessions":0,"lot_scenario":lots[symbol],"note":"No index candles returned; no option requests or invented sessions. Exchange calendar not verified."})
                continue
            under = underlyings[symbol]; received = 0; selected_flag = None
            for flag in ("WEEK", "MONTH"):
                flag_count = 0
                for side in ("CALL", "PUT"):
                    for offset in OFFSETS:
                        if cancel(): raise InterruptedError("Cancelled")
                        progress(f"Reconstructing {symbol} {a}–{b}: {flag} {side} {offset}", completed, total)
                        raw = gateway.call(gateway.client.expired_options_data, under["security_id"], under["exchange_segment"],
                            "OPTIDX", flag, 1, offset, side, list(FIELDS), a,
                            str((pd.Timestamp(b)+pd.Timedelta(days=1)).date()), 1, cache_seconds=-1, cancel=cancel)
                        series = raw.get("ce" if side == "CALL" else "pe") or {}
                        flag_count += merge_series(book, rejected, atm, series, symbol, side, flag, offset, a, b, invalid, settings.session_exit)
                        completed += 1
                if flag_count:
                    received += flag_count; selected_flag = flag; break
            missing_index = 0; missing_atm = 0
            for day, observed in segment.groupby("session"):
                expected = pd.date_range(f"{day} 09:15", f"{day} {settings.session_exit}", freq="min", tz="Asia/Kolkata")
                missing_index += int((~expected.isin(observed.timestamp)).sum())
                missing_atm += sum(len(atm.get((t,symbol,side),set())) != 1 for t in expected for side in ("CALL","PUT"))
            any_options = any_options or bool(received)
            if not received or segment.empty or missing_index or missing_atm or any(k[1] == symbol for k in rejected):
                replay.coverage_incomplete = True
            coverage.append({"symbol":symbol, "probe_from":a, "probe_to":b, "candles":received,
                "api_access":"success" if received else "no_data", "expiry_cycle":selected_flag,
                "conflicting_candles":sum(k[1] == symbol for k in rejected), "lot_scenario":lots[symbol],
                "invalid_candles":sum(v["symbol"]==symbol for v in invalid),"invalid_candle_examples":[v for v in invalid if v["symbol"]==symbol][:20],
                "underlying_candles":len(segment), "observed_sessions":segment.session.nunique(),
                "missing_index_minutes":missing_index,"missing_or_ambiguous_atm_minutes_by_side":missing_atm,
                "option_sessions":len({str(k[0].date()) for k in book if k[1] == symbol}), "offsets":list(OFFSETS)})
        recovered = set()
        def recover(stamp, symbol, side):
            day = str(stamp.date()); key = (day,symbol,side)
            if key in recovered: return
            recovered.add(key)
            evidence = next(c for c in coverage if c["symbol"] == symbol and c["probe_from"] == a)
            flag = evidence["expiry_cycle"]
            if not flag: return
            under = underlyings[symbol]
            for distance in range(4,11):
                for sign in ("-", "+"):
                    if cancel(): raise InterruptedError("Cancelled")
                    offset = f"ATM{sign}{distance}"
                    progress(f"Recovering held {symbol} {side} strike: {day} {offset}", completed, total)
                    try:
                        raw = gateway.call(gateway.client.expired_options_data, under["security_id"], under["exchange_segment"],
                            "OPTIDX", flag, 1, offset, side, list(FIELDS), day,
                            str((stamp+pd.Timedelta(days=1)).date()), 1, cache_seconds=-1, cancel=cancel)
                    except ValueError as exc:
                        if "Local historical candles missing" not in str(exc): raise
                        evidence.setdefault("unavailable_recovery_offsets",[]).append({"date":day,"side":side,"offset":offset})
                        continue
                    evidence["candles"] += merge_series(book, rejected, atm, raw.get("ce" if side == "CALL" else "pe") or {}, symbol, side, flag, offset, day, day, invalid, settings.session_exit)
            evidence.setdefault("recovery_sessions",[]).append({"date":day,"side":side,"offset_limit":10})
            evidence["conflicting_candles"] = sum(k[1] == symbol for k in rejected)
            evidence["invalid_candles"] = sum(v["symbol"]==symbol for v in invalid)
            evidence["invalid_candle_examples"] = [v for v in invalid if v["symbol"]==symbol][:20]
            if evidence["conflicting_candles"]: replay.coverage_incomplete = True
        segment = features[features.session.between(a, b)]
        replay.consume(segment, book, atm, cancel, recover)
        if replay.stopped: break
    result = replay.result(coverage)
    if not any_options:
        result.update(status="data_blocked", quality="incomplete")
        result["metrics"]["gross_pnl"] = None
    return result
