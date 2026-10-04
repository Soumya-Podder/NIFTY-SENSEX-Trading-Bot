"""Causal price zones and sweep hypotheses; observation only, never order authority."""
import hashlib
import math
import pandas as pd
from .market_calendar import calendar_info

VERSION = "market-structure-v2"
TIMEFRAMES = {"2m": 2, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "1d": 375}


def completed_minutes(frame, now, symbol, lookback_days=7):
    if frame is None or frame.empty:
        return pd.DataFrame()
    x = frame.copy()
    if "symbol" in x:
        x = x[x.symbol == symbol]
    stamps = pd.to_datetime(x.timestamp)
    x["timestamp"] = stamps.dt.tz_localize("Asia/Kolkata") if stamps.dt.tz is None else stamps.dt.tz_convert("Asia/Kolkata")
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("Asia/Kolkata")
    else:
        now = now.tz_convert("Asia/Kolkata")
    x = x[(x.timestamp + pd.Timedelta(minutes=1) <= now) &
          (x.timestamp >= now.normalize() - pd.Timedelta(days=lookback_days))].sort_values("timestamp")
    minute = x.timestamp.dt.hour * 60 + x.timestamp.dt.minute
    x = x[(minute >= 555) & (minute < 930)]
    if x.timestamp.duplicated().any():
        return pd.DataFrame()
    if any(not pd.to_numeric(x[k], errors="coerce").map(lambda v: math.isfinite(v) and v > 0).all()
           for k in ("open", "high", "low", "close")):
        return pd.DataFrame()
    if ((x.high < x[["open", "close"]].max(axis=1)) |
        (x.low > x[["open", "close"]].min(axis=1))).any():
        return pd.DataFrame()
    return x.reset_index(drop=True)


def aggregate_minutes(minutes, size):
    """Session anchored; incomplete bins and bins containing a missing minute are discarded."""
    if minutes.empty:
        return pd.DataFrame()
    x = minutes.copy()
    start = x.timestamp.dt.normalize() + pd.Timedelta(hours=9, minutes=15)
    x["bucket"] = start + pd.to_timedelta(((x.timestamp-start).dt.total_seconds() // (size*60)) * size, unit="min")
    x["aligned"] = x.timestamp == x.timestamp.dt.floor("min")
    groups = x.groupby("bucket", sort=True).agg(
        count=("timestamp", "size"), unique=("timestamp", "nunique"),
        first=("timestamp", "first"), last=("timestamp", "last"), aligned=("aligned", "all"),
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    # Unique minute-aligned timestamps spanning exactly size minutes cannot contain a hole.
    groups = groups[(groups["count"] == size) & (groups["unique"] == size) & groups.aligned &
                    (groups["first"] == groups.index) &
                    (groups["last"] == groups.index+pd.Timedelta(minutes=size-1))]
    result = groups[["open", "high", "low", "close"]].astype(float).reset_index().rename(columns={"bucket": "timestamp"})
    result["available_at"] = result.timestamp+pd.Timedelta(minutes=size)
    return result


def expected_bar_slots(minutes, size):
    """Keep holes visible across sessions; never treat missing bars as neighbours."""
    slots = []
    for day in pd.date_range(minutes.timestamp.iloc[0].normalize(), minutes.timestamp.iloc[-1].normalize(), freq="D"):
        if day.weekday() >= 5 or calendar_info(day.date())["closed"]:
            continue
        start = day + pd.Timedelta(hours=9, minutes=15)
        slots.extend(start + pd.Timedelta(minutes=i*size) for i in range(375//size))
    return {stamp: i for i, stamp in enumerate(slots)}


def detect_sweeps(minutes, zones):
    """Strict breach of a known zone, reclaim, then the next minute confirms rejection."""
    events = []
    for i in range(max(1, len(minutes)-10), len(minutes)):
        sweep, confirm = minutes.iloc[i-1], minutes.iloc[i]
        if confirm.timestamp-sweep.timestamp != pd.Timedelta(minutes=1):
            continue
        for z in zones:
            if pd.Timestamp(z["available_at"]) > sweep.timestamp:
                continue
            buy = sweep.low < z["lower"] and sweep.close > z["upper"] and confirm.close > sweep.high
            sell = sweep.high > z["upper"] and sweep.close < z["lower"] and confirm.close < sweep.low
            if not (buy or sell):
                continue
            events.append({"zone_id": z["id"], "timeframe": z["timeframe"], "level": z["price"],
                           "side": "SELL_SIDE_RECLAIM" if buy else "BUY_SIDE_RECLAIM",
                           "bias": "CALL" if buy else "PUT", "swept_at": sweep.timestamp.isoformat(),
                           "confirmed_at": (confirm.timestamp+pd.Timedelta(minutes=1)).isoformat(),
                           "status": "CONFIRMED_PRICE_PATTERN", "interpretation": "Inferred sweep; hidden stop orders are not observed"})
    return events


def analyze_structure(frame, now, symbol, lookback_days=7, zone_limit_per_side=None):
    x = completed_minutes(frame, now, symbol, lookback_days=lookback_days)
    result = {"version": VERSION, "symbol": symbol, "authority": "OBSERVATION_ONLY", "zones": [],
              "sweeps": [], "coverage": {label: {"complete_bars": 0, "confirmed_swings": 0, "minutes": size,
                  "reason": "No complete candles available"} for label, size in TIMEFRAMES.items()},
              "status": "DATA_UNAVAILABLE", "reason": "Valid completed minute candles unavailable"}
    if x.empty:
        return result
    now = pd.Timestamp(now)
    now = now.tz_localize("Asia/Kolkata") if now.tzinfo is None else now.tz_convert("Asia/Kolkata")
    zones = []

    def zone(label, kind, price, width, formed, available):
        identity = f"{VERSION}|{symbol}|{label}|{kind}|{formed}|{price}"
        zones.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:20], "timeframe": label,
                      "kind": kind, "price": round(price, 4), "lower": round(price-width, 4),
                      "upper": round(price+width, 4), "formed_at": formed.isoformat(),
                      "available_at": available.isoformat()})

    for label, size in TIMEFRAMES.items():
        bars = aggregate_minutes(x, size)
        result["coverage"][label].update(complete_bars=len(bars),
            reason="Fewer than five complete candles; awaiting swing confirmation" if len(bars) < 5
            else "No confirmed swing in consecutive completed candles")
        if bars.empty:
            continue
        slots = expected_bar_slots(x, size) if size >= 60 else {}
        stamps = bars.timestamp.tolist()
        available = bars.available_at.tolist()
        highs, lows, closes = bars.high.tolist(), bars.low.tolist(), bars.close.tolist()
        widths = ((bars.high-bars.low).rolling(14, min_periods=1).mean()*.1).tolist()
        # Pivots require two completed candles on each side. No future bar can confirm them.
        for i in range(2, len(bars)-2):
            window_stamps = stamps[i-2:i+3]
            if size < 60:
                if (len({stamp.date() for stamp in window_stamps}) != 1 or
                    any(b-a != pd.Timedelta(minutes=size) for a, b in zip(window_stamps, window_stamps[1:]))):
                    continue
            else:
                positions = [slots.get(stamp) for stamp in window_stamps]
                if any(p is None for p in positions) or any(b-a != 1 for a, b in zip(positions, positions[1:])):
                    continue
            width = max(widths[i], closes[i]*.00002)
            for values_all, kind, compare in ((highs, "SWING_HIGH", max), (lows, "SWING_LOW", min)):
                values = values_all[i-2:i+3]
                if values[2] == compare(values) and values.count(values[2]) == 1:
                    zone(label, kind, values[2], width, stamps[i], available[i+2])
                    result["coverage"][label]["confirmed_swings"] += 1
        if result["coverage"][label]["confirmed_swings"]:
            result["coverage"][label]["reason"] = "Confirmed swings available"
        if label == "1d":
            previous = bars[bars.timestamp.dt.date < now.date()]
            if not previous.empty:
                row = previous.iloc[-1]
                width = max((row.high-row.low)*.01, row.close*.00002)
                for field in ("high", "low"):
                    zone("1d", "PREVIOUS_SESSION_"+field.upper(), row[field], width, row.timestamp, row.available_at)
    today = x[x.timestamp.dt.date == now.date()]
    opening = today.iloc[:15]
    start = now.normalize()+pd.Timedelta(hours=9, minutes=15)
    if len(opening) == 15 and list(opening.timestamp) == list(pd.date_range(start, periods=15, freq="min")):
        for field in ("high", "low"):
            value = float(opening[field].max() if field == "high" else opening[field].min())
            zone("15m", "OPENING_"+field.upper(), value, value*.00002, start, start+pd.Timedelta(minutes=15))
    # Fast timeframes must not evict slower-timeframe evidence from the response.
    if zone_limit_per_side is None:
        zones = [z for label in TIMEFRAMES for z in sorted(
            (item for item in zones if item["timeframe"] == label), key=lambda item: item["available_at"])[-24:]]
    last = x.iloc[-1]
    price = float(last.close)
    for z in zones:
        z["relation"] = "SUPPORT" if z["upper"] < price else "RESISTANCE" if z["lower"] > price else "AT_ZONE"
        z["distance_points"] = round(max(z["lower"]-price, price-z["upper"], 0), 4)
    if zone_limit_per_side is not None:
        # Display selection must not let recent resistance evict older support.
        selected = []
        for label in TIMEFRAMES:
            for relation in ("SUPPORT", "RESISTANCE", "AT_ZONE"):
                candidates = sorted((z for z in zones if z["timeframe"] == label and z["relation"] == relation),
                                    key=lambda z: (z["distance_points"], -pd.Timestamp(z["available_at"]).timestamp()))
                seen = set()
                for candidate in candidates:
                    band = (candidate["lower"], candidate["upper"], candidate["price"])
                    if band in seen:
                        continue
                    seen.add(band)
                    selected.append(candidate)
                    if len(seen) >= zone_limit_per_side:
                        break
        zones = selected
    fresh = last.timestamp.date() == now.date() and 60 <= (now-last.timestamp).total_seconds() <= 125
    return {**result, "status": "OBSERVED" if fresh else "STALE", "reason": "Completed candles only" if fresh else "Last completed candle is stale",
            "as_of": (last.timestamp+pd.Timedelta(minutes=1)).isoformat(), "price": price,
            "recent_prices": [{"timestamp": row.timestamp.isoformat(), "close": float(row.close)} for row in x.tail(120).itertuples()],
            "zones": zones, "sweeps": detect_sweeps(today, zones),
            "nearest_support": min((z for z in zones if z["relation"] == "SUPPORT"), key=lambda z: z["distance_points"], default=None),
            "nearest_resistance": min((z for z in zones if z["relation"] == "RESISTANCE"), key=lambda z: z["distance_points"], default=None),
            "limitations": [f"{lookback_days}-calendar-day lookback; higher-timeframe swing history can be insufficient.",
                            "09:15 IST anchored full candles only; shortened session-end candles are excluded.",
                            "Higher-timeframe confirmation uses weekday slots and the shared closure calendar; special sessions and BSE closures are not independently verified.",
                            "Zones and sweeps are price hypotheses, not observed institutional orders."]}


def structure_evidence(snapshot, side, now=None):
    """Describe the nearest obstacle without inventing target prices from option delta."""
    obstacle = snapshot.get("nearest_resistance" if side == "CALL" else "nearest_support")
    status = snapshot.get("status", "DATA_UNAVAILABLE")
    sweeps = snapshot.get("sweeps", [])
    if now is not None and snapshot.get("as_of"):
        current = pd.Timestamp(now)
        current = current.tz_localize("Asia/Kolkata") if current.tzinfo is None else current.tz_convert("Asia/Kolkata")
        age = (current-pd.Timestamp(snapshot["as_of"])).total_seconds()
        if not 0 <= age <= 65:
            status = "STALE"
        if age < 0:
            obstacle, sweeps = None, []
    return {"status": status, "version": VERSION,
            "authority": "OBSERVATION_ONLY", "as_of": snapshot.get("as_of"),
            "nearest_obstacle": obstacle,
            "sweeps": sweeps,
            "conflicting_sweeps": [s for s in sweeps if s["bias"] != side]}
