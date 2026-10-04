"""Replay display integrity; fixtures are not evidence of a trading edge."""
import json
import sqlite3
import zlib
import threading
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.chart_replay import ChartReplay, recorded_seconds


def archive(path, rows):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations(id TEXT, received_at TEXT, kind TEXT, payload BLOB)")
        connection.executemany("INSERT INTO observations VALUES(?,?,?,?)", rows)


def test_observations_keep_received_time_ohlc_and_reject_bad_or_future_ticks(tmp_path):
    opening = pd.Timestamp('2026-10-01T09:15:00+05:30')
    def tick(identifier, received, price, exchange='2026-10-01T09:15:00+05:30', symbol='NIFTY'):
        payload = json.dumps(dict(symbol=symbol, ltp=price, exchange_timestamp=exchange)).encode()
        return identifier, '2026-10-01T09:15:' + received + '+05:30', 'underlying', zlib.compress(payload)
    rows = [tick('a', '00.200', 100), tick('b', '00.500', 105), tick('c', '00.800', 101),
            tick('d', '02.000', 110), tick('future', '01.000', 999, '2026-10-01T09:16:00+05:30'),
            tick('invalid', '01.000', -1), tick('other', '01.000', 200, symbol='SENSEX'),
            ('disconnect', '2026-10-01T09:15:03+05:30', 'feed_disconnected', '{}'),
            ('broken', '2026-10-01T09:15:04+05:30', 'underlying', 'bad JSON')]
    folder = tmp_path / 'market_observations'; folder.mkdir()
    archive(folder / 'one.db', rows)
    archive(tmp_path / 'market_observations.db', rows[:1])
    observations, capture = recorded_seconds(tmp_path, 'NIFTY', opening, opening + pd.Timedelta(minutes=5))
    assert len(observations) == 2
    assert observations[0] == dict(time=int(opening.timestamp()) + 1, minute=int(opening.timestamp()),
                                 open=100, high=105, low=100, close=101, count=3)
    assert observations[1]['close'] == 110
    assert capture['observations'] == 4 and capture['invalid'] == 3
    assert capture['disconnects'] == [int(opening.timestamp()) + 3]


def test_session_is_local_only_and_candle_fallback_never_invents_observations(monkeypatch, tmp_path):
    now = pd.Timestamp('2026-10-05T08:00:00+05:30')
    monkeypatch.setattr('app.chart_replay.now_ist', lambda: now)
    frame = pd.DataFrame({'timestamp': pd.date_range('2026-10-01 09:15', periods=375, freq='min', tz='Asia/Kolkata'),
                          'symbol': 'NIFTY', 'open': 100., 'high': 102., 'low': 99., 'close': 101., 'volume': 10.})
    store = SimpleNamespace(list_records=lambda namespace, limit: [])
    terminal = SimpleNamespace(store=store, _history=lambda *args: frame,
                              _volume_series=lambda *args: ({}, pd.DataFrame(), None),
                              volume_bars=lambda *args: [])
    replay = ChartReplay(terminal, tmp_path)
    result = replay.session('NIFTY', '5m', date(2026, 10, 1))
    assert result['mode'] == 'candles' and result['observations'] == []
    assert len(result['minutes']) == 375 and result['volume']['bars'] == []
    assert all(pd.Timestamp(z['available_at']) <= now for z in result['zones'])
    with pytest.raises(ValueError, match='already started'):
        replay.session('NIFTY', '5m', date(2026, 10, 5))
    with pytest.raises(ValueError, match='open market session'):
        replay.session('NIFTY', '5m', date(2026, 10, 4))
    terminal._history = lambda *args: pd.DataFrame()
    with pytest.raises(ValueError, match='No saved candles'):
        replay.session('NIFTY', '5m', date(2026, 9, 30))


def test_replay_reuses_frozen_data_across_periods_and_reload_refreshes_it(monkeypatch, tmp_path):
    monkeypatch.setattr('app.chart_replay.now_ist', lambda: pd.Timestamp('2026-10-05T08:00:00+05:30'))
    frames = [pd.DataFrame(dict(timestamp=pd.date_range(day + ' 09:15', periods=375, freq='min', tz='Asia/Kolkata'),
                               symbol='NIFTY', open=100., high=102., low=99., close=101., volume=10.))
              for day in ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01']]
    frame = pd.concat(frames, ignore_index=True)
    calls = []
    def history(*args):
        calls.append(args)
        return frame
    terminal = SimpleNamespace(store=SimpleNamespace(list_records=lambda *args: []), _history=history,
                              _volume_series=lambda *args: ({}, pd.DataFrame(), None), volume_bars=lambda *args: [])
    replay = ChartReplay(terminal, tmp_path)
    first = replay.session('NIFTY', '2m', date(2026, 10, 1))
    assert len(first['history_candles']) == 200
    assert all(bar['end_time'] <= first['start'] for bar in first['history_candles'])
    second = replay.session('NIFTY', '5m', date(2026, 10, 1))
    assert len(calls) == 1 and second['minutes'] == first['minutes']
    replay.session('NIFTY', '5m', date(2026, 10, 1), refresh=True)
    assert len(calls) == 2
    for day in [date(2026, 9, 29), date(2026, 9, 30)]:
        replay.session('NIFTY', '5m', day)
    assert len(replay.cache) == 2


def test_current_engine_candles_are_replayed_without_revealing_future_minutes(monkeypatch, tmp_path):
    now = pd.Timestamp('2026-10-01T09:17:00+05:30')
    monkeypatch.setattr('app.chart_replay.now_ist', lambda: now)
    current = pd.DataFrame(dict(timestamp=pd.date_range('2026-10-01 09:15', periods=3, freq='min', tz='Asia/Kolkata'),
                                symbol='NIFTY', open=100., high=102., low=99., close=101., volume=10.))
    terminal = SimpleNamespace(store=SimpleNamespace(list_records=lambda *args: []), _history=lambda *args: pd.DataFrame(),
                              engine=SimpleNamespace(lock=threading.Lock(), frames={'NIFTY': current}),
                              _volume_series=lambda *args: ({}, pd.DataFrame(), None), volume_bars=lambda *args: [])
    result = ChartReplay(terminal, tmp_path).session('NIFTY', '5m', now.date())
    assert len(result['minutes']) == 2
    assert all(bar['end_time'] <= now.timestamp() for bar in result['minutes'])
