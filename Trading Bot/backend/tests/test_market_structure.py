"""Synthetic fixtures only; these tests are not performance evidence."""
from copy import deepcopy
import pandas as pd
import pytest
from app.market_structure import analyze_structure, aggregate_minutes, completed_minutes, detect_sweeps, structure_evidence


def candles(n=30):
    return pd.DataFrame({"timestamp": pd.date_range("2026-09-25 09:15", periods=n, freq="min", tz="Asia/Kolkata"),
                         "symbol": "NIFTY", "open": 100., "high": 102., "low": 99., "close": 100.})


def test_pivot_waits_for_both_confirmation_bars_and_ignores_future_data():
    f = candles()
    for i, high in enumerate([102., 104., 110., 105., 103., 102.]):
        f.loc[i*5:i*5+4, "high"] = high
    before = analyze_structure(f, "2026-09-25T09:39:59+05:30", "NIFTY")
    assert not [z for z in before["zones"] if z["kind"] == "SWING_HIGH" and z["timeframe"] == "5m"]
    now = "2026-09-25T09:40:00+05:30"
    result = analyze_structure(f, now, "NIFTY")
    pivot = next(z for z in result["zones"] if z["kind"] == "SWING_HIGH" and z["timeframe"] == "5m")
    assert pivot["price"] == 110 and pivot["available_at"] == now
    f.loc[25:, ["high", "close"]] = [9999., 9000.]
    assert analyze_structure(f, now, "NIFTY") == result
    missing = analyze_structure(f.drop(index=12), now, "NIFTY")
    assert missing["coverage"]["5m"]["confirmed_swings"] == 0


def test_timeframes_require_complete_session_anchored_bins_and_full_prior_day():
    f = candles(375)
    before = completed_minutes(f, "2026-09-25T10:14:59+05:30", "NIFTY")
    assert aggregate_minutes(before, 60).empty
    at = completed_minutes(f, "2026-09-25T10:15:00+05:30", "NIFTY")
    assert len(aggregate_minutes(at, 60)) == 1
    next_day = analyze_structure(f, "2026-09-26T10:15:00+05:30", "NIFTY")
    assert next_day["status"] == "STALE"
    assert len([z for z in next_day["zones"] if z["kind"].startswith("PREVIOUS_SESSION")]) == 2
    assert not [z for z in analyze_structure(f.drop(index=42), "2026-09-26T10:15:00+05:30", "NIFTY")["zones"] if z["kind"].startswith("PREVIOUS_SESSION")]


def test_symbol_separation_naive_ist_and_duplicates():
    f = candles()
    other = f.assign(symbol="SENSEX", open=1000., high=1010., low=990., close=1000.)
    now = "2026-09-25T09:45:00+05:30"
    result = analyze_structure(pd.concat([f, other]), now, "NIFTY")
    assert result["price"] == 100
    naive = f.copy(); naive["timestamp"] = naive.timestamp.dt.tz_localize(None)
    assert analyze_structure(naive, now, "NIFTY") == analyze_structure(f, now, "NIFTY")
    assert analyze_structure(pd.concat([f, f.iloc[[1]]]), now, "NIFTY")["status"] == "DATA_UNAVAILABLE"
    assert structure_evidence(result, "CALL", pd.Timestamp(now)+pd.Timedelta(minutes=3))["status"] == "STALE"
    assert structure_evidence(result, "CALL", "2026-09-25T09:45:00")["status"] == "OBSERVED"
    future = structure_evidence(result, "CALL", pd.Timestamp(now)-pd.Timedelta(minutes=1))
    assert future["status"] == "STALE" and future["nearest_obstacle"] is None and future["sweeps"] == []


def test_sweep_requires_known_zone_strict_breach_reclaim_and_later_confirmation():
    f = candles(2)
    f.loc[0, ["open", "high", "low", "close"]] = [100, 102, 98, 101]
    f.loc[1, ["open", "high", "low", "close"]] = [101, 104, 100, 103]
    z = {"id": "known", "timeframe": "15m", "price": 100, "lower": 99, "upper": 100.5, "available_at": "2026-09-25T09:15:00+05:30"}
    event = detect_sweeps(f, [z])[0]
    assert event["bias"] == "CALL" and event["confirmed_at"] == "2026-09-25T09:17:00+05:30"
    assert detect_sweeps(f, [{**z, "available_at": "2026-09-25T09:16:00+05:30"}]) == []
    for field, value in (("low", 99), ("close", 99.5)):
        altered = f.copy(); altered.loc[0, field] = value
        assert detect_sweeps(altered, [z]) == []
    altered = f.copy(); altered.loc[1, "close"] = 102
    assert detect_sweeps(altered, [z]) == []
    mirror = f.copy()
    for field in ("open", "close"): mirror[field] = 200-f[field]
    mirror["high"], mirror["low"] = 200-f.low, 200-f.high
    mirrored_zone = {**z, "lower": 99.5, "upper": 101}
    assert detect_sweeps(mirror, [mirrored_zone])[0]["bias"] == "PUT"


@pytest.mark.parametrize("size", [2, 5, 15, 30, 60, 120, 240])
def test_all_requested_timeframes_wait_for_full_session_anchored_candles(size):
    f = candles(375)
    end = f.timestamp.iloc[0]+pd.Timedelta(minutes=size)
    assert aggregate_minutes(completed_minutes(f, end-pd.Timedelta(seconds=1), "NIFTY"), size).empty
    bar = aggregate_minutes(completed_minutes(f, end, "NIFTY"), size).iloc[0]
    assert bar.timestamp == f.timestamp.iloc[0] and bar.available_at == end
    assert aggregate_minutes(completed_minutes(f.drop(index=size-1), end, "NIFTY"), size).empty
    full = aggregate_minutes(completed_minutes(f, "2026-09-25T15:30:00+05:30", "NIFTY"), size)
    assert len(full) == 375//size  # No shortened end-of-session candle.


@pytest.mark.parametrize("size,label", [(120, "2h"), (240, "4h")])
@pytest.mark.parametrize("symbol", ["NIFTY", "SENSEX"])
def test_higher_timeframe_swings_confirm_across_sessions_without_lookahead(size, label, symbol):
    sessions = []
    for day in ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"):
        session = candles(375).assign(symbol=symbol)
        session["timestamp"] = pd.date_range(day+" 09:15", periods=375, freq="min", tz="Asia/Kolkata")
        sessions.append(session)
    f = pd.concat(sessions, ignore_index=True)
    slots = aggregate_minutes(f, size).head(5)
    for bar, high, low in zip(slots.itertuples(), [102, 104, 110, 105, 103], [99, 97, 90, 96, 98]):
        mask = (f.timestamp >= bar.timestamp) & (f.timestamp < bar.available_at)
        f.loc[mask, ["high", "low"]] = [high, low]
    confirmed = slots.available_at.iloc[-1]
    before = analyze_structure(f, confirmed-pd.Timedelta(seconds=1), symbol)
    assert not [z for z in before["zones"] if z["timeframe"] == label]
    at = analyze_structure(f, confirmed, symbol)
    swings = [z for z in at["zones"] if z["timeframe"] == label]
    assert {z["relation"] for z in swings} == {"SUPPORT", "RESISTANCE"}
    assert all(z["available_at"] == confirmed.isoformat() for z in swings)
    assert at["coverage"][label]["confirmed_swings"] == 2
    missing = f[f.timestamp != slots.timestamp.iloc[1]+pd.Timedelta(minutes=3)]
    assert not [z for z in analyze_structure(missing, confirmed, symbol)["zones"] if z["timeframe"] == label]


def test_missing_whole_session_is_not_skipped_in_four_hour_confirmation():
    sessions = []
    for day, high in zip(["21", "22", "23", "25", "28"], [102, 104, 110, 103, 102]):
        session = candles(375)
        session["timestamp"] = pd.date_range(f"2026-09-{day} 09:15", periods=375, freq="min", tz="Asia/Kolkata")
        session["high"] = float(high)
        sessions.append(session)
    result = analyze_structure(pd.concat(sessions), "2026-09-28T13:15:00+05:30", "NIFTY")
    assert result["coverage"]["4h"]["complete_bars"] == 5
    assert not [z for z in result["zones"] if z["timeframe"] == "4h"]


def test_empty_data_advertises_every_timeframe_without_fabricated_levels():
    result = analyze_structure(pd.DataFrame(), "2026-09-25T15:30:00+05:30", "SENSEX")
    assert set(result["coverage"]) == {"2m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"}
    assert result["zones"] == [] and all(c["complete_bars"] == 0 for c in result["coverage"].values())


def test_display_retention_preserves_old_support_after_extended_decline():
    import math
    parts = []
    days = pd.bdate_range(end="2026-09-25", periods=150)
    for i, day in enumerate(days):
        base = (70 if i < 25 else 130) + 10*math.sin(i*1.3)
        if i == len(days)-1:
            base = 100
        stamps = pd.date_range(str(day.date())+" 09:15", periods=375, freq="min", tz="Asia/Kolkata")
        parts.append(pd.DataFrame({"timestamp":stamps, "symbol":"NIFTY", "open":base,
                                   "high":base+2, "low":base-2, "close":base+1, "volume":10}))
    frame = pd.concat(parts, ignore_index=True)
    now = "2026-09-25T15:31:00+05:30"
    legacy = analyze_structure(frame, now, "NIFTY", lookback_days=365)
    display = analyze_structure(frame, now, "NIFTY", lookback_days=365, zone_limit_per_side=24)
    assert not any(z["timeframe"] == "4h" and z["relation"] == "SUPPORT" for z in legacy["zones"])
    supports = [z for z in display["zones"] if z["timeframe"] == "4h" and z["relation"] == "SUPPORT"]
    assert supports and all(z["upper"] < display["price"] for z in supports)
    assert all(pd.Timestamp(z["available_at"]) <= pd.Timestamp(display["as_of"]) for z in display["zones"])
    assert len(supports) <= 24
