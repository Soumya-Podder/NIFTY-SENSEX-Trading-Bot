"""Fixed-horizon outcome research. Historical frequencies are not calibrated forecasts."""
import hashlib
import json
import math
from collections import Counter
import pandas as pd
from .provenance import has_synthetic_options

VERSION = "outcome-evidence-v1"
MIN_SESSIONS = 30
SCOPE = ("symbol", "strategy_version", "regime", "option_type", "horizon_minutes", "exit_policy", "stop_bucket", "reward_multiple")


def timestamp(value):
    t = pd.Timestamp(value)
    return t.tz_localize("Asia/Kolkata") if t.tzinfo is None else t.tz_convert("Asia/Kolkata")


def outcome_scope(trade):
    entry = float(trade.get("entry", trade.get("underlying_entry", 0)) or 0)
    stop = float(trade.get("initial_stop", trade.get("stop_price", trade.get("stop", 0))) or 0)
    target = float(trade.get("target_price", trade.get("target", 0)) or 0)
    risk = entry-stop
    pct = risk/entry if entry > 0 else 0
    return {**{k: trade.get(k) for k in SCOPE},
            "stop_bucket": "0-5%" if pct <= .05 else "5-10%" if pct <= .1 else "10-20%" if pct <= .2 else "20%+",
            "reward_multiple": round((target-entry)/risk, 1) if risk > 0 else None}


def label_outcomes(frame, trades):
    """Labels are attached AFTER replay; future rows never participate in candidate selection.

    Target/stop mean original fixed premium barriers over the declared horizon,
    including after an actual early exit. They are separate from actual net P&L.
    """
    records = {}
    for row in frame.to_dict("records"):
        key = (row.get("symbol"), timestamp(row["timestamp"]))
        records[key] = None if key in records else row  # duplicates invalidate the window
    for trade in trades:
        horizon = int(trade.get("horizon_minutes") or 0)
        if horizon not in (3, 5, 10, 20, 30, 45, 60) or not trade.get("identity_verified") or has_synthetic_options(trade):
            continue
        start = timestamp(trade["entry_ts"])
        if start.second or start.microsecond:
            continue  # minute data cannot reconstruct a partial entry candle
        stamps = pd.date_range(start, periods=horizon, freq="min")
        rows = [records.get((trade["symbol"], t)) for t in stamps]
        result = {"version": VERSION, "scope": outcome_scope(trade), "entry_at": start.isoformat(),
                  "observed_at": (start+pd.Timedelta(minutes=horizon)).isoformat(),
                  "direction": None, "barrier": None, "status": "DATA_UNAVAILABLE",
                  "reason": "Complete fixed-horizon index/contract observations required",
                  "population": "Executed replay trades only; not all market opportunities",
                  "barrier_basis": "Original fixed premium stop/target; excludes adaptive exits and fees",
                  "direction_basis": "Index open at entry to horizon close; flat band +/-0.02%"}
        trade["outcome_evidence"] = result
        if any(row is None for row in rows) or stamps[-1].date() != start.date() or stamps[-1].strftime("%H:%M") >= "15:30":
            continue
        index_prices = [float(rows[0]["open"]), float(rows[-1]["close"])]
        if not all(math.isfinite(v) and v > 0 for v in index_prices):
            continue
        move = index_prices[1]/index_prices[0]-1
        result.update(direction="UP" if move > .0002 else "DOWN" if move < -.0002 else "FLAT", index_return=move)
        stop = float(trade.get("initial_stop", trade.get("stop", 0)))
        target = float(trade.get("target", 0))
        if not 0 < stop < float(trade["entry"]) < target:
            continue
        barrier = "NEITHER"
        for row in rows:
            options = [q for q in row.get("option_quotes", []) if q.get("contract_id") == trade.get("contract_id")]
            if len(options) != 1:
                barrier = None; break
            q = options[0]
            if has_synthetic_options(q) or not q.get("identity_verified") or any(q.get(k) != trade.get(k) for k in ("expiry", "strike", "option_type", "lot_size")):
                barrier = None; break
            values = [q.get(k) for k in ("open", "high", "low", "close")]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values):
                barrier = None; break
            o, h, l, c = values
            if h < max(o, c) or l > min(o, c):
                barrier = None; break
            if o <= stop:
                barrier = "STOP_FIRST"; break
            if o >= target:
                barrier = "TARGET_FIRST"; break
            if l <= stop and h >= target:
                barrier = "AMBIGUOUS"; break
            if l <= stop:
                barrier = "STOP_FIRST"; break
            if h >= target:
                barrier = "TARGET_FIRST"; break
        result.update(barrier=barrier, status="OBSERVED_CANDLES" if barrier else "PARTIAL",
                      reason="Minute-candle outcome; same-bar order remains ambiguous" if barrier else result["reason"])


def evidence_records(report):
    """Only completed verified reports contribute. Repeated reports share an economic key."""
    if report.get("quality") != "verified" or report.get("status") not in (None, "complete") or report.get("issues") or report.get("partial") or report.get("unresolved") or report.get("unresolved_positions") or report.get("learning_eligible") is False or report.get("estimation") or has_synthetic_options(report):
        return []
    from .ai import training_gate_results
    output = []
    for t in report.get("trades", []):
        e = t.get("outcome_evidence") or {}
        if e.get("version") != VERSION or e.get("direction") is None or not all(training_gate_results(report, t).values()):
            continue
        try:
            times = [timestamp(e["observed_at"]), timestamp(t["exit_ts"]), timestamp(t.get("outcome_observed_at", t["exit_ts"])), timestamp(t["entry_ts"])]
            if any(pd.isna(t) for t in times) or times[3] >= times[1]:
                continue
            available = max(times[:3])
        except (KeyError, TypeError, ValueError):
            continue
        identity = [t.get(k) for k in ("symbol", "contract_id", "entry_ts", "entry", "initial_stop", "target", "horizon_minutes", "strategy_version", "exit_policy")]
        key = hashlib.sha256(json.dumps(identity, default=str).encode()).hexdigest()
        output.append(("market_outcomes", key, {**e, "id": key, "source_report": report.get("run_id"),
                                               "available_at": available.isoformat(),
                                               "actual_net_positive": t.get("pnl", 0) > 0,
                                               "report_quality": "verified"}))
    return output


def frequency(count, n):
    # Wilson interval, with at most one example per session to limit within-day clustering.
    z = 1.96; p = count/n; d = 1+z*z/n
    center = (p+z*z/(2*n))/d
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return {"estimate": p, "low": max(0, center-half), "high": min(1, center+half)}


def summarize_outcomes(records, scope, now):
    now = timestamp(now)
    matched = []
    for r in records:
        if r.get("version") != VERSION or r.get("report_quality") != "verified":
            continue
        if any(r.get("scope", {}).get(k) != scope.get(k) for k in SCOPE):
            continue
        try:
            times = [timestamp(r["observed_at"]), timestamp(r["available_at"]), timestamp(r["entry_at"])]
            if any(pd.isna(t) for t in times) or max(times[:2]) >= now or times[0] <= times[2]:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        matched.append(r)
    sessions = {}
    for row in sorted(matched, key=lambda r: (r["entry_at"], r["id"])):
        sessions.setdefault(str(timestamp(row["entry_at"]).date()), row)
    rows = list(sessions.values())
    n = len(rows)
    counts = Counter(r.get("barrier") or "MISSING" for r in rows)
    result = {"version": VERSION, "scope": scope, "status": "INSUFFICIENT_EVIDENCE",
              "sessions": n, "samples": n, "matching_records": len(matched), "minimum_sessions": MIN_SESSIONS,
              "authority": "RESEARCH_ONLY", "calibrated": False, "estimates": {}, "barrier_counts": dict(counts),
              "method": "First matching executed trade per session; 95% Wilson intervals",
              "reason": f"Need {MIN_SESSIONS} distinct completed sessions in this exact scope",
              "population": "Executed replay trades only; not a forecast for every market minute"}
    if n < MIN_SESSIONS:
        return result
    estimates = {name: frequency(sum(r.get("direction") == name for r in rows), n) for name in ("UP", "DOWN", "FLAT")}
    estimates["NET_PROFIT"] = frequency(sum(r.get("actual_net_positive") is True for r in rows), n)
    if not counts["AMBIGUOUS"] and not counts["MISSING"]:
        estimates.update({name: frequency(counts[name], n) for name in ("TARGET_FIRST", "STOP_FIRST", "NEITHER")})
    return {**result, "status": "EMPIRICAL_RESEARCH", "estimates": estimates,
            "reason": "Historical frequencies, not a calibrated next-trade forecast",
            "barrier_reason": "Ambiguous or missing paths: barrier probabilities withheld" if counts["AMBIGUOUS"] or counts["MISSING"] else "Original premium barriers only; actual exits may occur earlier"}
