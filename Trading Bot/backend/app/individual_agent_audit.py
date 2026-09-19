"""Deterministic audit of the architecture agents.

This module is deliberately independent of the LLM advisory path.  It treats
all agent output as evidence and never gives an agent order or risk authority.
The audit distinguishes activity, learning attempts, validation, deployment and
forward improvement, and records why a claim is blocked by overfitting risk.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from .learning_validation import MIN_DAYS, MIN_TEST, MIN_TRAIN, VERSION


ARCHITECTURE_AGENT_SPECS = (
    {"id": "Regime Agent", "aliases": ("Regime",), "kind": "intelligence", "learnable": True,
     "evidence": "completed bars, ADX/EMA/ATR regime label and regime-attributed outcomes"},
    {"id": "Directional Agent", "aliases": ("Directional", "Setup"), "kind": "intelligence", "learnable": True,
     "evidence": "spot/futures directional evidence and direction-attributed outcomes"},
    {"id": "Options Flow Agent", "aliases": ("Options Flow", "Option Selector"), "kind": "intelligence", "learnable": True,
     "evidence": "OI, change in OI, volume and strike-migration fields"},
    {"id": "Gamma Agent", "aliases": ("Gamma",), "kind": "intelligence", "learnable": True,
     "evidence": "gamma concentration/migration and asymmetric CE/PE evidence"},
    {"id": "Theta Agent", "aliases": ("Theta",), "kind": "intelligence", "learnable": True,
     "evidence": "decay-adjusted expected move versus option premium"},
    {"id": "IV Agent", "aliases": ("IV", "Volatility"), "kind": "intelligence", "learnable": True,
     "evidence": "IV/skew/volatility regime and premium-change evidence"},
    {"id": "Liquidity Agent", "aliases": ("Liquidity", "Option Selector"), "kind": "intelligence", "learnable": True,
     "evidence": "fresh bid/ask, spread, depth and slippage evidence"},
    {"id": "Momentum Agent", "aliases": ("Momentum", "Confirmation"), "kind": "intelligence", "learnable": True,
     "evidence": "multi-timeframe acceleration/deceleration evidence"},
    {"id": "Structure Agent", "aliases": ("Structure", "Confirmation"), "kind": "intelligence", "learnable": True,
     "evidence": "VWAP, EMA, support/resistance and opening-structure evidence"},
    {"id": "News/Event Agent", "aliases": ("News/Event", "Calendar and Event", "Event"), "kind": "event", "learnable": True,
     "evidence": "timestamped official/event-risk source and severity"},
    {"id": "Adversarial Agent", "aliases": ("Adversarial", "DevilsAdvocateAgent"), "kind": "debate", "learnable": True,
     "evidence": "recorded invalidation challenge for every proposed trade"},
    {"id": "Loss Investigator", "aliases": ("Loss Investigator",), "kind": "learning", "learnable": True,
     "evidence": "loss forensic record and classified primary/secondary cause"},
    {"id": "Risk Sentinel", "aliases": ("Risk", "Risk Sentinel"), "kind": "control", "learnable": False,
     "evidence": "deterministic veto decisions; this role must never learn"},
    {"id": "Orchestrator", "aliases": ("Orchestrator", "Option Selector"), "kind": "control", "learnable": True,
     "evidence": "candidate-to-CALL/PUT/WAIT/EXIT decision with veto-aware rationale"},
)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _stamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed
    except (TypeError, ValueError):
        return None


def _day(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        stamp = _stamp(row.get(key))
        if stamp:
            return stamp.date().isoformat()
    return None


def _matches_agent(row: dict[str, Any], aliases: tuple[str, ...]) -> bool:
    if row.get("agent") in aliases:
        return True
    contexts = row.get("agent_contexts") or {}
    return any(alias in contexts for alias in aliases)


def _model_rows(models: list[dict[str, Any]], aliases: tuple[str, ...]) -> list[dict[str, Any]]:
    result = []
    for model in models:
        scope = str(model.get("scope", ""))
        agent = str(model.get("agent", ""))
        if any(alias.lower() in scope.lower() or alias.lower() == agent.lower() for alias in aliases):
            result.append(model)
    return result


def _overfitting_gate(models: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a conservative gate; absence of evidence is never a pass."""
    reasons: list[str] = []
    if not models:
        return {"status": "NOT_ASSESSED", "passed": False,
                "reasons": ["No candidate model has been recorded for this agent."],
                "version": VERSION}
    for model in models:
        checks = model.get("overfitting_checks") or {}
        if checks.get("version") != VERSION:
            reasons.append("Model was not evaluated by the current overfitting guard.")
        if checks.get("passed") is not True:
            reasons.append("Model overfitting checks did not pass.")
        if model.get("status") in {"HOLDOUT_ALREADY_USED", "REJECTED", "INSUFFICIENT_SESSIONS", "FILTER_VALIDATED_REPLAY_REQUIRED"}:
            reasons.append(f"Model status {model.get('status')} is not promotable.")
        if not model.get("dataset_fingerprint"):
            reasons.append("Input dataset fingerprint is missing.")
        train = model.get("train_trades")
        test = model.get("test_trades")
        if train is not None and int(train) < MIN_TRAIN:
            reasons.append(f"Training sample is below {MIN_TRAIN} trades.")
        if test is not None and int(test) < MIN_TEST:
            reasons.append(f"Holdout sample is below {MIN_TEST} trades.")
        gap = model.get("holdout_brier_gap")
        if _finite(gap) and float(gap) > 0.10:
            reasons.append("Holdout calibration gap is greater than 0.10.")
    # A repeated attempt over a previously used holdout is a direct overfit risk.
    if any(m.get("status") == "HOLDOUT_ALREADY_USED" for m in models):
        reasons.append("At least one candidate reused a previously examined holdout.")
    if any(not r.get("dataset_fingerprint") for r in runs if r.get("models")):
        reasons.append("A related training run lacks an input fingerprint.")
    if reasons:
        return {"status": "BLOCKED", "passed": False, "reasons": sorted(set(reasons)), "version": VERSION}
    return {"status": "PASS", "passed": True, "reasons": [], "version": VERSION}


def _loss_investigation(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify losses only when the record contains the relevant evidence."""
    losses = [e for e in episodes if _finite(e.get("pnl")) and float(e["pnl"]) < 0]
    categories = Counter()
    records = []
    for episode in losses:
        reasons = str(episode.get("reason") or episode.get("exit_reason") or "").upper()
        spread = episode.get("spread") or episode.get("spread_pct")
        holding = episode.get("holding_minutes")
        if any(token in reasons for token in ("STALE", "LIQUID", "SLIPPAGE", "DEPTH")) or (_finite(spread) and float(spread) > 0.02):
            primary = "LIQUIDITY_OR_SLIPPAGE"
        elif any(token in reasons for token in ("INVALID", "FALSE_BREAK", "THESIS")):
            primary = "SETUP_OR_DIRECTION"
        elif _finite(holding) and float(holding) <= 3:
            primary = "LATE_OR_PREMATURE_ENTRY"
        elif episode.get("option_atr") is not None and episode.get("underlying_move") is not None:
            primary = "PREMIUM_DECAY_OR_VOLATILITY"
        else:
            primary = "UNCLASSIFIED"
        categories[primary] += 1
        records.append({"trade_id": episode.get("id"), "primary": primary,
                        "evidence_complete": primary != "UNCLASSIFIED",
                        "status": "HYPOTHESIS_ONLY"})
    return {"losses": len(losses), "classified": sum(v for k, v in categories.items() if k != "UNCLASSIFIED"),
            "categories": dict(categories), "records": records[-100:],
            "status": "EVIDENCE_COLLECTING" if losses else "NO_LOSSES"}


def audit_individual_agents(store, *, deployed: dict[str, Any] | None = None,
                            forward: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit every architecture role using only durable project evidence."""
    deployed = deployed or {}
    forward = forward or {}
    events = store.list_records("events", 20000)
    episodes = store.list_records("episodes", 10000)
    runs = store.list_records("ml_runs", 10000)
    models = store.list_records("ml_models", 10000)
    learning = store.learning_snapshot()
    ledger = learning.get("history", [])
    selections = store.list_records("strategy_selections", 10000)
    days_all = {_day(row, "timestamp", "entry_ts", "exit_ts", "recorded_at") for row in [*events, *episodes]}
    days_all.discard(None)
    rows = []
    for spec in ARCHITECTURE_AGENT_SPECS:
        aliases = tuple(spec["aliases"])
        event_rows = [row for row in events if _matches_agent(row, aliases)]
        outcome_rows = [row for row in episodes if _matches_agent(row, aliases)]
        if spec["id"] == "Loss Investigator":
            # Loss analysis is attributed to every closed losing episode even
            # when the execution record predates an explicit agent_contexts
            # field.  Classification remains hypothesis-only until replay.
            outcome_rows = [row for row in episodes if _finite(row.get("pnl")) and float(row["pnl"]) < 0]
        learning_rows = [row for row in ledger if row.get("agent") in aliases or row.get("agent") == spec["id"]]
        model_rows = _model_rows(models, aliases)
        run_rows = [run for run in runs if any(_model_rows(run.get("models", []), aliases))]
        decision_days = {_day(row, "timestamp", "entry_ts", "exit_ts") for row in [*event_rows, *outcome_rows]}
        decision_days.discard(None)
        overfit = _overfitting_gate(model_rows, run_rows)
        active_ids = [key for key in deployed if any(alias.lower() in key.lower() for alias in aliases)]
        forward_tagged = [row for row in outcome_rows if row.get("ml_quality", {}).get("model_id") in active_ids]
        if not spec["learnable"]:
            status = "FIXED_NON_LEARNABLE"
            reason = "Risk veto logic is deterministic and cannot be learned or overridden."
        elif overfit["status"] == "BLOCKED":
            status = "BLOCKED_OVERFITTING"
            reason = overfit["reasons"][0]
        elif active_ids and forward.get("status") == "COMPLETE" and forward.get("self_improvement_proven") and forward_tagged:
            status = "SELF_IMPROVEMENT_PROVEN"
            reason = "Current validation guard, deployment and independent forward comparison all passed."
        elif active_ids:
            status = "DEPLOYED_FORWARD_UNPROVEN"
            reason = "A model is active, but independent forward improvement is not proven."
        elif model_rows or learning_rows:
            status = "LEARNING_ATTEMPTED"
            reason = "Training or policy evidence exists, but deployment and forward improvement are not proven."
        elif event_rows or outcome_rows:
            status = "EVIDENCE_COLLECTING"
            reason = "Decisions or outcomes are recorded; enough independent evidence for learning is not present."
        else:
            status = "NO_EVIDENCE"
            reason = "No durable, agent-attributed decisions or outcomes were recorded."
        eligible = len(outcome_rows) >= MIN_TEST and len(decision_days) >= MIN_DAYS and all(
            row.get("learning_eligible") is not False and not row.get("estimated_exit") for row in outcome_rows)
        rows.append({"id": spec["id"], "kind": spec["kind"], "learnable": spec["learnable"],
                     "required_evidence": spec["evidence"], "status": status,
                     "self_improvement_proven": status == "SELF_IMPROVEMENT_PROVEN",
                     "decision_count": len(event_rows), "outcome_count": len(outcome_rows),
                     "learning_attempts": len(learning_rows), "candidate_models": len(model_rows),
                     "active_model_ids": active_ids, "forward_tagged_episodes": len(forward_tagged),
                     "observed_sessions": len(decision_days), "learning_eligible": eligible,
                     "overfitting": overfit, "reason": reason,
                     "last_evidence_at": max((row.get("timestamp") or row.get("exit_ts") or row.get("recorded_at") or "" for row in [*event_rows, *outcome_rows, *learning_rows]), default=None)})
    loss = _loss_investigation(episodes)
    overfit_rows = [row for row in rows if row["overfitting"]["status"] == "BLOCKED"]
    if overfit_rows:
        overfit_status = "BLOCKED"
    elif any(row["overfitting"]["status"] == "PASS" for row in rows):
        overfit_status = "PASSED_FOR_RECORDED_CANDIDATES"
    else:
        overfit_status = "NOT_ASSESSED"
    return {"version": VERSION, "agents": rows, "loss_investigation": loss,
            "overfitting_status": overfit_status, "self_improvement_proven": any(row["self_improvement_proven"] for row in rows),
            "independent_sessions": len(days_all),
            "principles": ["Activity is not learning.", "Learning is not deployment.",
                           "Deployment is not forward improvement.", "Risk Sentinel is never learned.",
                           "Loss research continues without loss chasing."],
            "authority": "AUDIT_ONLY_NO_ORDER_OR_RISK_AUTHORITY"}
