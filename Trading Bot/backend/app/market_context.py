"""Causal research observations. No scores, order authority or learned probabilities."""
from copy import deepcopy
import math
import pandas as pd

VERSION = "market-context-v1"
MAX_AGE_SECONDS = 120
CHAIN_FIELDS = ("symbol", "contract_id", "security_id", "exchange", "expiry", "strike", "option_type",
                "identity_verified", "metadata_source", "metadata_observed_on", "spot", "oi", "previous_oi",
                "volume", "iv", "chain_observed_at", "delta", "gamma", "theta", "vega",
                "greeks_source", "greeks_observed_at", "greek_units", "lot_size", "tick_size",
                "ltp", "previous_volume", "previous_close_price", "average_price", "chain_bid", "chain_ask",
                "chain_bid_qty", "chain_ask_qty", "api_response_id", "observation_change")


def unavailable(reason):
    return {"status": "DATA_UNAVAILABLE", "reason": reason}


def finite(value, minimum=0):
    try:
        return value is not None and math.isfinite(float(value)) and float(value) >= minimum
    except (TypeError, ValueError):
        return False


def fresh(stamp, now, max_age=MAX_AGE_SECONDS):
    try:
        timestamp = pd.Timestamp(stamp)
        current = pd.Timestamp(now)
        return timestamp.tzinfo is not None and current.date() == timestamp.tz_convert(current.tz).date() and \
            0 <= (current - timestamp).total_seconds() <= max_age
    except (ValueError, TypeError):
        return False


def chain_window(chain, symbol):
    """One expiry, ATM plus five listed strikes on either side; never mix contracts."""
    rows = [dict(c) for c in chain if c.get("symbol") == symbol]
    if not rows or not finite(rows[0].get("spot"), 1):
        return [], "Option-chain spot unavailable"
    if len({c.get("expiry") for c in rows}) != 1:
        return [], "Mixed option expiries"
    if any(not finite(c.get("strike"), 1) for c in rows):
        return [], "Invalid option strike"
    strikes = sorted({float(c["strike"]) for c in rows})
    atm = min(strikes, key=lambda k: abs(k - float(rows[0]["spot"])))
    index = strikes.index(atm)
    if index < 5 or index + 5 >= len(strikes):
        return [], "ATM +/-5 strike coverage incomplete"
    selected = set(strikes[index - 5:index + 6])
    return [c for c in rows if float(c["strike"]) in selected], None


def positioning_context(rows, symbol, now, *, full_chain=False):
    if not rows:
        return unavailable("Option-chain window unavailable")
    if any(not c.get("identity_verified") or not c.get("metadata_source") or
           not str(c.get("security_id", "")).isdigit() or c.get("symbol") != symbol or
           str(c.get("expiry", "")) <= str(now.date()) for c in rows):
        return unavailable("Fixed option identity or eligible expiry unavailable")
    if len({c.get("expiry") for c in rows}) != 1 or len({c.get("chain_observed_at") for c in rows}) != 1:
        return unavailable("Mixed chain observations")
    if any(not fresh(c.get("chain_observed_at"), now) for c in rows):
        return unavailable("Option-chain observation stale or timestamp unavailable")
    if any(not finite(c.get("oi")) or not finite(c.get("strike"), 1) or
           not finite(c.get("spot"), 1) for c in rows):
        return unavailable("Invalid option-chain values")
    strikes = {float(c["strike"]) for c in rows}
    keys = {(c["strike"], c.get("option_type")) for c in rows}
    expected = {(strike, side) for strike in strikes for side in ("CALL", "PUT")}
    if (not full_chain and (len(strikes) != 11 or keys != expected or len(rows) != 22)) or len({c["contract_id"] for c in rows}) != len(rows) or len(keys) != len(rows):
        return unavailable("Incomplete or duplicated CALL/PUT pairs in ATM +/-5 window")
    spot = float(rows[0]["spot"])
    if any(float(c["spot"]) != spot for c in rows):
        return unavailable("Mixed spot observations")
    calls = [c for c in rows if c["option_type"] == "CALL"]
    puts = [c for c in rows if c["option_type"] == "PUT"]
    if full_chain and (not calls or not puts):
        return unavailable("Both CALL and PUT positioning observations are required")
    call_oi = sum(float(c["oi"]) for c in calls)
    put_oi = sum(float(c["oi"]) for c in puts)
    prior_complete = all(finite(c.get("previous_oi")) for c in rows)
    def wall(items):
        chosen = max(items, key=lambda c: float(c["oi"]), default=None)
        return {k: chosen[k] for k in ("contract_id", "strike", "oi")} if chosen else None
    return {"status": "OBSERVED", "source": "dhan_option_chain", "observed_at": rows[0]["chain_observed_at"],
            "scope": "FULL_RETURNED_FIXED_CONTRACT_CHAIN" if full_chain else "ATM_PLUS_MINUS_5",
            "strike_count": len(strikes), "missing_pairs": len(expected-keys),
            "coverage": "Returned contracts mapped to current instrument metadata; unmapped contracts are not analysed",
            "timestamp_basis": "HTTP response received; exchange OI update time unavailable",
            "expiry": rows[0]["expiry"], "spot": spot, "contracts": len(rows),
            "atm_strike": min(strikes, key=lambda k: abs(k - spot)),
            "call_oi": call_oi, "put_oi": put_oi, "pcr": put_oi / call_oi if call_oi > 0 else None,
            "call_wall": wall([c for c in calls if float(c["strike"]) > spot]),
            "put_wall": wall([c for c in puts if float(c["strike"]) < spot]),
            "prior_oi_status": "OBSERVED" if prior_complete else "DATA_UNAVAILABLE",
            "call_oi_change": sum(float(c["oi"]) - float(c["previous_oi"]) for c in calls) if prior_complete else None,
            "put_oi_change": sum(float(c["oi"]) - float(c["previous_oi"]) for c in puts) if prior_complete else None,
            "oi_change_basis": "Previous day, as supplied by Dhan",
            "since_previous": window_changes(rows),
            "interpretation": "Related positioning observations, not independent votes or buyer/writer direction"}


def window_changes(rows):
    """Aggregate only matched fixed contracts, never changes in the ATM basket."""
    observations=[c.get("observation_change") or {} for c in rows]
    first=next((c for c in observations if c.get("status")=="OBSERVED"),None)
    if first is None:
        return unavailable(next((c["reason"] for c in observations if c.get("reason")),"Awaiting a second fresh chain response"))
    matched=[]
    for row,observation in zip(rows,observations):
        contract=observation.get("contract") or {}
        if observation.get("status")!="OBSERVED" or observation.get("previous_observed_at")!=first["previous_observed_at"] or \
           observation.get("observed_at")!=first["observed_at"]:
            return unavailable("Mixed comparison intervals")
        if contract.get("security_id")==str(row.get("security_id")) and contract.get("strike")==row.get("strike") and \
           contract.get("option_type")==row.get("option_type"):
            matched.append(contract)
    def total(side,field):
        values=[c.get("changes",{}).get(field) for c in matched if c["option_type"]==side]
        return sum(values) if values and all(v is not None and math.isfinite(v) for v in values) else None
    return {"status":"OBSERVED" if len(matched)==len(rows) else "PARTIAL",
            "observed_at":first["observed_at"],"previous_observed_at":first["previous_observed_at"],
            "previous_response_id":first.get("previous_response_id"),
            "response_id":rows[0].get("api_response_id"),"interval_seconds":first["interval_seconds"],
            "long_gap":first["long_gap"],"matched_contracts":len(matched),"window_contracts":len(rows),
            "call_oi_change":total("CALL","oi"),"put_oi_change":total("PUT","oi"),
            "call_volume_change":total("CALL","volume"),"put_volume_change":total("PUT","volume"),
            "volume_resets":sum(c.get("volume_status")=="RESET_OR_CORRECTION" for c in matched),
            "contracts":matched,"interpretation":first["interpretation"]}


def futures_context(contract, frame, now):
    if not contract or not contract.get("identity_verified") or contract.get("instrument") != "FUTIDX" or \
            not str(contract.get("security_id", "")).isdigit() or not contract.get("metadata_source"):
        return unavailable("Verified index futures contract unavailable")
    if str(contract.get("expiry", "")) < str(now.date()):
        return unavailable("Futures contract expired")
    if frame is None or frame.empty or not {"timestamp", "high", "low", "close", "volume"} <= set(frame):
        return unavailable("Futures candles unavailable")
    x = frame.copy()
    x["timestamp"] = pd.to_datetime(x.timestamp, utc=True, errors="coerce").dt.tz_convert("Asia/Kolkata")
    if x.timestamp.isna().any():
        return unavailable("Invalid futures candle timestamps")
    start = pd.Timestamp(now).tz_convert("Asia/Kolkata").normalize() + pd.Timedelta(hours=9, minutes=15)
    x = x[(x.timestamp >= start) & (x.timestamp + pd.Timedelta(minutes=1) <= pd.Timestamp(now))].sort_values("timestamp")
    if x.empty or not fresh(x.timestamp.iloc[-1] + pd.Timedelta(minutes=1), now, 180):
        return unavailable("Completed futures candles are stale or missing")
    expected = pd.date_range(start, x.timestamp.iloc[-1], freq="min")
    if list(x.timestamp) != list(expected):
        return unavailable("Futures session has missing or duplicated minutes")
    for key in ("high", "low", "close", "volume"):
        x[key] = pd.to_numeric(x[key], errors="coerce")
        if not all(finite(v, 0 if key == "volume" else 0.000001) for v in x[key]):
            return unavailable("Invalid futures prices or volume")
    if (x.high < x.low).any() or ((x.close < x.low) | (x.close > x.high)).any() or x.volume.sum() <= 0:
        return unavailable("Invalid futures candle range or zero session volume")
    vwap = float((((x.high + x.low + x.close) / 3) * x.volume).sum() / x.volume.sum())
    close = float(x.close.iloc[-1])
    return {"status": "OBSERVED", "contract_id": contract["contract_id"], "expiry": contract["expiry"],
            "source": "dhan_futures_minute_candles", "observed_at": (x.timestamp.iloc[-1] + pd.Timedelta(minutes=1)).isoformat(),
            "method": "HLC3 minute-volume VWAP proxy, not exact trade VWAP",
            "vwap": vwap, "futures_close": close, "distance_points": close - vwap,
            "relation": "ABOVE" if close > vwap else "BELOW" if close < vwap else "AT",
            "volume": float(x.volume.sum()), "bars": len(x),
            "comparison": "Same futures contract versus its own VWAP; no spot/futures basis mixing"}


def volatility_context(rows, positioning, now, session_exit="15:05", horizon_minutes=10):
    if positioning.get("status") != "OBSERVED":
        return unavailable("Fresh ATM option observation unavailable")
    atm = [c for c in rows if c["strike"] == positioning["atm_strike"]]
    if len(atm) != 2 or any(not finite(c.get("iv"), 0.000001) for c in atm):
        return unavailable("Both observed ATM implied volatilities are required")
    end = pd.Timestamp(str(now.date()) + " " + session_exit, tz="Asia/Kolkata")
    remaining = max(0, (end - pd.Timestamp(now)).total_seconds() / 60)
    horizon = min(max(0, horizon_minutes), remaining)
    if horizon <= 0:
        return unavailable("Paper holding window has ended")
    iv = sum(float(c["iv"]) for c in atm) / 2
    return {"status": "SCENARIO", "source": "same-index ATM call/put IV", "iv_percent": iv,
            "observed_at": positioning["observed_at"], "remaining_minutes": remaining, "horizon_minutes": horizon,
            "move_points": float(positioning["spot"]) * iv / 100 * math.sqrt(horizon / (365 * 24 * 60)),
            "method": "Annualised IV scaled by calendar time; uncalibrated intraday scenario",
            "interpretation": "Underlying movement scale only; not option P&L, probability or an entry hurdle"}


def build_context(symbol, rows, contract, frame, now, session_exit="15:05", horizon_minutes=10, *, full_chain=False):
    positioning = positioning_context(rows, symbol, now, full_chain=full_chain)
    return {"version": VERSION, "symbol": symbol, "captured_at": now.isoformat(),
            "session_exit": session_exit,
            "authority": "RESEARCH_ONLY", "learning_eligible": False,
            "positioning": positioning, "futures": futures_context(contract, frame, now) if contract.get("symbol") == symbol else unavailable("Matching index futures unavailable"),
            "volatility": volatility_context(rows, positioning, now, session_exit, horizon_minutes)}


def decision_context(snapshot, now, generation, horizon_minutes=10):
    """Never carry yesterday's observation or a prior credential generation into a decision."""
    if not snapshot:
        return {"authority": "RESEARCH_ONLY", "status": "DATA_UNAVAILABLE", "reason": "Awaiting market-context collection"}
    result = deepcopy(snapshot)
    if not fresh(result.get("captured_at"), now) or result.get("credential_generation") != generation:
        result.update(status="STALE", reason="Context expired or credentials changed")
        for key in ("positioning", "futures", "volatility"):
            result[key] = unavailable(result["reason"])
        return result
    result["status"] = "RESEARCH_ONLY"
    for key in ("positioning", "futures", "volatility"):
        part = result[key]
        if part.get("status") in {"OBSERVED", "SCENARIO"} and not fresh(part.get("observed_at"), now, 180 if key == "futures" else MAX_AGE_SECONDS):
            result[key] = unavailable("Source observation expired")
    volatility = result["volatility"]
    if volatility.get("status") == "SCENARIO":
        end = pd.Timestamp(str(now.date()) + " " + result["session_exit"], tz="Asia/Kolkata")
        remaining = max(0, (end - pd.Timestamp(now)).total_seconds() / 60)
        horizon = min(horizon_minutes, remaining)
        if horizon <= 0 or result["positioning"].get("status") != "OBSERVED":
            result["volatility"] = unavailable("Holding window ended or positioning observation expired")
        else:
            volatility.update(remaining_minutes=remaining, horizon_minutes=horizon,
                move_points=result["positioning"]["spot"] * volatility["iv_percent"] / 100 * math.sqrt(horizon / (365 * 24 * 60)))
    result["evaluated_at"] = now.isoformat()
    return result
