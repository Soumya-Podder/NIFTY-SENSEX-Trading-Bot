"""Archived-input fixtures exercise the live selector and isolated virtual account."""
import hashlib
import json
import sqlite3
import zlib
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from app.autonomous_policy import VERSION
from app.backtest.autonomous_replay import run_replay, captured_events, ReplayStore, decision_blocker_history
from app.config import Settings
from app.market_context import positioning_context, chain_window
from app.store import Store
from app.telemetry.event_bus import event_bus
from tests.test_simple_paper import downtrend_frame
from tests.test_market_context import chain_fixture, NOW


def test_expired_candidate_keeps_earlier_missing_data_history(tmp_path):
    store = ReplayStore(tmp_path/"replay.db", keep_open=True)
    for identifier, agent, status, reason, timestamp in (
        ("1", "Option Selector", "WAITING", "Missing contract candles", "2026-09-04T10:01:00+05:30"),
        ("2", "Orchestrator", "WAIT", "Missing contract candles", "2026-09-04T10:01:00+05:30"),
        ("3", "Orchestrator", "WAIT", "Missing contract candles", "2026-09-04T10:01:02+05:30"),
        ("4", "Orchestrator", "WAIT", "Setup no longer confirmed", "2026-09-04T10:02:00+05:30"),
    ):
        store.record_event({"id": identifier, "agent": agent, "status": status, "summary": reason,
            "timestamp": timestamp, "symbol": "NIFTY", "signal_id": "candidate", "evaluation": {"evidence": reason}})
    store.put_record("strategy_opportunities", "candidate", {"id": "candidate", "status": "REJECTED", "reason": "Setup no longer confirmed"})
    rows, waits = decision_blocker_history(store)
    assert waits == {"candidate"}
    assert rows[0] == {"reason": "Missing contract candles", "checks": 2,
        "first_at": "2026-09-04T10:01:00+05:30", "last_at": "2026-09-04T10:01:02+05:30", "by_symbol": {"NIFTY": 2}}
    assert rows[1]["reason"] == "Setup no longer confirmed"
    store.close()


def test_normal_setup_rejection_is_not_a_data_gap(tmp_path):
    store = ReplayStore(tmp_path/"replay.db", keep_open=True)
    store.record_event({"id": "1", "agent": "Risk", "status": "REJECTED", "signal_id": "candidate",
        "timestamp": "2026-09-04T10:02:00+05:30", "summary": "Setup no longer confirmed"})
    assert decision_blocker_history(store) == ([], set())
    store.close()


def test_replay_write_setting_is_isolated_and_completed_account_remains_readable(tmp_path):
    primary = Store(tmp_path/"primary.db", keep_open=True)
    replay = ReplayStore(tmp_path/"replay.db", keep_open=True)
    for store, mode in ((primary, 2), (replay, 1)):
        with store._conn() as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert connection.execute("PRAGMA synchronous").fetchone()[0] == mode
    replay.put_record("paper", "account", {"cash": 30000., "positions": []})
    replay.close()
    reopened = Store(tmp_path/"replay.db")
    assert reopened.get_record("paper", "account") == {"cash": 30000., "positions": []}
    assert primary.get_record("paper", "account") is None
    with primary._conn() as connection:
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    reopened.close()
    primary.close()


def test_archive_loading_cancels_while_sql_filters_old_quote_rows(tmp_path):
    with sqlite3.connect(tmp_path/"dhan_api_observations.db") as connection:
        connection.execute("CREATE TABLE observations(id TEXT PRIMARY KEY,received_at TEXT,kind TEXT,generation INTEGER,payload TEXT)")
        connection.execute("CREATE INDEX observations_time ON observations(received_at,id)")
        connection.executemany("INSERT INTO observations VALUES(?,?,?,?,?)",
            [(str(n), "2026-09-03T10:00:00+05:30", "underlying", 0, "{}") for n in range(6000)])
    calls=0
    def cancelled():
        nonlocal calls
        calls+=1
        return calls>=3
    with pytest.raises(InterruptedError,match="Cancelled"):
        captured_events(tmp_path,"2026-09-04","2026-09-04",cancelled)


def test_archive_warmup_retains_api_responses_but_not_previous_session_books(tmp_path):
    for filename, rows in (
        ("dhan_api_observations.db", [("warmup", "2026-09-03T15:05:00+05:30", "dhan_api")]),
        ("market_observations.db", [("old-book", "2026-09-03T15:05:00+05:30", "option_depth"),
                                   ("old-policy", "2026-09-03T09:00:00+05:30", "runtime_policy"),
                                   ("session-policy", "2026-09-04T09:00:00+05:30", "runtime_policy"),
                                   ("session-book", "2026-09-04T10:00:00+05:30", "option_depth")])):
        with sqlite3.connect(tmp_path/filename) as connection:
            connection.execute("CREATE TABLE observations(id TEXT PRIMARY KEY,received_at TEXT,kind TEXT,generation INTEGER,payload TEXT)")
            connection.executemany("INSERT INTO observations VALUES(?,?,?,?,?)", [(*row,0,"{}") for row in rows])
    events=captured_events(tmp_path,"2026-09-04","2026-09-04")
    assert {e["id"] for e in events} == {"warmup","session-policy","session-book"}


def test_full_returned_chain_includes_oi_outside_the_previous_atm_window():
    rows = chain_fixture()
    rows[-2]["oi"] = 100000.
    window, _ = chain_window(rows, "NIFTY")
    narrow = positioning_context(window, "NIFTY", NOW)
    full = positioning_context(rows, "NIFTY", NOW, full_chain=True)
    assert full["status"] == "OBSERVED" and full["contracts"] == len(rows)
    assert full["call_oi"] > narrow["call_oi"] and full["call_wall"]["strike"] == 24300.
    assert positioning_context([r for r in rows if r["option_type"] == "PUT"], "NIFTY", NOW, full_chain=True)["status"] == "DATA_UNAVAILABLE"


def test_captured_bid_ask_replay_opens_and_closes_the_shared_autonomous_policy(tmp_path, monkeypatch):
    now = pd.Timestamp("2026-09-04 10:05", tz="Asia/Kolkata")
    frame = downtrend_frame({"now": now})
    frame.loc[49, "ema21"] = 24013.

    def indicators(bars):
        result = bars.copy()
        for key in ("adx", "atr", "ema9", "ema21"):
            result[key] = frame[key].to_numpy()[:len(result)]
        return result

    monkeypatch.setattr("app.strategy_portfolio.add_features", indicators)
    structure_calls = []
    def structure(bars, timestamp, symbol):
        structure_calls.append((timestamp, symbol))
        return {"status": "OBSERVED", "as_of": timestamp.isoformat(), "zones": [], "sweeps": []}
    monkeypatch.setattr("app.backtest.autonomous_replay.analyze_structure", structure)
    monkeypatch.setattr("requests.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Replay performed HTTP")))
    store = Store(tmp_path/"source.db", keep_open=True)
    data = tmp_path/"archive"
    data.mkdir()
    base = {"symbol": "NIFTY", "exchange": "NSE", "expiry": "2026-09-10", "strike": 24000.,
            "lot_size": 10, "tick_size": .05, "identity_verified": True, "metadata_source": "isolated_archive_fixture",
            "metadata_observed_on": "2026-09-04", "oi": 1000., "volume": 1000.}
    put = {**base, "contract_id": "NSE:12345", "security_id": "12345", "option_type": "PUT"}
    call = {**base, "contract_id": "NSE:12346", "security_id": "12346", "option_type": "CALL"}
    for contract in (put, call): store.put_record("contract_metadata", contract["contract_id"], contract)
    for qty in range(10, 241, 10):
        for sell in (0., 97.05):
            body = {"source": "N", "data": {"exchange": "NSE", "segment": "D", "txn_type": "S",
                "qty": qty//10, "window": "SHORT_TRADE", "security_id": "12345", "buy_price": 100.05,
                "sell_price": sell, "product": "I", "instrument": "OPTIDX", "exchange1": ""}}
            store.cache_put(f"charges:fixture-{qty}-{sell}", {"kind": "broker_calculator_quote", "quantity": qty,
                "as_of": "2026-09-04", "captured_at": "2026-09-04T09:00:00+05:30", "buy_price": 100.05,
                "sell_price": sell, "total": 20., "brokerage": 20.,
                "request_fingerprint": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()})

    def candles(bars):
        return {**{k: bars[k].tolist() for k in ("open", "high", "low", "close", "volume")},
                "timestamp": [int(t.timestamp()) for t in bars.timestamp]}

    option_bars = pd.DataFrame({"timestamp": frame.timestamp, "open": 100., "high": 101., "low": 98., "close": 100., "volume": 1000.})
    leg = {"security_id": "12345", "last_price": 100., "oi": 1000., "previous_oi": 900., "volume": 1000.,
           "implied_volatility": 20., "greeks": {"delta": -.5, "gamma": .001, "theta": -1., "vega": 2.}}
    book = {**put, "bid": 100., "ask": 100.05, "bid_qty": 1000, "ask_qty": 1000, "source": "dhan_market_feed",
            "timestamp": now.isoformat(), "quote_update_timestamp": now.isoformat(), "exchange_timestamp": now.isoformat()}
    observations = [
        ("00-policy", now.replace(hour=9, minute=0), "runtime_policy", {"source": VERSION}),
        ("01-index-api", now, "dhan_api", {"outcome": "SUCCESS", "method": "intraday_minute_data", "request": [13, "IDX_I", "INDEX"], "response": candles(frame)}),
        ("01b-index-api", now, "dhan_api", {"outcome": "SUCCESS", "method": "intraday_minute_data", "request": [13, "IDX_I", "INDEX"], "response": candles(frame)}),
        ("02-option-api", now, "dhan_api", {"outcome": "SUCCESS", "method": "intraday_minute_data", "request": [12345, "NSE_FNO", "OPTIDX"], "response": candles(option_bars)}),
        ("03-chain-api", now, "dhan_api", {"outcome": "SUCCESS", "method": "option_chain", "request": [13, "IDX_I", "2026-09-10"],
            "response": {"last_price": 23990., "oc": {"24000.000000": {"pe": leg, "ce": {**leg, "security_id": "12346", "greeks": {"delta": .5}}}}}}),
        ("04-underlying", now, "underlying", {"symbol": "NIFTY", "security_id": "13", "ltp": 23990., "source": "dhan_market_feed", "quote_update_timestamp": now.isoformat()}),
        ("05-entry-book", now, "option_depth", book),
        ("06-exit-book", now+timedelta(seconds=2), "option_depth", {**book, "bid": 107., "ask": 107.05,
            "timestamp": (now+timedelta(seconds=2)).isoformat(), "quote_update_timestamp": (now+timedelta(seconds=2)).isoformat(),
            "exchange_timestamp": (now+timedelta(seconds=2)).isoformat()}),
    ]
    with sqlite3.connect(data/"market_observations.db") as connection:
        connection.execute("CREATE TABLE observations(id TEXT,received_at TEXT,kind TEXT,generation INTEGER,payload BLOB)")
        connection.executemany("INSERT INTO observations VALUES(?,?,?,?,?)", [(i, t.isoformat(), kind, 1 if kind == "dhan_api" else 3, zlib.compress(json.dumps(p).encode())) for i, t, kind, p in observations])
    before = store.list_records("paper_account")
    events = deepcopy(event_bus.recent(100))
    report = run_replay(store=store, gateway=SimpleNamespace(), settings=Settings(_env_file=None), data_dir=data,
                        start="2026-09-04", end="2026-09-04", symbols=("NIFTY",))
    assert len(report["trades"]) == 1, report["admission_blockers"]
    trade = report["trades"][0]
    assert trade["option_type"] == "PUT" and trade["reason"] == "TARGET" and trade["pnl"] > 0
    assert trade["entry_quote_observation_id"] == "05-entry-book" and trade["exit_quote_observation_id"] == "06-exit-book"
    assert trade["qty"] > trade["lot_size"] and trade["risk_rupees"] <= 650
    assert trade["entry_ts"] == now.isoformat() and trade["exit_ts"] == (now+timedelta(seconds=2)).isoformat()
    assert report["status"] == "research_partial" and not report["coverage_summary"]["full_sessions"]
    assert report["input_digest"] and report["policy_settings_digest"]
    assert structure_calls == [(now, "NIFTY")]
    assert store.list_records("paper_account") == before and event_bus.recent(100) == events
    store.close()
