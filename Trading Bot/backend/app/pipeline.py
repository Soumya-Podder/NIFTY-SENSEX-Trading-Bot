"""Shared decision stages for historical replay and live-data paper execution."""
import hashlib
import math
import pandas as pd
from .indicators import add_features
from .regime import RegimeEngine
from .setups import SetupEngine, opening_range_retest
from .telemetry.decision_trace import event, AGENT_ORDER
from .session import local_time


def execution_context(timestamp):
    return f"entry_hour_{local_time(timestamp).hour:02d}"


def finite(value):
    try: return math.isfinite(float(value))
    except (TypeError,ValueError): return False


def plan_protection(signal, contract, retest_quote, entry_price, reward_multiple=2., horizon_minutes=10):
    """Freeze an observed option-structure stop, never adjust it to fit risk."""
    if reward_multiple < 2 or horizon_minutes not in (3, 5, 10, 20):
        raise ValueError("Unsupported frozen protection configuration")
    if not retest_quote or retest_quote.get("contract_id") != contract.get("contract_id"):
        raise ValueError("Selected contract retest candle is unavailable")
    for key in ("expiry", "strike", "lot_size", "option_type"):
        if retest_quote.get(key) != contract.get(key):
            raise ValueError("Retest contract identity changed")
    tick = contract.get("tick_size")
    low = retest_quote.get("low")
    if not all(finite(v) and v > 0 for v in (tick, low, entry_price)):
        raise ValueError("Invalid observed protection inputs")
    stop = round(math.floor((low - tick + 1e-10) / tick) * tick, 8)
    if not 0 < stop < entry_price:
        raise ValueError("Structural option stop is not below the proposed entry")
    target = round(math.ceil((entry_price + reward_multiple * (entry_price - stop) - 1e-10) / tick) * tick, 8)
    return {**signal, "stop_price": stop, "target_price": target,
            "stop_percent": (entry_price - stop) / entry_price,
            "target_percent": (target - entry_price) / entry_price,
            "horizon_minutes": horizon_minutes, "exit_policy": "structural_stop_target_time_v1",
            "protection_evidence": {"contract_id": contract["contract_id"],
                                    "retest_timestamp": signal["retest_timestamp"],
                                    "observed_low": low, "tick_size": tick,
                                    "reward_multiple": reward_multiple}}


def plan_exit(position, now, *, bid=None, underlying=None, halted=False, close_start="15:05"):
    """Shared ordered exit policy; the execution adapter supplies only observed values."""
    if halted: return "RISK_HALT"
    if finite(bid) and bid > 0 and bid <= position["stop"]: return "STOP"
    invalidation = position.get("invalidation")
    if finite(underlying) and finite(invalidation):
        if (underlying <= invalidation if position["option_type"] == "CALL" else underlying >= invalidation):
            return "STRUCTURAL_FAILURE"
    if local_time(now).strftime("%H:%M") >= close_start: return "SESSION_EXIT"
    underlying_target=position.get("underlying_target")
    if finite(underlying) and finite(underlying_target):
        if underlying>=underlying_target if position["option_type"]=="CALL" else underlying<=underlying_target:
            return "UNDERLYING_TARGET"
    horizon = position.get("horizon_minutes")
    if horizon and (local_time(now) - local_time(position["entry_ts"])).total_seconds() >= horizon * 60:
        return "TIME_EXIT"
    if finite(bid) and bid >= position["target"]: return "TARGET"
    return None


class DecisionPipeline:
    def __init__(self,policies=None,publish=None):
        self.policies=policies or {}; self.publish=publish or (lambda e:None)
        self.regime=RegimeEngine(); self.setup=SetupEngine()
        self.counts={a:{"candidates":0,"passed":0,"rejected":0} for a in AGENT_ORDER}

    def stage(self,agent,symbol,status,summary,context="",**details):
        policy=self.policies.get(agent,{})
        if status in {"PASS","OBSERVATION"} and not self.context_allowed(agent,context):
            status="REJECTED"; summary=f"Validated policy v{policy['version']} excluded this context"
        self.counts[agent]["candidates"]+=1
        if status=="PASS": self.counts[agent]["passed"]+=1
        if status=="REJECTED": self.counts[agent]["rejected"]+=1
        self.publish(event(agent,symbol,status,summary,context=str(context),evaluation=details,
                           policy_version=policy.get("version",0)))
        return status!="REJECTED"

    def context_allowed(self,agent,context):
        policy=self.policies.get(agent,{})
        return policy.get("blocked_value")!=str(context) and ("allowed_value" not in policy or policy["allowed_value"]==str(context))

    @staticmethod
    def features(frame):
        x=add_features(frame)
        if x.empty: return x
        x["session"]=x.timestamp.dt.strftime("%Y-%m-%d")
        return x

    def signal(self,row,opening_high,opening_low,session_bars):
        symbol=row["symbol"]
        stamp=pd.Timestamp(row["timestamp"])
        volume=row.get("relative_volume")
        scan_context=f"{stamp.hour:02d}:00|volume_"+("unavailable" if not finite(volume) else "high" if volume>=1.5 else "normal")
        valid=session_bars>=15 and all(finite(row.get(k)) for k in ("close","ema9","ema21","ema50","atr")) and row["atr"]>0
        if not self.stage("Scanner",symbol,"PASS" if valid else "REJECTED","Closed candle and feature quality" if valid else "Waiting for complete opening range and price features",scan_context): return None
        rg=self.regime.classify(pd.Series(row))
        if not self.stage("Regime",symbol,"PASS" if rg.regime!="DATA_UNSAFE" else "REJECTED",rg.regime,rg.regime,
                          rule_score=rg.confidence,score_kind="rule_strength_not_probability"): return None
        candidates=self.setup.evaluate(pd.Series(row),opening_high,opening_low)
        candidates=[s for s in candidates if (s.direction.value=="CALL" and rg.regime in {"TREND_UP","VOLATILITY_EXPANSION"}) or
                    (s.direction.value=="PUT" and rg.regime in {"TREND_DOWN","VOLATILITY_EXPANSION"})]
        if not candidates:
            self.stage("Setup",symbol,"REJECTED","No aligned setup","none"); return None
        chosen=max(candidates,key=lambda s:s.confidence)
        if not self.stage("Setup",symbol,"PASS",chosen.setup_id,chosen.setup_id,rule_score=chosen.confidence): return None
        direction=chosen.direction.value
        has_vwap=finite(row.get("vwap"))
        confirmed=(row["ema9"]>row["ema21"] and (not has_vwap or row["close"]>row["vwap"])) if direction=="CALL" else (row["ema9"]<row["ema21"] and (not has_vwap or row["close"]<row["vwap"]))
        distance=abs(float(row.get("vwap_distance_atr",float("nan"))))
        confirmation="price_only_no_index_volume" if not has_vwap else "extended" if distance>2 else "near_vwap"
        if not self.stage("Confirmation",symbol,"PASS" if confirmed else "REJECTED","EMA agreement; VWAP unavailable" if not has_vwap else "EMA and VWAP direction agreement",confirmation): return None
        signal_id=hashlib.sha256(f"v4|{symbol}|{stamp.isoformat()}|{chosen.setup_id}".encode()).hexdigest()[:24]
        return {"id":signal_id,"symbol":symbol,"timestamp":stamp.isoformat(),"option_type":direction,
                "setup":chosen.setup_id,"regime":rg.regime,"stop_percent":chosen.stop_percent,
                "target_percent":chosen.target_percent,"underlying_entry":float(row["close"]),
                "agent_contexts":{"Scanner":scan_context,"Regime":rg.regime,"Setup":chosen.setup_id,"Confirmation":confirmation},
                "policy_versions":{a:self.policies.get(a,{}).get("version",0) for a in AGENT_ORDER}}

    def plan_signal(self, frame, now, symbol, buffer_atr=.1, retest_bars=5):
        """Shared baseline decision; executable premium protection is a later gate."""
        candidate = opening_range_retest(frame, now, buffer_atr, retest_bars)
        return self.plan_candidate(candidate,symbol)

    def plan_candidate(self,candidate,symbol):
        """Apply frozen policy to a causally produced candidate, without future labels."""
        if not candidate:
            return None
        contexts = {}
        for agent, context, summary in (
            ("Scanner", "completed_bars", "Continuous completed bars and opening range verified"),
            ("Regime", "price_only_baseline", "Price-only baseline; no unsupported volume/flow proxy"),
            ("Confirmation", "completed_resumption", "Retest and subsequent resumption confirmed"),
            ("Setup", candidate["setup"], "Completed opening-range retest and resumption"),
        ):
            if not self.stage(agent, symbol, "PASS", summary, context):
                return None
            contexts[agent] = context
        fingerprint = f"orb-retest-v1|{symbol}|{candidate['break_timestamp']}|{candidate['retest_timestamp']}"
        return {**candidate, "id": hashlib.sha256(fingerprint.encode()).hexdigest()[:24],
                "symbol": symbol, "strategy_version": "orb-retest-v1",
                "regime": "PRICE_ONLY_BASELINE", "agent_contexts": contexts,
                "policy_versions": {a: self.policies.get(a, {}).get("version", 0) for a in AGENT_ORDER},
                "execution_ready": False,
                "required_execution_gates": ["verified_contract", "premium_stop_and_target",
                                             "fee_aware_risk", "validated_net_expectancy"]}

    def option_candidates(self,signal,contracts,cash,now,max_spread=.03,historical=False):
        ranked=[]
        for c in contracts:
            if c.get("option_type")!=signal["option_type"] or c.get("is_atm",False): continue
            if not c.get("identity_verified") or not c.get("expiry") or str(c["expiry"])[:10]<str(now)[:10]: continue
            if not all(finite(c.get(k)) and c[k]>0 for k in ("strike","lot_size")): continue
            price=c.get("close") if historical else c.get("ask")
            if not finite(price) or price<=0 or price*c["lot_size"]>=cash: continue
            spread=None if historical else (c.get("ask",0)-c.get("bid",0))/price
            if not historical and (not finite(c.get("bid")) or c["bid"]<=0 or spread<0 or spread>max_spread or c.get("ask_qty",0)<c["lot_size"] or c.get("bid_qty",0)<c["lot_size"]): continue
            if not finite(c.get("oi")) or c["oi"]<=0 or not finite(c.get("volume")) or c["volume"]<=0: continue
            delta=c.get("delta")
            if finite(delta) and not .2<=abs(delta)<=.8: continue
            dte=(pd.Timestamp(c["expiry"])-pd.Timestamp(str(now)[:10])).days
            ctx=f"dte_{'0' if dte==0 else '1-3' if dte<=3 else '4+'}|delta_{'unknown' if not finite(delta) else 'low' if abs(delta)<.4 else 'medium' if abs(delta)<.6 else 'high'}"
            if not self.context_allowed("Option Selector",ctx): continue
            rank=(spread if spread is not None else 0,abs(abs(delta)-.5) if finite(delta) else 1,-c["oi"])
            greek_age=None
            if c.get("greeks_observed_at"):
                try: greek_age=max(0.,(local_time(now)-local_time(c["greeks_observed_at"])).total_seconds())
                except (TypeError,ValueError): greek_age=None
            ranked.append((rank,{**c,"spread_pct":spread,"option_context":ctx,
                                 "greeks_age_seconds":greek_age}))
        nearest_expiry=min((c["expiry"] for _,c in ranked),default=None)
        result=[c for _,c in sorted(ranked,key=lambda v:v[0]) if c["expiry"]==nearest_expiry]
        self.stage("Option Selector",signal["symbol"],"PASS" if result else "REJECTED",
                   "Liquid non-ATM candidates within cash budget" if result else "No verified, liquid contract fits the budget",
                   result[0]["option_context"] if result else "unavailable",count=len(result))
        return result
