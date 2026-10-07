"""Paper-only research learning. Estimated charges never become verified evidence."""
import hashlib
import json
import threading
from collections import Counter, defaultdict
from statistics import mean, stdev
from datetime import timedelta
import pandas as pd

from .ai import FEATURES, SCHEMA, MLTradeQualityModel, number
from .autonomous_policy import VERSION, STRATEGY_SPECS
from .risk import SIZING_VERSION
from .session import local_time

RESEARCH_VERSION = "autonomous-paper-learning-v1"
COLUMNS = (*FEATURES, "chain_pcr", "chain_oi_change_ratio", "zone_room_atr", "futures_above_vwap",
           "is_sensex", "holding_minutes", *("strategy_"+s["id"] for s in STRATEGY_SPECS))
MIN_TRAIN, MIN_TEST, MIN_DAYS = 60, 30, 34


def entry_context(signal):
    """Only inputs captured before entry, never exit P&L, MFE or future candles."""
    features = signal["entry_features"]
    position = signal.get("market_context", {}).get("positioning", {})
    changes = position.get("since_previous", {})
    total = (number(position.get("call_oi")) or 0)+(number(position.get("put_oi")) or 0)
    call, put = number(changes.get("call_oi_change")), number(changes.get("put_oi_change"))
    obstacle = signal.get("market_structure", {}).get("target_obstacle") or {}
    atr = number(signal.get("feature_row", {}).get("atr"))
    futures = signal.get("market_context", {}).get("futures", {})
    values = {"chain_pcr": number(position.get("pcr")),
              "chain_oi_change_ratio": (put-call)/total if call is not None and put is not None and total > 0 else None,
              "zone_room_atr": number(obstacle.get("distance_points"))/atr if atr and number(obstacle.get("distance_points")) is not None else None,
              "futures_above_vwap": int(futures.get("relation") == "ABOVE") if futures.get("status") == "OBSERVED" else None,
              "is_sensex": int(signal["symbol"] == "SENSEX"), "holding_minutes": signal["horizon_minutes"],
              **{"strategy_"+s["id"]: int(signal["strategy_id"] == s["id"]) for s in STRATEGY_SPECS}}
    features["values"].update(values)
    features["paper_policy_version"] = VERSION
    return features


def eligibility(trade):
    reasons = []
    if trade.get("portfolio_version") != VERSION: reasons.append("Different active paper policy")
    if trade.get("sizing_policy_version") != SIZING_VERSION: reasons.append("Different active sizing policy")
    if trade.get("source") != "paper_live_quotes" or trade.get("partial") or trade.get("estimated_exit"):
        reasons.append("Completed observed paper episode required")
    if not trade.get("identity_verified") or not trade.get("metadata_source") or not str(trade.get("security_id", "")).isdigit():
        reasons.append("Fixed contract metadata required")
    if not trade.get("entry_quote_observation_id") or not trade.get("exit_quote_observation_id"):
        reasons.append("Recorded entry and exit quote identities required")
    feature = trade.get("entry_features") or {}
    if feature.get("schema") != SCHEMA or feature.get("paper_policy_version") != VERSION or sum(number((feature.get("values") or {}).get(k)) is not None for k in FEATURES) < 6:
        reasons.append("Causal active-policy entry features required")
    try:
        entry, exit_at, seen, bar = (pd.Timestamp(v) for v in (trade["entry_ts"], trade["exit_ts"], feature["observed_at"], feature["bar_at"]))
        if any(v.tzinfo is None for v in (entry, exit_at, seen, bar)) or not bar+pd.Timedelta(minutes=1) <= seen <= entry <= exit_at:
            reasons.append("Feature timestamps must precede entry and outcome")
        gross, costs, net = (number(trade[k]) for k in ("gross_pnl", "costs", "pnl"))
        if any(v is None for v in (gross, costs, net)) or costs < 0 or abs(gross-costs-net) > .01:
            reasons.append("Reconciled recorded net-cost paper outcome required")
    except (KeyError, TypeError, ValueError): reasons.append("Missing causal timestamps or outcome")
    return reasons


def investigation(trade):
    loss = float(trade.get("pnl") or 0) < 0
    budget = float(trade.get("risk_rupees") or 0)
    category = "PROFITABLE_OUTCOME" if not loss else "PLANNED_TRADE_LOSS"
    if loss and budget > 0 and -float(trade["pnl"]) > budget+.01: category = "EXECUTION_OR_GAP_OVERRUN"
    elif loss and float(trade.get("mfe") or 0) > 0: category = "FAVOURABLE_MOVE_REVERSED"
    elif loss and trade.get("reason") == "TIME_EXIT": category = "MOVE_DID_NOT_DEVELOP"
    return {"trade_id": trade["id"], "category": category, "pnl": trade.get("pnl"), "exit_reason": trade.get("reason"),
            "planned_risk": budget, "mae": trade.get("mae"), "mfe": trade.get("mfe"),
            "status": "EVIDENCE_HYPOTHESIS", "authority": "RESEARCH_ONLY",
            "conclusion": "Observed outcome classification; it does not prove the cause or justify widening risk",
            "entry_features": trade.get("entry_features"), "specialist_agents": trade.get("specialist_agents", {})}


class PaperResearchLearning:
    def __init__(self, store):
        self.store = store
        self.frozen = {}
        self.training_lock = threading.Lock()

    def eligible(self):
        all_rows = self.store.list_records("episodes", 100000)
        rejected = Counter()
        rows = []
        for trade in all_rows:
            reasons = eligibility(trade)
            if reasons: rejected.update(reasons)
            else: rows.append(trade)
        return sorted(rows, key=lambda t: t["entry_ts"]), dict(rejected)

    def train(self, now):
        if not self.training_lock.acquire(blocking=False):
            return {"status": "TRAINING", "authority": "UNVALIDATED_PAPER_RESEARCH_ONLY"}
        try:
            return self._train(now)
        finally:
            self.training_lock.release()

    def _train(self, now):
        rows, rejected = self.eligible()
        # New outcomes trigger a new attempt; repeated polling is not learning.
        recorded = self.store.list_records("episodes", 100000)
        completed_through = str(local_time(now).date()) if local_time(now).strftime("%H:%M") >= "15:35" else str(local_time(now).date()-timedelta(days=1))
        fingerprint = hashlib.sha256(json.dumps([SIZING_VERSION, completed_through, sorted((t["id"], t.get("pnl")) for t in recorded)]).encode()).hexdigest()
        previous = self.store.get_record("paper_learning_state", VERSION, {})
        if previous.get("fingerprint") == fingerprint: return previous
        completed_rows = [t for t in rows if t["exit_ts"][:10] <= completed_through]
        days = sorted({t["entry_ts"][:10] for t in completed_rows})
        result = {"version": RESEARCH_VERSION, "sizing_policy_version": SIZING_VERSION, "fingerprint": fingerprint, "checked_at": now.isoformat(),
                  "eligible_outcomes": len(rows), "independent_days": len(days), "rejections": rejected,
                  "minimum_train": MIN_TRAIN, "minimum_holdout": MIN_TEST, "minimum_days": MIN_DAYS,
                  "status": "INSUFFICIENT_EVIDENCE", "authority": "UNVALIDATED_PAPER_RESEARCH_ONLY"}
        for trade in recorded:
            if trade.get("source") == "paper_live_quotes":
                self.store.put_record("paper_investigations", trade["id"], investigation(trade))
        if len(completed_rows) >= MIN_TRAIN+MIN_TEST and len(days) >= MIN_DAYS:
            cutoff = days[-max(10, len(days)//3)]
            candidates = self.store.list_records("paper_learning_candidates", 1000)
            consumed_through = max((c["validation_end"] for c in candidates if c.get("version") == RESEARCH_VERSION), default="")
            fresh_days = [d for d in days if d > consumed_through]
            if consumed_through:
                if len(fresh_days) < 10:
                    result.update(status="WAITING_FOR_NEW_HOLDOUT", fresh_holdout_days=len(fresh_days))
                    self.store.put_record("paper_learning_state", VERSION, result)
                    return result
                cutoff = max(cutoff, fresh_days[0])
            train = [t for t in completed_rows if t["entry_ts"][:10] < cutoff]
            holdout = [t for t in completed_rows if t["entry_ts"][:10] >= cutoff]
            labels = [int(t["pnl"] > 0) for t in train]
            if len(train) >= MIN_TRAIN and len(holdout) >= MIN_TEST and len(set(labels)) == 2:
                model = MLTradeQualityModel.fit([t["entry_features"] for t in train], labels, COLUMNS)
                predictions = [model.predict(t["entry_features"]) for t in holdout]
                selected = [t for t, p in zip(holdout, predictions) if p >= model.artifact["threshold"]]
                daily = defaultdict(float)
                for trade, probability in zip(holdout, predictions):
                    daily[trade["entry_ts"][:10]] += -trade["pnl"] if probability < model.artifact["threshold"] else 0
                paired = list(daily.values())
                lower = mean(paired)-1.96*stdev(paired)/len(paired)**.5 if len(paired) > 1 else float("-inf")
                stress_net = sum(t["pnl"]-t["costs"] for t in selected)
                passed = len(selected) >= MIN_TEST and len(selected) >= .5*len(holdout) and lower > 0 and stress_net > 0
                result.update(status="AWAITING_FULL_ACCOUNT_REPLAY" if passed else "HOLDOUT_REJECTED",
                    train_count=len(train), holdout_count=len(holdout), retained_count=len(selected),
                    paired_daily_lower_bound=lower, doubled_fee_net=stress_net)
                candidate = {**result, "id": fingerprint[:24], "artifact": model.artifact,
                    "policy_version": VERSION,
                    "training_end": max(t["exit_ts"] for t in train), "validation_start": cutoff, "validation_end": days[-1],
                    "paper_approved": False, "risk_authority": "NONE", "label": "completed_net_pnl_positive",
                    "validation_warning": "Post-hoc filtering is not a full-account replay; estimated fees are research evidence"}
                self.store.put_record("paper_learning_candidates", candidate["id"], candidate)
                result["candidate_id"] = candidate["id"]
        self.store.put_record("paper_learning_state", VERSION, result)
        return result

    def validate_replay(self, candidate, baseline, challenger, now):
        """Paper approval requires both paths through the same archived account simulation."""
        reasons = []
        if not self.valid_artifact(candidate): reasons.append("Active-policy feature schema or model artifact changed")
        if pd.Timestamp(candidate["training_end"]).date() >= pd.Timestamp(candidate["validation_start"]).date():
            reasons.append("Training overlaps the independent holdout")
        if not baseline.get("input_digest") or baseline.get("input_digest") != challenger.get("input_digest"):
            reasons.append("Baseline and challenger must use identical archived inputs")
        if not baseline.get("policy_settings_digest") or baseline.get("policy_settings_digest") != challenger.get("policy_settings_digest"):
            reasons.append("Baseline and challenger risk and execution settings differ")
        for report in (baseline, challenger):
            if report.get("status") != "research_complete" or report.get("issues") or report.get("unresolved_positions") or report.get("source") != "autonomous_observed_quote_replay":
                reasons.append("Complete observed quote replay required")
            if report.get("requested_start") != candidate["validation_start"] or report.get("requested_end") != candidate["validation_end"]:
                reasons.append("Independent holdout range changed")
            if report.get("coverage_summary", {}).get("full_sessions") is not True: reasons.append("Full market-session coverage required")
            if report.get("policy_version") != VERSION or len(report.get("trades", [])) < MIN_TEST: reasons.append("Active policy and at least 30 replay outcomes required")
            if report.get("sizing_policy_version") != SIZING_VERSION: reasons.append("Replay must use the active sizing policy")
        paired = [float(challenger.get("daily_pnl", {}).get(day, 0))-float(baseline.get("daily_pnl", {}).get(day, 0))
                  for day in sorted(set(baseline.get("daily_pnl", {})) | set(challenger.get("daily_pnl", {})))]
        lower = mean(paired)-1.96*stdev(paired)/len(paired)**.5 if len(paired) >= 10 else float("-inf")
        if lower <= 0: reasons.append("Independent full-account improvement lower bound is not positive")
        if float(challenger.get("net_pnl", 0))-float(challenger.get("estimated_charges", 0)) <= 0:
            reasons.append("Doubled-fee challenger result is not positive")
        if abs(float(challenger.get("max_drawdown", 0))) > abs(float(baseline.get("max_drawdown", 0))): reasons.append("Challenger drawdown worsened")
        candidate.update(status="PAPER_APPROVED_NEXT_SESSION" if not reasons else "REPLAY_REJECTED", paper_approved=not reasons,
                         replay_reasons=reasons, replay_lower_bound=lower, approved_at=now.isoformat(),
                         effective_on=str(local_time(now).date()+timedelta(days=1)))
        self.store.put_record("paper_learning_candidates", candidate["id"], candidate)
        return candidate

    @staticmethod
    def valid_artifact(candidate):
        artifact = candidate.get("artifact", {})
        n = len(COLUMNS)
        return (candidate.get("version") == RESEARCH_VERSION and candidate.get("policy_version") == VERSION
                and candidate.get("sizing_policy_version") == SIZING_VERSION
                and artifact.get("schema") == SCHEMA and artifact.get("features") == list(COLUMNS)
                and artifact.get("algorithm") == "regularized_logistic_regression" and artifact.get("threshold") == .55
                and artifact.get("label") == "completed_net_pnl_positive" and number(artifact.get("intercept")) is not None
                and all(len(artifact.get(k, [])) == size and all(number(v) is not None for v in artifact[k])
                        for k, size in (("medians", n), ("mean", n*2), ("scale", n*2), ("coef", n*2)))
                and all(number(v) > 0 for v in artifact["scale"]))

    def freeze(self, now):
        key = str(local_time(now).date())+":"+VERSION+":"+SIZING_VERSION
        frozen = self.store.get_record("paper_learning_sessions", key)
        if frozen is None:
            approved = [c for c in self.store.list_records("paper_learning_candidates", 1000)
                        if c.get("paper_approved") and c.get("status") == "PAPER_APPROVED_NEXT_SESSION"
                        and self.valid_artifact(c) and c.get("effective_on", "9999") <= key[:10]]
            chosen = max(approved, key=lambda c: c["approved_at"], default=None)
            frozen = {"session": key[:10], "models": {VERSION: chosen} if chosen else {},
                      "authority": "PAPER_ENTRY_FILTER_ONLY", "frozen_at": now.isoformat()}
            self.store.put_record("paper_learning_sessions", key, frozen)
        self.frozen = frozen
        return frozen

    def score(self, signal, frozen):
        feature = entry_context(signal)
        candidate = (frozen or {}).get("models", {}).get(VERSION)
        if not candidate: return {"allowed": True, "status": "BASELINE_PAPER_COLLECTION", "probability": None, "authority": "NO_MODEL_DEPLOYED"}
        probability = MLTradeQualityModel(candidate["artifact"]).predict(feature)
        threshold = candidate["artifact"]["threshold"]
        return {"allowed": probability >= threshold, "status": "PAPER_RESEARCH_FILTER", "probability": probability,
                "threshold": threshold, "model_id": candidate["id"], "label": "completed_net_pnl_positive",
                "authority": "PAPER_ONLY_UNVALIDATED_FOR_LIVE"}

    def status(self):
        return {**self.store.get_record("paper_learning_state", VERSION, {"status": "INSUFFICIENT_EVIDENCE", "eligible_outcomes": 0}),
                "active_models": list(self.frozen.get("models", {})), "frozen_session": self.frozen.get("session"),
                "candidates": [{k: v for k, v in c.items() if k != "artifact"} for c in self.store.list_records("paper_learning_candidates", 20)],
                "investigations": self.store.list_records("paper_investigations", 20),
                "live_eligible": False, "risk_changes_permitted": False}
