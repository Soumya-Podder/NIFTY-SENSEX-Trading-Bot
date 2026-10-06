"""Shared causal entry and management policy for autonomous paper execution/replay."""
import hashlib
import math
import pandas as pd

from .strategy_portfolio import STRATEGIES, closed_session, evaluate_completed_bars
from .simple_paper import trend_signal
from .market_structure import analyze_structure, structure_evidence
from .pipeline import plan_protection
from .option_screen import describe as option_screen_policy

VERSION = "autonomous-paper-v1"
STRATEGY_SPECS = (
    {"id": "trend_continuation", "name": "Trend continuation", "version": "autonomous-continuation-v1",
     "condition": "ADX >= 20, aligned EMA 9/21 and completed continuation without excessive extension", "horizon_minutes": 30},
    *({**s, "version": "autonomous-"+s["version"], "horizon_minutes": 45 if s["id"] == "orb_retest" else 30 if s["id"] == "trend_pullback" else 10} for s in STRATEGIES),
)


def strategy_order(regime):
    order = ("range_rejection", "orb_retest", "trend_pullback", "trend_continuation") if regime == "RANGE" else (
        ("trend_pullback", "trend_continuation", "orb_retest", "range_rejection") if regime in {"TREND_UP", "TREND_DOWN"}
        else ("orb_retest", "trend_continuation", "trend_pullback", "range_rejection"))
    return {name: i for i, name in enumerate(order)}


def evaluate_market(frame, now, symbol, structure=None):
    bars, problem = closed_session(frame, now)
    signals, rows = evaluate_completed_bars(bars, now, symbol, problem)
    trend, reason = trend_signal(frame, now, symbol)
    row = {**STRATEGY_SPECS[0], "symbol": symbol, "status": "WAITING", "reason": reason,
           "checked_at": pd.Timestamp(now).isoformat(), "evidence": "UNVALIDATED_PAPER"}
    if bars is not None:
        last = bars.iloc[-1]
        atr = float(last.atr)
        slope = (float(last.ema21)-float(bars.iloc[-6].ema21))/atr if atr > 0 else 0
        regime = "TREND_UP" if last.adx >= 20 and last.ema9 > last.ema21 and slope >= .05 else (
            "TREND_DOWN" if last.adx >= 20 and last.ema9 < last.ema21 and slope <= -.05 else rows[0].get("regime", "TRANSITION"))
        row.update(last_bar=last.timestamp.isoformat(), feature_row=rows[0].get("feature_row"), regime=regime)
        if trend and (regime != trend["regime"] or abs(float(last.close-last.ema21)) > 2*atr):
            trend = None
            row["reason"] = "Trend is flat, contradictory or extended beyond two ATR from EMA 21"
        if trend:
            trend.update(strategy_id="trend_continuation", underlying_entry=float(last.close),
                         max_greeks_age_seconds=option_screen_policy()["max_greek_age_seconds"],
                         retest_timestamp=bars.iloc[-2].timestamp.isoformat(), feature_row=rows[0]["feature_row"],
                         evidence=["completed_continuation", "aligned_ema9_21", "adx_at_least_20", "bounded_extension"])
            signals.append(trend)
            row.update(status="CANDIDATE", reason="Completed directional continuation")
        for item in rows: item["regime"] = regime
        for signal in signals: signal["regime"] = regime
    rows.insert(0, row)
    specs = {s["id"]: s for s in STRATEGY_SPECS}
    for item in rows: item.update({k: specs[item["id"]][k] for k in ("name", "version", "condition", "horizon_minutes")})
    snapshot = structure if structure is not None else analyze_structure(frame, now, symbol)
    for signal in signals:
        spec = specs[signal["strategy_id"]]
        identity = f"{VERSION}|{spec['version']}|{symbol}|{signal['timestamp']}|{signal['option_type']}"
        signal.update(id=hashlib.sha256(identity.encode()).hexdigest()[:24], portfolio_version=VERSION,
                      strategy_version=spec["version"], strategy_name=spec["name"], horizon_minutes=spec["horizon_minutes"],
                      regime_priority=strategy_order(signal["regime"])[spec["id"]], policy_versions={}, execution_ready=False,
                      agent_contexts={"Scanner": "completed_bars", "Regime": signal["regime"], "Setup": signal["setup"], "Confirmation": "completed_bar"})
        evidence = structure_evidence(snapshot, signal["option_type"], now)
        # A confirmed higher-timeframe obstacle is a target-room constraint.
        # Two-minute noise is still displayed, but does not consume target room.
        relation = "RESISTANCE" if signal["option_type"] == "CALL" else "SUPPORT"
        zones = [z for z in snapshot.get("zones", []) if z["relation"] == relation and z["timeframe"] != "2m"]
        evidence["target_obstacle"] = min(zones, key=lambda z: z["distance_points"], default=None)
        signal["market_structure"] = evidence
    return signals, rows


def plan_candidate(signal, contract, candle):
    atr = candle.get("option_atr")
    if not isinstance(atr, (float, int)) or not math.isfinite(atr) or atr <= 0:
        raise ValueError("Completed selected-contract ATR required for adaptive protection")
    planned = plan_protection(signal, contract, candle, contract["ask"],
                              horizon_minutes=signal["horizon_minutes"], min_stop=atr)
    evidence = signal.get("market_structure", {})
    if evidence.get("status") != "OBSERVED":
        raise ValueError("Current causal support/resistance evidence unavailable")
    delta = abs(float(contract["delta"]))
    direction = 1 if signal["option_type"] == "CALL" else -1
    price = float(signal["feature_row"]["close"])
    projected_move = (planned["target_price"]-float(contract["ask"]))/delta
    target = price+direction*projected_move
    obstacle = evidence.get("target_obstacle")
    if obstacle:
        boundary = float(obstacle["lower"] if direction == 1 else obstacle["upper"])
        if direction*(boundary-price) < projected_move:
            raise ValueError(f"Insufficient 2R target room before confirmed {obstacle['timeframe']} zone")
        target = min(target, boundary) if direction == 1 else max(target, boundary)
    old_target = signal.get("underlying_target")
    if old_target is not None and direction*(float(old_target)-price) < projected_move:
        raise ValueError("Range midpoint offers insufficient room for the declared 2R premium target")
    planned.update(underlying_target=target)
    planned["protection_evidence"].update(source="completed_contract_structure_and_ATR",
        option_atr=atr, target_room_points=direction*(target-price), target_room_basis="Observed delta approximation, not an option payoff guarantee")
    return planned


def management_decision(position, frame, now):
    """A completed reversal can end a hold early; it never widens risk or a stop."""
    bars, problem = closed_session(frame, now)
    if problem or bars is None: return {"action": "HOLD", "reason": "Protective exits remain active; current completed-bar context unavailable"}
    recent = bars.tail(2)
    entry_at = pd.Timestamp(position["entry_ts"])
    if any(stamp+pd.Timedelta(minutes=1) <= entry_at for stamp in recent.timestamp):
        return {"action": "HOLD", "reason": "Awaiting two completed post-entry bars"}
    direction = 1 if position["option_type"] == "CALL" else -1
    reverse = all((float(r.close)-float(r.ema21))*direction < 0 and (float(r.ema9)-float(r.ema21))*direction < 0 for r in recent.itertuples())
    return {"action": "EXIT" if reverse else "HOLD", "reason": "COMPLETED_TREND_REVERSAL" if reverse else "Structure and momentum remain compatible; manage the observed bid and trailing protection",
            "bar_at": bars.iloc[-1].timestamp.isoformat(), "evaluated_at": pd.Timestamp(now).isoformat()}
