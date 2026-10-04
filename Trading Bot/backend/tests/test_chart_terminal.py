"""Synthetic fixtures verify display integrity, not profitability."""
from datetime import datetime
from types import SimpleNamespace
import threading
import pandas as pd
import pytest
from app.chart_terminal import chart_bars, ChartTerminal


def candles(n=30, symbol="NIFTY"):
    return pd.DataFrame({"timestamp": pd.date_range("2026-09-25 09:15", periods=n, freq="min", tz="Asia/Kolkata"),
                         "symbol": symbol, "open": 100., "high": 102., "low": 99., "close": 101., "volume": 10.})


def test_chart_uses_session_anchor_and_excludes_future_minutes():
    f = candles(375)
    bars = chart_bars(f, "2026-09-25T09:27:00+05:30", "NIFTY", 5)
    assert len(bars) == 3 and bars[-1]["complete"] is False
    assert pd.Timestamp(bars[-1]["time"], unit="s", tz="UTC").tz_convert("Asia/Kolkata").minute == 25
    f.loc[12:, ["high", "close"]] = [900., 800.]
    assert chart_bars(f, "2026-09-25T09:27:00+05:30", "NIFTY", 5) == bars


def test_missing_minutes_not_filled_and_shortened_session_bar_is_explicit():
    f = candles(375)
    bars = chart_bars(f, "2026-09-25T15:31:00+05:30", "NIFTY", 240)
    assert len(bars) == 2 and bars[-1]["shortened"] and bars[-1]["complete"]
    assert len(chart_bars(f.drop(index=20), "2026-09-25T15:31:00+05:30", "NIFTY", 240)) == 1
    assert not chart_bars(f, "2026-09-25T15:31:00+05:30", "SENSEX", 5)


def test_live_ticks_are_partial_and_do_not_rewrite_completed_candles():
    f = candles(10)
    tick = {"symbol": "NIFTY", "ltp": 110., "exchange_timestamp": "2026-09-25T09:25:04+05:30"}
    bars = chart_bars(f, "2026-09-25T09:25:05+05:30", "NIFTY", 5, [tick])
    assert len(bars) == 3 and bars[-1]["partial_observation"] and not bars[-1]["complete"]
    assert bars[-1]["close"] == 110 and bars[1]["close"] == 101
    assert len(chart_bars(f, "2026-09-25T09:25:05+05:30", "NIFTY", 5, [{**tick, "exchange_timestamp": None}])) == 2
    assert len(chart_bars(f, "2026-09-27T09:25:05+05:30", "NIFTY", 5, [{**tick, "exchange_timestamp": "2026-09-27T09:25:04+05:30"}])) == 2


def test_volume_uses_complete_actual_minutes_and_never_index_tick_volume():
    f = candles(10).drop(columns="symbol")
    bars = chart_bars(f, "2026-09-25T09:25:00+05:30", "NIFTY", 5, volume=True)
    assert [b["value"] for b in bars] == [50., 50.]
    f.loc[3, "volume"] = float("nan")
    assert len(chart_bars(f, "2026-09-25T09:25:00+05:30", "NIFTY", 5, volume=True)) == 1


def test_snapshot_is_read_only_symbol_scoped_and_never_claims_forecast(monkeypatch):
    monkeypatch.setattr("app.chart_terminal.now_ist", lambda: datetime.fromisoformat("2026-09-25T09:45:00+05:30"))
    class Storage:
        def history_ranges(self, *args, **kwargs):
            return []
        def list_records(self, namespace, limit):
            assert namespace in {"market_context_inputs", "trades", "chart_futures_contracts"}
            return []
    engine = SimpleNamespace(lock=threading.Lock(), frames={"NIFTY": candles()}, status={"portfolio": {"evaluations": [{"symbol": "SENSEX"}]}})
    market = SimpleNamespace(lock=threading.Lock(), latest={}, recent_market_events=[], connected=True)
    result = ChartTerminal(Storage(), engine, market).snapshot("NIFTY", "5m")
    assert len(result["candles"]) == 6
    assert not result["live"] and not result["probabilities"]["calibrated"]
    assert not result["volume"]["bars"] and not result["decision"]["evaluations"]


def test_terminal_merges_old_history_with_current_engine_and_confirms_4h(monkeypatch):
    from app.market_structure import analyze_structure
    import numpy as np
    days = pd.bdate_range("2026-08-31", "2026-09-11")
    parts = []
    for i, day in enumerate(days):
        part = candles(375)
        part["timestamp"] = pd.date_range(str(day.date())+" 09:15", periods=375, freq="min", tz="Asia/Kolkata")
        base = 100+10*np.sin(i*1.3)
        part[["open", "high", "low", "close"]] = [base, base+2, base-2, base+1]
        parts.append(part)
    history = pd.concat(parts, ignore_index=True)
    now = datetime.fromisoformat("2026-09-25T09:45:00+05:30")
    # The old seven-day default remains unchanged for trading-engine callers.
    assert not analyze_structure(history, now, "NIFTY")["zones"]
    monkeypatch.setattr("app.chart_terminal.now_ist", lambda: now)
    monkeypatch.setattr(ChartTerminal, "_history", lambda self, symbol, now: history)
    storage = SimpleNamespace(list_records=lambda *args: [])
    engine = SimpleNamespace(lock=threading.Lock(), frames={"NIFTY": candles()}, status={})
    market = SimpleNamespace(lock=threading.Lock(), latest={}, recent_market_events=[], connected=False)
    result = ChartTerminal(storage, engine, market).snapshot("NIFTY", "4h")
    assert result["history_days"] == 365
    assert result["structure"]["coverage"]["4h"]["complete_bars"] == len(days)
    assert any(z["timeframe"] == "4h" for z in result["structure"]["zones"])
    assert result["candles"][0]["time"] < int(pd.Timestamp("2026-09-01", tz="Asia/Kolkata").timestamp())
    assert result["candles"][-1]["complete"] is False
    # No historical 1,400-bar truncation when inspecting the finer timeframes.
    assert len(chart_bars(history, now, "NIFTY", 2)) > 1400


def test_one_year_window_retains_old_candles_without_including_older_or_future_data():
    recent = candles(10)
    old = recent.copy()
    old["timestamp"] -= pd.Timedelta(days=300)
    expired = recent.copy()
    expired["timestamp"] -= pd.Timedelta(days=370)
    bars = chart_bars(pd.concat([expired, old, recent]), "2026-09-25T09:25:00+05:30", "NIFTY", 5)
    assert len(bars) == 4
    assert bars[0]["time"] == int(old.timestamp.iloc[0].timestamp())


def test_volume_history_merges_only_matching_identified_contract(monkeypatch):
    contract = {"symbol": "NIFTY", "contract_id": "NSE:123", "security_id": "123", "exchange": "NSE",
                "expiry": "2026-09-29", "identity_verified": True, "captured_at": "2026-09-25T09:25:00+05:30"}
    storage = SimpleNamespace(list_records=lambda *args: [contract])
    terminal = ChartTerminal(storage, None, None)
    retained = candles(10)
    monkeypatch.setattr(terminal, "_history", lambda *args: retained)
    now = datetime.fromisoformat("2026-09-25T09:30:00+05:30")
    recent = candles(15)
    recent.loc[0, "volume"] = 99
    context = {"futures_contract": contract, "futures_candles": recent.to_dict("records"), "captured_at": now.isoformat()}
    selected, merged, capture = terminal._volume_history("NIFTY", now, context)
    assert selected["contract_id"] == "NSE:123" and len(merged) == 15
    newer = {**contract, "captured_at": "2026-09-26T10:00:00+05:30"}
    storage.list_records = lambda *args: [newer]
    assert terminal._volume_history("NIFTY", now, context)[2] == newer["captured_at"]
    storage.list_records = lambda *args: [contract]
    assert merged.iloc[0].volume == 99 and capture == now.isoformat()
    # An expired different contract must never be silently spliced into this series.
    context["futures_contract"] = {**contract, "contract_id": "NSE:456", "expiry": "2026-08-25"}
    selected, merged, capture = terminal._volume_history("NIFTY", now, context)
    assert selected["contract_id"] == "NSE:123" and len(merged) == 10
    assert merged.iloc[0].volume == 10


def test_structure_reference_is_identical_across_chart_periods_and_live_tick(monkeypatch):
    now = datetime.fromisoformat("2026-09-25T09:45:05+05:30")
    monkeypatch.setattr("app.chart_terminal.now_ist", lambda: now)
    monkeypatch.setattr(ChartTerminal, "_history", lambda *args: candles())
    storage = SimpleNamespace(list_records=lambda *args: [])
    engine = SimpleNamespace(lock=threading.Lock(), frames={"NIFTY": candles()}, status={})
    tick = {"symbol": "NIFTY", "ltp": 150., "exchange_timestamp": "2026-09-25T09:45:04+05:30"}
    market = SimpleNamespace(lock=threading.Lock(), latest={"NIFTY": tick}, recent_market_events=[tick], connected=True)
    terminal = ChartTerminal(storage, engine, market)
    five = terminal.snapshot("NIFTY", "5m")
    hour = terminal.snapshot("NIFTY", "1h")
    assert five["candles"][-1]["close"] == 150
    assert five["structure"]["price"] == 101
    assert five["structure"] == hour["structure"]
    assert engine.status == {}


def test_runtime_index_candles_survive_restart_only_after_complete_session(monkeypatch, tmp_path):
    from app.market_data import DhanGateway
    from app.store import Store
    store = Store(tmp_path / "history.db")
    gateway = object.__new__(DhanGateway)
    gateway.store = store
    frame = candles(375)
    frame["timestamp"] += pd.Timedelta(days=4)  # 29 September
    clock = [datetime.fromisoformat("2026-09-29T14:00:00+05:30")]
    monkeypatch.setattr("app.market_data.now_ist", lambda: clock[0])
    gateway._retain_complete_chart_sessions(frame, "13")
    terminal = ChartTerminal(store, None, None)
    assert terminal._history("NIFTY", clock[0]).empty
    clock[0] = datetime.fromisoformat("2026-09-29T15:31:00+05:30")
    gateway._retain_complete_chart_sessions(frame.drop(index=20), "13")
    assert terminal._history("NIFTY", clock[0]).empty
    gateway._retain_complete_chart_sessions(frame, "13")
    restarted = ChartTerminal(Store(tmp_path / "history.db"), None, None)
    retained = restarted._history("NIFTY", clock[0])
    assert len(retained) == 375
    assert retained.timestamp.iloc[-1] == frame.timestamp.iloc[-1]
    count = store.cache_summary()["responses"]
    gateway._retain_complete_chart_sessions(frame, "13")
    assert store.cache_summary()["responses"] == count


def test_retained_futures_volume_is_fixed_contract_scoped_and_excludes_after_hours(monkeypatch, tmp_path):
    from app.market_data import DhanGateway
    from app.store import Store
    now = datetime.fromisoformat("2026-09-25T16:00:00+05:30")
    monkeypatch.setattr("app.market_data.now_ist", lambda: now)
    store = Store(tmp_path / "futures.db")
    gateway = object.__new__(DhanGateway)
    gateway.store = store
    gateway._retain_complete_chart_sessions(candles(385), "123", "NSE_FNO", "FUTIDX")
    contract = {"security_id":"123", "exchange":"NSE"}
    terminal = ChartTerminal(store, None, None)
    retained = terminal._history("NIFTY", now, contract)
    assert len(retained) == 375
    assert retained.volume.sum() == 3750
    assert terminal._history("NIFTY", now, {"security_id":"456", "exchange":"NSE"}).empty
    assert terminal._history("NIFTY", now).empty
