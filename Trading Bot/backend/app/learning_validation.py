"""Fixed research gates. Passing these gates never proves absence of overfitting."""
import math
from collections import defaultdict
from statistics import NormalDist, mean, stdev

VERSION = "learning_guard_v1"
MIN_TRAIN = 60
MIN_TEST = 30
MIN_DAYS = 34


def replay_evidence(candidate, baseline, start, end, trials=1):
    reasons = []
    daily = []
    for report in (candidate, baseline):
        if (report.get("quality") != "verified" or report.get("issues") or report.get("partial")
                or report.get("unresolved_positions") or report.get("unresolved")
                or report.get("status", "complete") != "complete"):
            reasons.append("Complete verified full-account replay required")
        totals = defaultdict(float)
        rows = report.get("trades", [])
        if len(rows) < MIN_TEST:
            reasons.append("At least 30 completed trades required in each replay")
        for trade in rows:
            day = str(trade.get("entry_ts", ""))[:10]
            try:
                pnl, gross, costs = (float(trade[k]) for k in ("pnl", "gross_pnl", "costs"))
                valid = all(math.isfinite(x) for x in (pnl, gross, costs)) and costs >= 0 and abs(pnl - gross + costs) < .01
            except (KeyError, TypeError, ValueError):
                valid = False
            if not valid or not start <= day <= end or str(trade.get("exit_ts", ""))[:10] > end:
                reasons.append("Invalid net-cost outcome or outcome outside the holdout")
                continue
            totals[day] += pnl
        daily.append(totals)
    coverage = [{str(d.get("date", ""))[:10] for d in r.get("daily", [])} or set(totals)
                for r, totals in zip((candidate, baseline), daily)]
    if coverage[0] != coverage[1] or any(not start <= day <= end for days in coverage for day in days):
        reasons.append("Candidate and baseline session coverage must match within the holdout")
    days = sorted(set(daily[0]) | set(daily[1]))
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
