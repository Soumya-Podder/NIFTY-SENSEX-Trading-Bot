"""Deterministic specialist-agent evidence for a paper candidate.

These are evidence producers, not independent traders.  They intentionally use
rule strength and data-quality labels rather than invented win probabilities.
The shared Risk Sentinel and paper engine remain the only authorities that can
reject or execute an order.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .session import quote_is_fresh


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _age_seconds(value: Any, now: Any) -> float | None:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        current = now if isinstance(now, datetime) else datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        return max(0.0, (current - stamp).total_seconds())
    except (TypeError, ValueError):
        return None


def assess_specialists(signal: dict[str, Any], contract: dict[str, Any], now: Any,
                       *, risk: float, reward: float, max_quote_age: float = 2.0) -> dict[str, Any]:
    """Assess specialist evidence for one candidate without placing an order."""
    feature = signal.get("feature_row") or {}
    spread = contract.get("spread_pct")
    if not _finite(spread) and _finite(contract.get("ask")) and _finite(contract.get("bid")) and float(contract.get("ask")) > 0:
        spread = (float(contract["ask"]) - float(contract["bid"])) / float(contract["ask"])
    depth_ok = _finite(contract.get("ask_qty")) and _finite(contract.get("bid_qty")) and contract.get("lot_size", 0) > 0 and \
        contract.get("ask_qty", 0) >= contract.get("lot_size", 0) and contract.get("bid_qty", 0) >= contract.get("lot_size", 0)
    fresh = quote_is_fresh(contract, now, max_quote_age)
    agents: dict[str, dict[str, Any]] = {
        "Regime Agent": {"status": "PASS" if signal.get("regime") not in {None, "TRANSITION", "DATA_UNSAFE"} else "OBSERVATION",
                         "score_kind": "rule_strength", "evidence": signal.get("regime") or "missing"},
        "Directional Agent": {"status": "PASS" if signal.get("option_type") in {"CALL", "PUT"} and _finite(signal.get("underlying_entry")) else "DATA_UNAVAILABLE",
                              "score_kind": "rule_strength", "evidence": signal.get("option_type")},
        "Options Flow Agent": {"status": "PASS" if _finite(contract.get("oi")) and float(contract.get("oi")) > 0 and _finite(contract.get("volume")) and float(contract.get("volume")) > 0 else "DATA_UNAVAILABLE",
                               "score_kind": "data_quality", "evidence": {"oi": contract.get("oi"), "volume": contract.get("volume"), "change_oi": contract.get("change_oi", contract.get("oi_change"))}},
        "Gamma Agent": {"status": "PASS" if _finite(contract.get("gamma")) else "DATA_UNAVAILABLE",
                        "score_kind": "observed_greek", "evidence": {"gamma": contract.get("gamma"), "observed_at": contract.get("greeks_observed_at")}},
        "Theta Agent": {"status": "PASS" if _finite(contract.get("theta")) and _finite(contract.get("iv")) else "DATA_UNAVAILABLE",
                        "score_kind": "decay_observation", "evidence": {"theta": contract.get("theta"), "iv": contract.get("iv")}},
        "IV Agent": {"status": "PASS" if _finite(contract.get("iv")) else "DATA_UNAVAILABLE",
                     "score_kind": "observed_volatility", "evidence": {"iv": contract.get("iv"), "greeks_age_seconds": _age_seconds(contract.get("greeks_observed_at"), now)}},
        "Liquidity Agent": {"status": "PASS" if fresh and depth_ok and _finite(spread) and 0 <= float(spread) <= .03 else "VETO",
                            "score_kind": "execution_quality", "evidence": {"fresh": fresh, "depth_ok": depth_ok, "spread_pct": spread}},
        "Momentum Agent": {"status": "PASS" if _finite(feature.get("adx")) and _finite(feature.get("ema_slope_atr")) else "DATA_UNAVAILABLE",
                           "score_kind": "rule_strength", "evidence": {"adx": feature.get("adx"), "ema_slope_atr": feature.get("ema_slope_atr")}},
        "Structure Agent": {"status": "PASS" if _finite(feature.get("atr")) and _finite(feature.get("vwap_distance_atr")) else "DATA_UNAVAILABLE",
                            "score_kind": "rule_strength", "evidence": {"atr": feature.get("atr"), "vwap_distance_atr": feature.get("vwap_distance_atr")}},
        # No unverified headline is treated as a positive signal.  The absence
        # is visible and reduces confidence; it does not fabricate a clear event.
        "News/Event Agent": {"status": "DATA_UNAVAILABLE", "score_kind": "data_quality",
                             "evidence": "No validated event feed attached to this candidate", "confidence_penalty": .15},
    }
    warnings = []
    if not _finite(risk) or risk <= 0:
        warnings.append("non-positive risk")
    if not _finite(reward) or reward <= 0:
        warnings.append("non-positive target reward")
    if _finite(risk) and _finite(reward) and reward / risk < 1:
        warnings.append("target reward below all-in risk")
    if not fresh:
        warnings.append("quote is stale")
    if not depth_ok:
        warnings.append("full-lot depth is unavailable")
    if _finite(spread) and float(spread) > .03:
        warnings.append("spread exceeds execution limit")
    agents["Adversarial Agent"] = {"status": "VETO" if warnings else "PASS", "score_kind": "challenge",
                                    "evidence": warnings or ["No deterministic contradiction found"],
                                    "warnings": warnings}
    agents["Orchestrator"] = {"status": "WAIT" if warnings else signal.get("option_type", "WAIT"),
                               "score_kind": "decision", "evidence": "Hard vetoes and data quality precede preference ranking"}
    vetoes = [name for name, row in agents.items() if row.get("status") == "VETO"]
    return {"decision": "WAIT" if vetoes else signal.get("option_type", "WAIT"),
            "vetoes": vetoes, "confidence_penalties": sum(float(row.get("confidence_penalty", 0)) for row in agents.values()),
            "agents": agents, "authority": "EVIDENCE_ONLY_RISK_SENTINEL_REMAINS_FINAL"}

