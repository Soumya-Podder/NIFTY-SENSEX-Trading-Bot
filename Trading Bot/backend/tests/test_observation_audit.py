import json
import sqlite3

from app.backtest.observation_audit import audit_observation_db


def test_audit_reports_observations_without_claiming_replay_eligibility(tmp_path):
    path = tmp_path / "observations.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE observations(
                id TEXT PRIMARY KEY, run_id TEXT, received_at TEXT,
                kind TEXT, generation INTEGER, payload TEXT
            );
            CREATE TABLE recorder_runs(
                id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT,
                clean_shutdown INTEGER, persisted INTEGER, dropped INTEGER,
                last_drop TEXT, error TEXT
            );
            """
        )
        payload = {
            "symbol": "NIFTY", "contract_id": "NSE:1", "expiry": "2026-09-22",
            "strike": 25000, "option_type": "CALL", "lot_size": 65,
            "tick_size": 0.05, "bid": 100, "ask": 101, "bid_qty": 10,
            "ask_qty": 10, "ltp": 100.5, "volume": 2, "oi": 3,
            "metadata_source": "security_master", "source": "feed",
            "exchange_timestamp": "2026-09-18T09:15:00+05:30",
        }
        db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?)",
                   ("1", "run", "2026-09-18T09:15:00+05:30", "option_depth", 1,
                    json.dumps(payload)))
        db.execute("INSERT INTO recorder_runs VALUES(?,?,?,?,?,?,?,?)",
                   ("run", "2026-09-18T09:00:00+05:30",
                    "2026-09-18T15:10:00+05:30", 1, 1, 0, None, None))

    result = audit_observation_db(path)
    assert result["option_depth_rows"] == 1
    assert result["distinct_contract_ids"] == 1
    assert result["option_days"] == ["2026-09-18"]
    assert result["all_runs_clean_without_drops"]
    assert not result["eligible_for_fixed_contract_replay"]
    assert "charge_schedule" in result["missing_option_fields"]


def test_audit_rejects_non_recorder_database(tmp_path):
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE records(id INTEGER)")
    try:
        audit_observation_db(path)
    except ValueError as exc:
        assert "QuoteRecorder" in str(exc)
    else:
        raise AssertionError("Expected non-recorder database to be rejected")
