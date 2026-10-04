"""Auditable specialist evidence. No votes, invented probabilities or order authority."""
from datetime import datetime
from typing import Any

from .option_screen import midpoint_spread, number
from .session import quote_is_fresh

VERSION = "specialist-review-v2"
ROLE_TASKS = {
    "Regime Agent": "Check the strategy against the current completed-bar regime",
    "Directional Agent": "Check CALL/PUT direction and structural invalidation",
    "Options Flow Agent": "Observe unsigned OI, prior OI and volume; no institutional-flow inference",
    "Gamma Agent": "Observe fresh contract gamma; dealer positioning is unavailable",
    "Theta Agent": "Observe daily decay only when the provider's units are documented",
    "IV Agent": "Observe fresh IV; comparable-maturity IV percentile is unavailable",
    "Liquidity Agent": "Check quote age, midpoint spread and one-lot bid/ask depth",
    "Momentum Agent": "Check completed-bar ADX, EMA alignment and EMA slope for this strategy",
    "Structure Agent": "Check current price, ATR, invalidation and remaining target room",
    "News/Event Agent": "Report whether a validated timestamped event feed is available",
    "Adversarial Agent": "Challenge required evidence, contradictions and net reward/risk",
    "Loss Investigator": "Classify closed losing episodes for research; never override entry gates",
    "Risk Sentinel": "Enforce shared account, session, cash and risk limits; recheck atomically at fill",
    "Orchestrator": "Review every required gate; rank eligible paper candidates or wait",
}


def waiting_agents(reason):
    return {name: {"status": "NOT_EVALUATED", "task": task, "evidence": reason}
            for name, task in ROLE_TASKS.items()}


def _age(value: Any, now: Any):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (now - stamp).total_seconds()
    except (TypeError, ValueError):
        return None


def assess_specialists(signal, contract, now, *, risk, reward, max_quote_age=2.,
                       max_spread=.02, min_net_reward_risk=1.):
    """Required evidence blocks; advisory observations cannot manufacture a direction."""
    feature = signal.get("feature_row") or {}
    agents = waiting_agents("Candidate review in progress")

    def record(name, status, evidence, required=False):
        agents[name].update(status=status, evidence=evidence, required=required,
                            evaluated_at=now.isoformat())

    side = signal.get("option_type")
    strategy, regime = signal.get("strategy_id"), signal.get("regime")
    direction = 1 if side == "CALL" else -1 if side == "PUT" else 0
    aligned = "TREND_UP" if side == "CALL" else "TREND_DOWN"
    compatible = (strategy in {"trend_pullback", "trend_continuation"} and regime == aligned or
                  strategy == "range_rejection" and regime == "RANGE" or
                  strategy == "orb_retest" and regime in {aligned, "RANGE", "TRANSITION"})
    record("Regime Agent", "PASS" if compatible else "VETO",
           {"strategy": strategy, "current_regime": regime, "compatible": compatible}, True)

    entry, invalid = number(signal.get("underlying_entry")), number(signal.get("invalidation"))
    directed = direction and entry is not None and invalid is not None and entry > 0 and invalid > 0 and (entry-invalid)*direction > 0
    record("Directional Agent", "PASS" if directed else "VETO",
           {"direction": side, "setup_entry": entry, "invalidation": invalid}, True)

    adx, slope = number(feature.get("adx")), number(feature.get("ema_slope_atr"))
    ema9, ema21 = number(feature.get("ema9")), number(feature.get("ema21"))
    age = _age(feature.get("timestamp"), now)
    complete = age is not None and 60 <= age <= 125
    available = complete and all(v is not None for v in (adx, slope, ema9, ema21)) and 0 <= adx <= 100 and ema9 > 0 and ema21 > 0
    momentum = False
    if available:
        if strategy == "trend_pullback":
            momentum = adx >= 25 and slope*direction >= .2 and (ema9-ema21)*direction > 0
        elif strategy == "trend_continuation":
            momentum = adx >= 20 and slope*direction >= .05 and (ema9-ema21)*direction > 0
        elif strategy == "range_rejection":
            momentum = adx <= 20 and abs(slope) <= .15
        elif strategy == "orb_retest":
            # ORB can lead a transition; reject a strongly established opposite trend.
            momentum = not (adx >= 25 and slope*direction <= -.2 and (ema9-ema21)*direction < 0)
    record("Momentum Agent", "DATA_UNAVAILABLE" if not available else "PASS" if momentum else "VETO",
           {"adx": adx, "ema_slope_atr": slope, "ema9": ema9, "ema21": ema21,
            "completed_bar": feature.get("timestamp"), "bar_age_seconds": age}, True)

    price, atr = number(feature.get("close")), number(feature.get("atr"))
    target = number(signal.get("underlying_target"))
    structure = (directed and price is not None and atr is not None and atr > 0 and
                 (price-invalid)*direction > 0 and (target is None or (target-price)*direction > 0))
    if structure and strategy == "trend_pullback":
        structure = ema21 is not None and abs(price-ema21) <= 1.5*atr
    if structure and strategy == "trend_continuation":
        structure = ema21 is not None and abs(price-ema21) <= 2*atr
    if structure and strategy == "range_rejection":
        structure = target is not None and (target-price)*direction >= 1.2*atr
    record("Structure Agent", "PASS" if complete and structure else "VETO",
           {"price": price, "atr": atr, "invalidation": invalid, "target": target,
            "completed_bar": feature.get("timestamp"), "multi_timeframe": signal.get("market_structure", {})}, True)

    oi, previous, volume = (number(contract.get(k)) for k in ("oi", "previous_oi", "volume"))
    record("Options Flow Agent", "OBSERVATION" if oi is not None and oi > 0 and volume is not None and volume > 0 else "DATA_UNAVAILABLE",
           {"oi": oi, "previous_oi": previous, "change_oi": oi-previous if oi is not None and previous is not None else None,
            "volume": volume, "interpretation": "Unsigned positioning; not proof of buyers, writers or institutional flow"})
    sensitivity = (contract.get("option_screen") or {}).get("sensitivity") or {}
    greek_age = _age(contract.get("greeks_observed_at"), now)
    greek_fresh = greek_age is not None and 0 <= greek_age <= 120
    for name, key in (("Gamma Agent", "gamma"), ("Theta Agent", "theta_daily_pct"), ("IV Agent", "iv")):
        value = sensitivity.get(key) if sensitivity else (contract.get(key) if key != "theta_daily_pct" else None)
        value = number(value) if greek_fresh else None
        record(name, "OBSERVATION" if value is not None else "DATA_UNAVAILABLE",
               {key: value, "observed_at": contract.get("greeks_observed_at"), "authority": "CONTEXT_ONLY"})
    record("News/Event Agent", "DATA_UNAVAILABLE", "No validated event feed; event risk has not been assessed")
    record("Loss Investigator", "POST_TRADE", "Closed-loss hypotheses are available in the individual-agent audit")

    _, spread = midpoint_spread(contract)
    bid_qty, ask_qty, lot = (number(contract.get(k)) for k in ("bid_qty", "ask_qty", "lot_size"))
    depth = lot is not None and lot > 0 and bid_qty is not None and ask_qty is not None and min(bid_qty, ask_qty) >= lot
    fresh = quote_is_fresh(contract, now, max_quote_age)
    liquidity = fresh and depth and spread is not None and 0 <= spread <= max_spread
    record("Liquidity Agent", "PASS" if liquidity else "VETO",
           {"fresh": fresh, "depth_ok": depth, "spread_pct": spread, "spread_basis": "midpoint"}, True)

    warnings = [name+": "+row["status"] for name, row in agents.items()
                if row.get("required") and row["status"] != "PASS"]
    if number(risk) is None or risk <= 0 or number(reward) is None or reward <= 0:
        warnings.append("Non-positive or unavailable net economics")
    elif reward/risk < min_net_reward_risk:
        warnings.append(f"Net target reward/risk below {min_net_reward_risk:g}:1 minimum")
    record("Adversarial Agent", "VETO" if warnings else "PASS", warnings or ["Required candidate evidence is consistent"], True)
    agents["Adversarial Agent"]["warnings"] = warnings
    agents["Adversarial Agent"]["structure_observations"] = signal.get("market_structure", {})
    agents["Adversarial Agent"]["outcome_estimate"] = signal.get("outcome_estimate", {})
    vetoes = [name for name, row in agents.items() if row.get("required") and row["status"] != "PASS"]
    decision = "WAIT" if vetoes else side
    record("Risk Sentinel", "PENDING", "Account preflight and atomic broker admission still required", True)
    record("Orchestrator", "WAIT" if vetoes else "CANDIDATE", "Candidate evidence only; not permission to fill")
    context = signal.get("market_context") or {}
    for name, key in (("Options Flow Agent", "positioning"), ("Structure Agent", "futures"), ("IV Agent", "volatility")):
        agents[name]["research_context"] = context.get(key, {"status": "DATA_UNAVAILABLE"})
        agents[name]["research_authority"] = "NONE"
    return {"version": VERSION, "decision": decision, "vetoes": vetoes, "agents": agents,
            "authority": "EVIDENCE_ONLY_RISK_SENTINEL_REMAINS_FINAL"}
