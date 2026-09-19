from app.individual_agent_audit import audit_individual_agents
from app.store import Store


def test_audit_is_explicit_about_empty_evidence_and_fixed_risk(tmp_path):
    audit = audit_individual_agents(Store(tmp_path / "audit.db"))
    regime = next(row for row in audit["agents"] if row["id"] == "Regime Agent")
    risk = next(row for row in audit["agents"] if row["id"] == "Risk Sentinel")
    assert regime["status"] == "NO_EVIDENCE"
    assert not regime["self_improvement_proven"]
    assert risk["status"] == "FIXED_NON_LEARNABLE"
    assert audit["overfitting_status"] == "NOT_ASSESSED"
    assert audit["authority"] == "AUDIT_ONLY_NO_ORDER_OR_RISK_AUTHORITY"


def test_activity_and_losses_do_not_count_as_learning(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.record_event({"id": "e1", "timestamp": "2026-01-02T09:20:00+05:30",
                        "agent": "Regime", "symbol": "NIFTY", "status": "PASS"})
    store.put_record("episodes", "loss-1", {
        "id": "loss-1", "entry_ts": "2026-01-02T09:20:00+05:30",
        "exit_ts": "2026-01-02T09:23:00+05:30", "pnl": -100,
        "reason": "LIQUIDITY_SLIPPAGE", "agent_contexts": {"Regime": "RANGE"},
        "learning_eligible": True,
    })
    audit = audit_individual_agents(store)
    regime = next(row for row in audit["agents"] if row["id"] == "Regime Agent")
    investigator = next(row for row in audit["agents"] if row["id"] == "Loss Investigator")
    assert regime["status"] == "EVIDENCE_COLLECTING"
    assert not regime["self_improvement_proven"]
    assert investigator["outcome_count"] == 1
    assert audit["loss_investigation"]["categories"]["LIQUIDITY_OR_SLIPPAGE"] == 1
    assert audit["loss_investigation"]["records"][0]["status"] == "HYPOTHESIS_ONLY"


def test_missing_current_overfit_guard_blocks_model(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.put_record("ml_models", "m1", {"id": "m1", "agent": "Regime",
                                          "scope": "Regime|v1", "status": "FITTED",
                                          "dataset_fingerprint": "data"})
    audit = audit_individual_agents(store)
    regime = next(row for row in audit["agents"] if row["id"] == "Regime Agent")
    assert regime["status"] == "BLOCKED_OVERFITTING"
    assert regime["overfitting"]["status"] == "BLOCKED"
    assert audit["overfitting_status"] == "BLOCKED"


def test_forward_improvement_requires_active_model_and_completed_comparison(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.put_record("ml_models", "m1", {
        "id": "m1", "agent": "Gamma", "scope": "Gamma|v1", "status": "FITTED",
        "dataset_fingerprint": "data", "train_trades": 80, "test_trades": 40,
        "overfitting_checks": {"version": "learning_guard_v3", "passed": True},
    })
    store.put_record("episodes", "e1", {
        "id": "e1", "entry_ts": "2026-01-02T09:20:00+05:30",
        "exit_ts": "2026-01-02T09:30:00+05:30", "pnl": 20,
        "agent_contexts": {"Gamma": "positive"}, "ml_quality": {"model_id": "Gamma|v1"},
        "learning_eligible": True,
    })
    audit = audit_individual_agents(store, deployed={"Gamma|v1": "m1"},
                                    forward={"status": "COMPLETE", "self_improvement_proven": True})
    gamma = next(row for row in audit["agents"] if row["id"] == "Gamma Agent")
    assert gamma["status"] == "SELF_IMPROVEMENT_PROVEN"
    assert audit["self_improvement_proven"]

