"""Read models for reports: retain audit data without presenting partial profit as complete."""
import math
from ..provenance import reviewed_report


def report_view(original):
    report = dict(reviewed_report(original))
    status = report.get("status")
    quality = report.get("quality")
    complete = status in {"complete", "research_complete", "scenario_complete"}
    allowed = complete and quality in {"verified", "research", "research_net", "estimated_scenario"} and not report.get("unresolved")
    daily = report.get("daily") or []
    dates = sorted({str(row.get("date")) for row in daily if row.get("date")})
    coverage = report.get("coverage") or []
    blockers = []
    if status == "invalidated": blockers.append("Synthetic option history invalidates this report's returns and learning claims.")
    elif not complete: blockers.append("The requested replay did not complete with sufficient evidence. Partial observations are retained for inspection.")
    if report.get("unresolved"): blockers.append(f"{len(report['unresolved'])} positions have no trustworthy exit.")
    for key, label in (("missing_index_minutes", "missing index minutes"), ("missing_or_ambiguous_atm_minutes_by_side", "missing/ambiguous ATM minutes by side"), ("conflicting_candles", "conflicting candles")):
        count = sum(int(c.get(key) or 0) for c in coverage)
        if count: blockers.append(f"{count:,} {label} recorded in source coverage.")
    m = report.get("metrics") or {}
    finite = lambda x: isinstance(x, (int, float)) and math.isfinite(x)
    if allowed and quality != "research" and not finite(m.get("total_pnl")):
        allowed = False
        blockers.append("The report does not establish a finite net total.")
    report["presentation"] = {
        "performance_available": bool(allowed),
        "evidence_label": "Contract-candle simulation" if quality == "verified" else "Estimated net research" if quality == "research_net" else "Gross research" if quality == "research" else "Invalidated evidence" if status == "invalidated" else "Incomplete evidence",
        "observed_from": dates[0] if dates else None, "observed_to": dates[-1] if dates else None,
        "observed_sessions": len(dates), "requested_from": report.get("config", {}).get("from"), "requested_to": report.get("config", {}).get("to"),
        "blockers": blockers, "full_exchange_calendar_verified": False,
        "strategy_scope": report.get("strategy_mode") or report.get("strategy_version") or report.get("config", {}).get("strategy_version") or "Unspecified saved strategy",
    }
    if quality=="estimated_scenario":
        report["presentation"]["evidence_label"]="Estimated-data scenario · excluded from learning"
    # Legacy net reports inherited the gross-only assumption; reconcile the display
    # with the recorded cost model, without changing the saved original report.
    if quality == "research_net":
        report["assumptions"] = [s for s in report.get("assumptions", []) if "net P&L and charges are unavailable" not in s]
        report["assumptions"].append("Net results use estimated charges and current lot sizes. Dated fees, exact historical expiry identity and executable bid/ask depth remain unverified.")
    return report


def history_row(job, original=None):
    row = {key: job.get(key) for key in ("id", "status", "message", "progress", "config", "report_id", "updated_at")}
    if original:
        report = report_view(original)
        row["report"] = {key: report.get(key) for key in ("status", "quality", "created_at", "strategy_version", "strategy_mode", "presentation")}
        row["report"]["metrics"] = report.get("metrics", {}) if report["presentation"]["performance_available"] else {}
    return row
