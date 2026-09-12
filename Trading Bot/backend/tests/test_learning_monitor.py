"""Isolated synthetic evidence tests, never performance evidence."""
import copy
from types import SimpleNamespace
from datetime import timedelta
from app.ai import LearningService
from app.store import Store
from app.learning_monitor import LearningMonitor, build_evidence
from app.learning_validation import replay_evidence
from tests.test_adaptive_learning import trades


def test_rejected_attempt_is_not_learning_or_deployment(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.put_record("ml_runs", "attempt", {"run_id": "attempt", "models": [
        {"scope": "NIFTY|orb-retest-v1|exit", "status": "INSUFFICIENT_SESSIONS"}]})
    result = build_evidence(store, {}, {})
    nifty = next(r for r in result["agents"] if r["id"] == "NIFTY / Opening-range retest")
    sensex = next(r for r in result["agents"] if r["id"] == "SENSEX / Opening-range retest")
    assert nifty["training_attempts"] == 1 and nifty["fitted_candidates"] == 0
    assert sensex["status"] == "NO_TRAINING_EVIDENCE"
    assert not result["self_improvement_proven"]


def test_saved_policy_is_not_active_policy(tmp_path):
    store = Store(tmp_path / "audit.db")
    store.record_learning([], [{"agent": "Setup", "version": 2, "updated_at": "2026-01-01",
                               "policy": {"version": 2, "validation_status": "PROMOTED"}}])
    result = build_evidence(store, {}, {})
    row = next(r for r in result["agents"] if r["id"] == "Setup")
    assert row["saved_policy_version"] == 2 and row["active_policy_version"] is None
    assert row["status"] == "FIXED_RULES"


def test_monitor_restart_does_not_claim_old_heartbeat_is_live(tmp_path):
    store = Store(tmp_path / "audit.db")
    engine = SimpleNamespace(ml_frozen={"models": {}}, pipeline=SimpleNamespace(policies={}))
    monitor = LearningMonitor(store, engine, LearningService(store), tmp_path / ".env")
    monitor.scan()
    assert monitor.status()["stale"]
    restarted = LearningMonitor(store, engine, LearningService(store), tmp_path / ".env")
    assert restarted.status()["checked_at"] is None
    assert store.get_record("learning_monitor", "latest")["checked_at"]


def test_small_research_dataset_cannot_lower_its_own_gates(tmp_path):
    service = LearningService(Store(tmp_path / "small.db"))
    rows = trades()[:72]
    for t in rows:
        t["quality"] = "research_net"
    result = service.train({"quality": "research_net", "trades": rows}, "tiny")
    assert result["models"][0]["status"] == "INSUFFICIENT_SESSIONS"
    assert not service.store.list_records("ml_models")


def test_profitable_research_or_missing_costs_cannot_pass_replay():
    baseline = {"quality": "verified", "trades": trades()[-120:]}
    candidate = {"quality": "research_net", "trades": [t for t in trades()[-120:] if t["pnl"] > 0]}
    assert not replay_evidence(candidate, baseline, "2025-01-01", "2025-12-31")["passed"]
    candidate["quality"] = "verified"
    candidate["trades"][0]["costs"] = None
    assert not replay_evidence(candidate, baseline, "2025-01-01", "2025-12-31")["passed"]


def test_changed_exit_name_cannot_reuse_same_symbol_holdout(tmp_path):
    service = LearningService(Store(tmp_path / "reuse.db"))
    service.train({"quality": "verified", "trades": trades()}, "first")
    changed = copy.deepcopy(trades())
    for row in changed:
        row["exit_policy"] = "renamed-exit"
    result = service.train({"quality": "verified", "trades": changed}, "second")
    assert result["models"][0]["status"] == "HOLDOUT_ALREADY_USED"


def test_failed_fit_still_consumes_holdout(tmp_path, monkeypatch):
    from app.ai import MLTradeQualityModel
    service = LearningService(Store(tmp_path / "failed.db"))
    def fail(*args):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(MLTradeQualityModel, "fit", fail)
    import pytest
    with pytest.raises(RuntimeError):
        service.train({"quality": "verified", "trades": trades()}, "failed")
    result = service.train({"quality": "verified", "trades": trades()}, "retry")
    assert result["models"][0]["status"] == "HOLDOUT_ALREADY_USED"


def test_two_connections_cannot_reserve_same_symbol_holdout(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / "concurrent.db"
    stores = [Store(path), Store(path)]
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda i: stores[i].reserve_ml_holdout(
            f"NIFTY|variant-{i}|exit", "2025-01-01", "2025-02-01", str(i)), [0, 1]))
    assert sorted(outcomes) == [False, True]


def test_monitor_history_changes_only_with_evidence(tmp_path):
    store = Store(tmp_path / "audit.db")
    engine = SimpleNamespace(ml_frozen={"models": {}}, pipeline=SimpleNamespace(policies={}))
    monitor = LearningMonitor(store, engine, LearningService(store), tmp_path / ".env")
    first = monitor.scan()
    assert monitor.scan()["evidence_id"] == first["evidence_id"]
    assert len(store.list_records("learning_monitor_history")) == 1
    engine.ml_frozen = {"models": {"NIFTY|orb-retest-v1|exit": "missing-model"}}
    new = monitor.scan()
    assert new["evidence_id"] != first["evidence_id"]
    row = next(r for r in new["agents"] if r["id"] == "NIFTY / Opening-range retest")
    assert row["status"] == "ACTIVE_VALIDATION_MISSING"
    assert len(store.list_records("learning_monitor_history")) == 2


def test_sdk_agent_reads_evidence_and_reloads_key(tmp_path, monkeypatch):
    """Exercise the real SDK Runner and tool loop with a deterministic provider stub."""
    import asyncio
    import agents
    import openai
    from agents import Model, ModelResponse
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
    from app.learning_monitor import explain_evidence

    captured = []
    original = openai.AsyncOpenAI
    def client_factory(**kwargs):
        captured.append(kwargs["api_key"])
        return original(**kwargs)
    monkeypatch.setattr(openai, "AsyncOpenAI", client_factory)

    class EvidenceModel(Model):
        def __init__(self): self.calls = 0
        async def get_response(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                output = [ResponseFunctionToolCall(id="call-1", call_id="call-1", name="read_learning_evidence", arguments="{}", type="function_call")]
            else:
                output = [ResponseOutputMessage(id="answer", type="message", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text="Improvement remains unproven.", annotations=[])])]
            return ModelResponse(output=output, usage=Usage(), response_id=None)
        async def stream_response(self, *args, **kwargs):
            raise NotImplementedError
            yield
    monkeypatch.setattr(agents, "OpenAIChatCompletionsModel", lambda **kwargs: EvidenceModel())
    monkeypatch.setattr(agents, "OpenAIResponsesModel", lambda **kwargs: EvidenceModel())
    path = tmp_path / ".env"
    for value in ("test-key-first", "test-key-replacement"):
        path.write_text(f"OPENROUTER_API_KEY={value}\nOPENROUTER_MODEL=test-model\n")
        result = asyncio.run(explain_evidence({"self_improvement_proven": False}, path))
        assert result["status"] == "AVAILABLE" and result["authority"] == "ADVISORY_ONLY"
    assert captured == ["test-key-first", "test-key-replacement"]
    path.write_text("LEARNING_MONITOR_PROVIDER=openai\nOPENAI_API_KEY=test-openai-key\n")
    result = asyncio.run(explain_evidence({"self_improvement_proven": False}, path))
    assert result["status"] == "AVAILABLE" and result["provider"] == "openai"
    assert captured[-1] == "test-openai-key"


def test_new_daily_budget_and_net_profit_target():
    from app.config import Settings
    from app.risk import PlanRiskPolicy
    settings = Settings(_env_file=None, daily_loss_limit_rupees=800, hard_daily_halt_rupees=800,
                        max_trade_risk_rupees=600, max_correlated_risk_rupees=600,
                        planned_daily_loss_rupees=600, emergency_execution_reserve_rupees=200,
                        daily_profit_target=1000, daily_profit_target_basis="net")
    policy = PlanRiskPolicy.from_settings(settings)
    assert policy.loss_allocation + policy.emergency_reserve == 800
    assert policy.remaining({"loss_spend": 250}, open_risk=100) == 250
    assert not policy.target_reached(1020, 980)
    assert policy.target_reached(1040, 1000)
    assert not policy.target_reached(2000, None)


def test_net_profit_lock_uses_broker_liquidation_after_costs(tmp_path):
    from dataclasses import replace
    from tests.test_paper import plan_account
    broker, store, clock = plan_account(tmp_path)
    broker.policy = replace(broker.policy, gross_target=1000, target_basis="net", loss_allocation=600)
    broker.state["loss_ledger"]["gross_realized"] = 1020
    broker.state["cash"] = broker.state["session_start_equity"] + 980
    broker.mark({}, clock["now"])
    assert not broker.state["loss_ledger"]["lock_reason"]
    broker.state["cash"] += 20
    broker.mark({}, clock["now"])
    assert broker.state["loss_ledger"]["lock_reason"] == "NET_PROFIT_LOCK"
