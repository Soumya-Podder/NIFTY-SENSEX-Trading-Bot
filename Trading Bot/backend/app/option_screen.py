"""Observed option-buying filters. Preferences are hypotheses, not probabilities."""
import math
from .session import local_time, quote_is_fresh

VERSION = "option-buyer-v1"


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def midpoint_spread(contract):
    bid, ask = number(contract.get("bid")), number(contract.get("ask"))
    if bid is None or ask is None or not 0 < bid <= ask:
        return None, None
    mid = (ask + bid) / 2
    return mid, (ask - bid) / mid


def describe(max_spread=.02, min_net_reward_risk=1.):
    return {"version": VERSION, "evidence": "UNVALIDATED_PAPER",
            "atm_allowed": True, "preferred_abs_delta": [.45, .60],
            "trend_only_abs_delta": [.30, .45], "max_greek_age_seconds": 120,
            "preferred_spread_pct": .01, "max_spread_pct": max_spread,
            "spread_basis": "midpoint", "expiry_day_allowed": False,
            "min_net_reward_risk": min_net_reward_risk,
            "target_policy": "Existing structural 2R nominal target; never extended to pass a filter",
            "iv_percentile_status": "DATA_UNAVAILABLE: comparable maturity history required"}


def assess(contract, signal, now, *, max_spread=.02, max_quote_age=2):
    """Reject missing/future evidence; retain every reason for no-trade reporting."""
    missing, rejected = [], []
    if not contract.get("identity_verified"):
        missing.append("Verified contract identity required")
    if contract.get("option_type")!=signal.get("option_type"):
        rejected.append("Contract side disagrees with signal")
    if any((number(contract.get(k)) or 0) <= 0 for k in ("oi", "volume")):
        missing.append("Positive observed OI and volume required")
    mid, spread = midpoint_spread(contract)
    if mid is None:
        missing.append("Valid non-crossed bid and ask required")
    elif spread > max_spread + 1e-12:
        rejected.append("Spread exceeds midpoint limit")
    if not quote_is_fresh(contract, now, max_quote_age):
        missing.append("Fresh observed option depth required")
    lot = number(contract.get("lot_size"))
    if lot is None or lot <= 0 or not lot.is_integer() or any((number(contract.get(k)) or 0) < lot for k in ("bid_qty", "ask_qty")):
        missing.append("Full-lot bid and ask depth required")
    try:
        if local_time(str(contract["expiry"])[:10]).date() <= local_time(now).date():
            rejected.append("Expiry-day and expired contracts excluded")
    except (KeyError, TypeError, ValueError):
        missing.append("Valid contract expiry required")
    age = None
    try:
        age = (local_time(now) - local_time(contract["greeks_observed_at"])).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    max_greeks_age = number(signal.get("max_greeks_age_seconds")) or 120
    fresh_greeks = age is not None and 0 <= age <= max_greeks_age
    if not fresh_greeks:
        missing.append(f"Observed Greeks must be no older than {max_greeks_age:g} seconds and not future-dated")
    delta = number(contract.get("delta"))
    preferred = False
    if delta is None:
        missing.append("Observed Delta required")
    else:
        side = signal.get("option_type")
        if (side == "CALL" and delta <= 0) or (side == "PUT" and delta >= 0):
            rejected.append("Delta sign disagrees with option type")
        magnitude = abs(delta)
        preferred = .45 <= magnitude <= .60
        trend = signal.get("regime") == ("TREND_UP" if side == "CALL" else "TREND_DOWN")
        if not preferred and not (.30 <= magnitude < .45 and trend):
            rejected.append("Delta outside preferred band or lower-Delta contract lacks aligned trend")
    theta, vega, gamma = (number(contract.get(k)) for k in ("theta", "vega", "gamma"))
    units = contract.get("greek_units") or {}
    daily_theta = abs(theta) / mid * 100 if (fresh_greeks and mid and theta is not None and
                    units.get("theta") == "premium_per_day") else None
    # These are conditional local sensitivities, never deducted from observed P&L.
    sensitivity = {
        "authority": "CONTEXT_ONLY", "theta_daily_pct": daily_theta,
        "theta_status": "LOCAL_ESTIMATE" if daily_theta is not None else "UNAVAILABLE_OR_DAILY_UNIT_UNVERIFIED",
        "vega_one_point_iv_drop_per_unit": -vega if (fresh_greeks and vega is not None and
                    units.get("vega") == "premium_per_iv_percentage_point") else None,
        "gamma": gamma if fresh_greeks else None,
        "iv": number(contract.get("iv")) if fresh_greeks else None,
        "iv_percentile": None, "iv_percentile_status": "Comparable maturity history unavailable",
        "note": "Greeks are local estimates; no institutional-flow inference or profit probability",
    }
    reasons = missing + rejected
    return {"version": VERSION, "status": "WAITING_DATA" if missing else "REJECTED" if rejected else "PASS",
            "reasons": reasons, "missing_data": bool(missing), "mid_price": mid,
            "spread_pct": spread, "spread_basis": "midpoint", "abs_delta": abs(delta) if delta is not None else None,
            "delta_preference": "PREFERRED" if preferred else "TREND_ONLY",
            "spread_preference": "PREFERRED" if spread is not None and spread <= .01 else "ACCEPTABLE",
            "greeks_age_seconds": age, "sensitivity": sensitivity}


def net_economics(entry, bid, stop, target, quantity, stop_cost, target_cost):
    """One spread reserve at the adverse exit, plus round-trip charges once."""
    values = [number(v) for v in (entry, bid, stop, target, quantity, stop_cost, target_cost)]
    if any(v is None for v in values):
        raise ValueError("Finite entry, protection, quantity and costs required")
    entry, bid, stop, target, quantity, stop_cost, target_cost = values
    if not 0 < stop < entry < target or not 0 < bid <= entry or quantity <= 0 or min(stop_cost, target_cost) < 0:
        raise ValueError("Invalid option protection or execution economics")
    spread_reserve = (entry - bid) * quantity
    risk = (entry - stop) * quantity + spread_reserve + stop_cost
    reward = (target - entry) * quantity - target_cost
    return {"risk": risk, "net_reward": reward, "net_reward_risk": reward / risk,
            "spread_reserve": spread_reserve, "stop_charges": stop_cost, "target_charges": target_cost,
            "strict_2r_pass": reward / risk >= 2., "target_extended": False}
