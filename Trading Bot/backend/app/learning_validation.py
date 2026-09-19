"""Fixed research gates. Passing these gates never proves absence of overfitting."""
import math
import pandas as pd
from collections import defaultdict
from statistics import NormalDist, mean, stdev
from .provenance import has_synthetic_options

VERSION = "learning_guard_v3"
MIN_TRAIN = 60
MIN_TEST = 30
MIN_DAYS = 34


def replay_evidence(candidate, baseline, start, end, trials=1):
    reasons = []
    daily = []
    coverage = []
    for report in (candidate, baseline):
        if has_synthetic_options(report):
            reasons.append("Synthetic option evidence is not eligible for promotion")
        if (report.get("quality") != "verified" or report.get("issues") or report.get("partial")
                or report.get("learning_eligible") is False or report.get("estimation")
                or report.get("unresolved_positions") or report.get("unresolved")
                or report.get("status", "complete") != "complete"):
            reasons.append("Complete verified full-account replay required")
        totals = defaultdict(float)
        identifiers = set()
        rows = report.get("trades", [])
        if len(rows) < MIN_TEST:
            reasons.append("At least 30 completed trades required in each replay")
        for trade in rows:
            try:
                entry, exit = (pd.Timestamp(trade[k]) for k in ("entry_ts", "exit_ts"))
                if pd.isna(entry) or pd.isna(exit): raise ValueError("Missing timestamp")
                entry = entry.tz_localize("Asia/Kolkata") if entry.tzinfo is None else entry.tz_convert("Asia/Kolkata")
                exit = exit.tz_localize("Asia/Kolkata") if exit.tzinfo is None else exit.tz_convert("Asia/Kolkata")
                day = str(entry.date())
                pnl, gross, costs = (float(trade[k]) for k in ("pnl", "gross_pnl", "costs"))
                valid = (all(math.isfinite(x) for x in (pnl, gross, costs)) and costs >= 0 and abs(pnl - gross + costs) < .01
                         and entry <= exit and entry.date() == exit.date() and start <= day <= end
                         and trade.get("learning_eligible") is not False and not trade.get("estimated_exit")
                         and trade.get("quality", "verified") == "verified")
            except (KeyError, TypeError, ValueError):
                valid = False
            identifier = trade.get("id")
            if not isinstance(identifier,str) or not identifier or identifier in identifiers:
                reasons.append("Unique completed trade identities required")
                valid = False
            elif identifier:
                identifiers.add(identifier)
            if not valid:
                reasons.append("Invalid net-cost outcome or outcome outside the holdout")
                continue
            totals[day] += pnl
        daily.append(totals)
        sessions = {}
        for row in report.get("daily", []):
            try:
                day = str(pd.Timestamp(row["date"]).date())
                value = float(row["pnl"])
                if not start <= day <= end or not math.isfinite(value) or day in sessions:
                    raise ValueError("Invalid session")
                sessions[day] = value
            except (KeyError, TypeError, ValueError):
                reasons.append("Unique finite daily account results within the holdout required")
        if not sessions or not set(totals).issubset(sessions):
            reasons.append("Explicit session coverage must include every completed trade")
        if any(abs(value-totals.get(day,0)) >= .01 for day,value in sessions.items()):
            reasons.append("Daily account results do not reconcile with completed net trades")
        coverage.append(set(sessions))
    if coverage[0] != coverage[1] or any(not start <= day <= end for days in coverage for day in days):
        reasons.append("Candidate and baseline session coverage must match within the holdout")
    # Include observed no-trade sessions; selecting only active days biases the comparison.
    days = sorted(coverage[0] | coverage[1])
    differences = [daily[0][d] - daily[1][d] for d in days]
    lower = None
    if len(days) < 10:
        reasons.append("At least 10 independent holdout sessions required")
    elif differences:
        # Conservative multiple-attempt correction; an approximation, not a guarantee.
        z = NormalDist().inv_cdf(1 - .05 / max(1, trials))
        lower = mean(differences) - z * stdev(differences) / math.sqrt(len(days))
        if lower <= 0:
            reasons.append("Paired daily improvement confidence bound is not positive")
    if sum(daily[0].values()) <= 0:
        reasons.append("Candidate net replay P&L must be positive")
    def drawdown(values):
        balance = peak = worst = 0
        for day in days:
            balance += values[day]
            peak = max(peak, balance)
            worst = max(worst, peak - balance)
        return worst
    if drawdown(daily[0]) > drawdown(daily[1]):
        reasons.append("Candidate daily drawdown is worse than baseline")
    return {"version": VERSION, "passed": not reasons, "reasons": sorted(set(reasons)),
            "paired_days": len(days), "improvement_lower_bound": lower, "attempts_corrected": trials,
            "limitation": "Daily normal approximation; serial dependence and unrecorded research trials remain risks. Forward paper evaluation required."}
