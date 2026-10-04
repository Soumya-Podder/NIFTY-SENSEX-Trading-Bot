"""Controlled research-label tests; no production data or broker calls."""
from copy import deepcopy
import pandas as pd
import pytest
from app.outcome_evidence import VERSION, label_outcomes, outcome_scope, evidence_records, summarize_outcomes
from tests.test_adaptive_learning import trades


def sample():
    trade = {**trades()[0], "symbol": "NIFTY", "entry": 100., "stop": 105., "initial_stop": 90.,
             "target": 120., "horizon_minutes": 5, "regime": "TREND_UP", "option_type": "CALL", "identity_verified": True}
    q = {**trade, "open": 100., "high": 110., "low": 95., "close": 101.}
    start = pd.Timestamp(trade["entry_ts"])
    frame = pd.DataFrame([{"timestamp": start+pd.Timedelta(minutes=i), "symbol": "NIFTY", "open": 25000., "high": 25030., "low": 24990., "close": 25020., "option_quotes": [deepcopy(q)]} for i in range(5)])
    return trade, frame


@pytest.mark.parametrize("opening,high,low,expected", [(100, 125, 95, "TARGET_FIRST"), (100, 110, 85, "STOP_FIRST"), (100, 125, 85, "AMBIGUOUS"), (125, 130, 85, "TARGET_FIRST"), (85, 125, 80, "STOP_FIRST"), (100, 110, 95, "NEITHER")])
def test_original_barriers_and_ambiguity(opening, high, low, expected):
    t, f = sample()
    q = f.iloc[0].option_quotes[0]
    q.update(open=opening, high=high, low=low)
    label_outcomes(f, [t])
    e = t["outcome_evidence"]
    assert e["barrier"] == expected
    assert e["direction"] == "UP"
    assert e["observed_at"] == (pd.Timestamp(t["entry_ts"])+pd.Timedelta(minutes=5)).isoformat()
    assert e["scope"]["reward_multiple"] == 2.


def test_missing_duplicate_and_changed_identity_do_not_invent_outcomes():
    t, f = sample()
    label_outcomes(f.iloc[:4], [t])
    assert t["outcome_evidence"]["direction"] is None
    label_outcomes(pd.concat([f, f.iloc[[2]]]), [t])
    assert t["outcome_evidence"]["direction"] is None
    f.iloc[2].option_quotes[0]["expiry"] = "2099-01-01"
    label_outcomes(f, [t])
    assert t["outcome_evidence"]["barrier"] is None


def test_verified_report_gates_and_duplicate_report_identity():
    t, f = sample(); label_outcomes(f, [t])
    report = {"quality": "verified", "status": "complete", "trades": [t], "run_id": "a"}
    first = evidence_records(report)
    assert len(first) == 1
    assert evidence_records({**report, "run_id": "b"})[0][1] == first[0][1]
    assert not evidence_records({**report, "quality": "research_net"})
    assert not evidence_records({**report, "issues": ["gap"]})
    assert not evidence_records({**report, "partial": True})
    assert not evidence_records({**report, "trades": [{**t, "contract_id": "rolling:NIFTY"}]})
    assert summarize_outcomes([first[0][2]], first[0][2]["scope"], t["exit_ts"])["samples"] == 0
    assert summarize_outcomes([first[0][2]], first[0][2]["scope"], pd.Timestamp(t["exit_ts"])+pd.Timedelta(minutes=1))["samples"] == 1


def records():
    t, f = sample(); label_outcomes(f, [t])
    base = evidence_records({"quality": "verified", "status": "complete", "trades": [t]})[0][2]
    result = []
    for i, day in enumerate(pd.bdate_range("2025-01-01", periods=30)):
        start = day.tz_localize("Asia/Kolkata")+pd.Timedelta(hours=10)
        result.append({**deepcopy(base), "id": str(i), "entry_at": start.isoformat(), "observed_at": (start+pd.Timedelta(minutes=5)).isoformat(), "available_at": (start+pd.Timedelta(minutes=10)).isoformat(), "barrier": "TARGET_FIRST" if i < 18 else "STOP_FIRST"})
    return result


def test_scope_future_outcomes_and_distinct_day_requirement():
    data = records(); scope = data[0]["scope"]
    assert summarize_outcomes(data[:29], scope, "2026-01-01")["estimates"] == {}
    assert summarize_outcomes(data, {**scope, "symbol": "SENSEX"}, "2026-01-01")["samples"] == 0
    assert summarize_outcomes(data, scope, data[0]["observed_at"])["samples"] == 0
    assert summarize_outcomes([data[0]]*100, scope, "2026-01-01")["samples"] == 1
    result = summarize_outcomes(data+data, scope, "2026-01-01")
    assert result["samples"] == 30 and result["calibrated"] is False
    p = result["estimates"]["TARGET_FIRST"]
    assert p["estimate"] == .6 and 0 < p["low"] < .6 < p["high"] < 1
    data[0]["barrier"] = "AMBIGUOUS"
    result = summarize_outcomes(data, scope, "2026-01-01")
    assert "UP" in result["estimates"] and "TARGET_FIRST" not in result["estimates"]


def test_restart_restores_research_as_stale_without_starting_a_trader(tmp_path, monkeypatch):
    from tests.test_strategy_portfolio import portfolio_account
    from tests.test_market_structure import candles
    from app.market_structure import analyze_structure
    from app.portfolio_engine import MultiStrategyPaperEngine
    engine, broker, store, clock = portfolio_account(tmp_path, monkeypatch)
    snapshot = analyze_structure(candles(), "2026-09-25T09:45:00+05:30", "NIFTY")
    row = records()[0]
    store.save_bundle([("market_structure", "saved", snapshot), ("market_outcomes", row["id"], row)])
    restored = MultiStrategyPaperEngine(engine.settings, store, engine.gateway, broker)
    assert restored.status["market_structure"]["NIFTY"]["status"] == "STALE"
    estimate = restored.status["outcome_estimates"]["NIFTY"]
    assert estimate["source"] == "LAST_HISTORICAL_SCOPE" and estimate["samples"] == 1
    assert estimate["estimates"] == {} and estimate["calibrated"] is False
    assert not restored.threads and not restored.ml_frozen and broker.snapshot()["open_positions"] == 0
