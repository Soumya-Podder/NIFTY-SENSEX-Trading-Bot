"""Synthetic fixtures test mechanics, never trading performance evidence."""
from datetime import datetime, timedelta
import copy
import json
import pytest
from app.ai import FEATURES, SCHEMA, LearningService, MLTradeQualityModel, scope
from app.adaptive_exit import VERSION, update_exit
from app.pipeline import plan_exit
from app.session import IST
from app.store import Store


def position():
    return {"entry": 100., "entry_ts": "2026-01-05T10:00:00+05:30", "stop": 90., "target": 140.,
            "qty": 10, "tick_size": .05, "entry_charges_remaining": 20., "option_atr": 10.,
            "exit_policy": VERSION, "option_type": "CALL", "horizon_minutes": 20}


def test_cost_covering_stop_and_restart_never_loosen():
    p = position()
    now = datetime(2026, 1, 5, 10, 1, tzinfo=IST)
    update_exit(p, 110., now, 20.)
    assert 104 < p["stop"] < 110
    restored = json.loads(json.dumps(p))
    update_exit(restored, 120., now+timedelta(seconds=2), 20.)
    assert restored["stop"] == 115
    update_exit(restored, 114., now+timedelta(seconds=4), 20.)
    assert restored["stop"] == 115
    assert plan_exit(restored, now, bid=114.) == "STOP"


def test_missing_option_atr_does_not_invent_trailing_volatility():
    p = position(); p["option_atr"] = None
    update_exit(p, 120., datetime(2026, 1, 5, 10, 1, tzinfo=IST), None)
    assert p["stop"] == 90
    assert "unavailable" in p["adaptive_data_status"]


def test_completed_stall_requires_contiguous_bars():
    start = datetime(2026, 1, 5, 10, 1, tzinfo=IST)
    p = position()
    for n in range(5):
        stamp = start+timedelta(minutes=n)
        update_exit(p, 103., stamp+timedelta(minutes=1), 20.,
                    {"timestamp": stamp.isoformat(), "high": 105. if n == 0 else 104., "low": 102.})
    assert plan_exit(p, start+timedelta(minutes=6), bid=103.) == "MOMENTUM_STALL"
    p = position()
    for n in (0, 1, 3, 4, 5):
        stamp=start+timedelta(minutes=n)
        update_exit(p, 103., stamp+timedelta(minutes=1), 20.,
                    {"timestamp": stamp.isoformat(), "high": 104., "low": 102.})
    assert not p.get("adaptive_exit_request")


def trades():
    result=[]
    start=datetime(2025, 1, 1, 10, tzinfo=IST)
    for day in range(100):
        for i in range(4):
            stamp=start+timedelta(days=day, minutes=20*i)
            quality = i != 0
            pnl = (100 if day % 7 else -30) if quality else -100
            feature={"schema": SCHEMA, "observed_at": stamp.isoformat(),
                     "bar_at": (stamp-timedelta(minutes=1)).isoformat(),
                     "values": {k: float(quality) for k in FEATURES}}
            result.append({"id": f"{day}:{i}", "signal_id": f"{day}:{i}", "entry_ts": stamp.isoformat(),
                           "exit_ts": (stamp+timedelta(minutes=10)).isoformat(), "entry_features": feature,
                           "quality": "verified", "costs": 10, "gross_pnl": pnl+10, "pnl": pnl,
                           "symbol": "NIFTY", "strategy_version": "test-only", "exit_policy": VERSION,
                           "contract_id": f"NSE:{100000+day}", "security_id": 100000+day, "exchange": "NSE",
                           "expiry": "2026-12-31", "strike": 25000, "lot_size": 65, "tick_size": .05,
                           "metadata_source": "dated_test_master", "metadata_valid_from": "2025-01-01",
                           "metadata_valid_to": "2025-12-31", "price_source": "observed_test_candles",
                           "quantity":65,
                           "entry_charges": {"kind":"dated_schedule","source":"unit_test_schedule",
                                             "as_of":str(stamp.date()),"quantity":65,"total":5},
                           "exit_charges": {"kind":"dated_schedule","source":"unit_test_schedule",
                                            "as_of":str(stamp.date()),"quantity":65,"total":5}})
    return result


def test_real_classifier_json_roundtrip_and_missing_features():
    data=trades()[:200]
    model=MLTradeQualityModel.fit([t["entry_features"] for t in data], [t["pnl"] > 0 for t in data])
    restored=MLTradeQualityModel(json.loads(json.dumps(model.artifact)))
    assert restored.predict(data[1]["entry_features"]) > restored.predict(data[0]["entry_features"])
    feature=copy.deepcopy(data[1]["entry_features"]); feature["values"]["option_delta"]=None
    assert 0 < restored.predict(feature) < 1
    with pytest.raises(ValueError): restored.predict({"schema": "future-schema"})


@pytest.mark.parametrize("flags", [
    {"status": "research_partial"}, {"quality": "research_net"},
    {"issues": ["missing candles"]}, {"unresolved": [{"contract_id": "open"}]},
    {"estimation": {"fees": "scenario"}},
])
def test_incomplete_or_estimated_reports_do_not_fit_models(tmp_path, flags):
    service = LearningService(Store(tmp_path / "excluded.db"))
    result = service.train({"quality": "verified", "trades": trades(), **flags}, "excluded")
    assert result["eligible_trades"] == 0
    assert result["models"] == []
    assert not service.store.list_records("ml_champions")


def test_rolling_contract_identity_fails_the_explicit_provenance_gate(tmp_path):
    data = trades()[:1]
    data[0]["contract_id"] = "rolling:NIFTY:WEEK:1:ATM:CALL"
    result = LearningService(Store(tmp_path / "rolling.db")).train(
        {"quality": "verified", "status": "complete", "trades": data}, "rolling")
    assert result["eligible_trades"] == 0
    assert result["gate_audit"]["fixed_contract_provenance"] == {"passing": 0, "failing": 1}


def test_purged_holdout_not_reused_and_no_promotion_without_full_replay(tmp_path):
    service=LearningService(Store(tmp_path/"model.db"))
    result=service.train({"quality": "verified", "trades": trades()}, "synthetic-1")
    item=result["models"][0]
    assert item["status"] == "FILTER_VALIDATED_REPLAY_REQUIRED"
    assert item["train_trades"] == 280 and item["test_trades"] == 120
    assert not service.store.list_records("ml_champions")
    second=service.train({"quality": "verified", "trades": trades()}, "synthetic-2")
    assert second["models"][0]["status"] == "HOLDOUT_ALREADY_USED"


def test_net_cost_and_future_feature_exclusions(tmp_path):
    data=trades()[:3]
    data[0]["entry_features"]["observed_at"]=data[0]["exit_ts"]
    data[1]["costs"]=None
    data[2]["pnl"]=123456
    result=LearningService(Store(tmp_path/"bad.db")).train({"quality": "verified", "trades": data}, "bad")
    assert result["eligible_trades"] == 0
    assert result["excluded_trades"] == 3


def test_same_bar_stop_losses_are_not_silently_removed_from_training(tmp_path):
    data=trades()[:1]
    data[0]["exit_ts"]=data[0]["entry_ts"]
    data[0]["outcome_observed_at"]=(datetime.fromisoformat(data[0]["entry_ts"])+timedelta(minutes=1)).isoformat()
    result=LearningService(Store(tmp_path/"same-bar.db")).train({"quality":"verified","trades":data},"same-bar")
    assert result["eligible_trades"] == 1 and result["excluded_trades"] == 0


def test_replay_failure_cannot_promote(tmp_path):
    service=LearningService(Store(tmp_path/"fail.db"))
    def replay(a, start, end):
        return {"quality": "incomplete", "trades": trades()[-120:]}, {"quality": "verified", "trades": []}
    result=service.train({"quality": "verified", "trades": trades()}, "replay-failure", replay)
    assert result["models"][0]["status"] == "REJECTED_REPLAY"
    assert not service.store.list_records("ml_champions")


def test_promotion_waits_for_next_session_and_freezes_across_restart(tmp_path):
    service=LearningService(Store(tmp_path/"pass.db"))
    from app.session import now_ist
    now=now_ist()
    assert service.freeze(now)["models"] == {}
    def replay(a, start, end):
        test=[t for t in trades()[-120:] if t["entry_features"]["values"]["adx"] == 1]
        days=sorted({t["entry_ts"][:10] for t in trades()[-120:]})
        def account(rows):
            return {"quality":"verified","trades":rows,
                    "daily":[{"date":day,"pnl":sum(t["pnl"] for t in rows if t["entry_ts"][:10]==day)} for day in days]}
        return account(test),account(trades()[-120:])
    result=service.train({"quality": "verified", "trades": trades()}, "test-promotion", replay)
    assert result["models"][0]["status"] == "VALIDATED_PENDING_SESSION"
    assert service.freeze(now)["models"] == {}
    tomorrow=now+timedelta(days=1)
    frozen=service.freeze(tomorrow)
    assert len(frozen["models"]) == 1
    assert LearningService(service.store).freeze(tomorrow) == frozen


def test_websocket_packets_are_bounded_and_do_not_write_database():
    from app.market_data import DhanMarketData
    class ForbiddenStore:
        def put_record(self, *args): raise AssertionError("Tick persisted to SQLite")
    feed=DhanMarketData("", "", "NIFTY", store=ForbiddenStore())
    feed.security_to_symbol={"13": "NIFTY"}
    for i in range(700): feed._on_message(None, {"security_id": "13", "exchange_segment": 0, "LTP": 23000+i})
    assert len(feed.recent_market_events) == 512
    assert feed.latest["NIFTY"]["ltp"] == 23699
