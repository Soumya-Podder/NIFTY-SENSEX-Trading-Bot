"""Read-only visual replay from retained candles and received market observations."""
import json
import math
import sqlite3
import threading
import zlib
from collections import OrderedDict
from contextlib import closing as close_connection
from datetime import datetime
from pathlib import Path

import pandas as pd

from .chart_terminal import HISTORY_DAYS, PERIODS, chart_bars
from .market_calendar import calendar_info
from .market_structure import analyze_structure
from .session import now_ist


def timestamp(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("Replay timestamps must include a timezone")
    return stamp.tz_convert("Asia/Kolkata")


def recorded_seconds(data_dir, symbol, opening, closing):
    """Collapse received ticks within a second, preserving observed OHLC and late arrival."""
    files = sorted((Path(data_dir) / "market_observations").glob("*.db"))
    legacy = Path(data_dir) / "market_observations.db"
    if legacy.exists():
        files.append(legacy)
    groups, seen, disconnects, issues = {}, set(), [], []
    count = invalid = 0
    start_second, end_second = opening.timestamp(), closing.timestamp()
    lower, upper = str(opening.date()), str((opening + pd.Timedelta(days=1)).date())
    for path in files:
        try:
            with close_connection(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
                if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='observations'").fetchone():
                    continue
                rows = connection.execute(
                    "SELECT id,received_at,kind,payload FROM observations "
                    "WHERE received_at>=? AND received_at<? AND kind IN ('underlying','feed_disconnected') "
                    "ORDER BY received_at,id", (lower, upper))
                for identifier, received, kind, raw in rows:
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                    try:
                        at = datetime.fromisoformat(received)
                        if at.tzinfo is None:
                            raise ValueError("Missing receive timezone")
                        received_second = at.timestamp()
                        # A sub-second observation is revealed at the next integer second.
                        second = math.ceil(received_second)
                        if not start_second <= received_second <= end_second:
                            continue
                        if kind == "feed_disconnected":
                            disconnects.append(second)
                            continue
                        item = json.loads(zlib.decompress(raw) if isinstance(raw, bytes) else raw)
                        if item.get("symbol") != symbol:
                            continue
                        exchange = datetime.fromisoformat(item.get("exchange_timestamp"))
                        if exchange.tzinfo is None:
                            raise ValueError("Missing exchange timezone")
                        exchange_second = exchange.timestamp()
                        price = float(item.get("ltp"))
                        if not math.isfinite(price) or price <= 0 or not start_second <= exchange_second <= received_second:
                            invalid += 1
                            continue
                        if received_second - exchange_second > 120:
                            invalid += 1
                            continue
                        minute = int(exchange_second // 60) * 60
                        key = (second, minute)
                        order = (received_second, identifier)
                        row = groups.setdefault(key, {"time": second, "minute": minute,
                            "open": price, "high": price, "low": price, "close": price,
                            "count": 0, "first": order, "last": order})
                        row["high"], row["low"] = max(row["high"], price), min(row["low"], price)
                        if order < row["first"]:
                            row["open"], row["first"] = price, order
                        if order >= row["last"]:
                            row["close"], row["last"] = price, order
                        row["count"] += 1
                        count += 1
                    except (ValueError, TypeError, KeyError, zlib.error):
                        invalid += 1
        except (sqlite3.Error, OSError):
            issues.append("An observation archive could not be read; coverage is incomplete.")
    observations = [{k: v for k, v in row.items() if k not in {"first", "last"}}
                    for _, row in sorted(groups.items())]
    return observations, {"observations": count, "invalid": invalid,
                          "disconnects": sorted(set(disconnects)), "issues": sorted(set(issues))}


class ChartReplay:
    def __init__(self, terminal, data_dir):
        self.terminal, self.data_dir = terminal, Path(data_dir)
        self.cache, self.lock = OrderedDict(), threading.Lock()

    def session(self, symbol, period, day, refresh=False):
        now = timestamp(now_ist())
        opening = pd.Timestamp(str(day) + "T09:15:00", tz="Asia/Kolkata")
        closing = min(opening.normalize() + pd.Timedelta(hours=15, minutes=30), now.floor("s"))
        if opening > closing:
            raise ValueError("Choose a session that has already started")
        if opening.weekday() >= 5 or calendar_info(opening.date())["closed"]:
            raise ValueError("Choose an open market session")
        key = (symbol, str(day))
        # A frozen archive is shared across timeframes. Reload explicitly replaces it.
        # Keep only two sessions in memory; no derived data is written to the account.
        with self.lock:
            if refresh or key not in self.cache:
                self.cache[key] = self._load_session(symbol, opening, closing)
            self.cache.move_to_end(key)
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
            frame, observations, capture, minutes, zones, future, trades, closing = self.cache[key]
        history = [bar for bar in chart_bars(frame, opening, symbol, PERIODS[period])
                   if bar["end_time"] <= opening.timestamp()][-200:]
        volumes = self.terminal.volume_bars(future, closing, symbol, PERIODS[period])
        first = history[0]["time"] if history else opening.timestamp()
        volumes = [bar for bar in volumes if bar["time"] >= first]
        return {"symbol": symbol, "period": period, "date": str(day),
                "start": int(opening.timestamp()), "end": int(closing.timestamp()),
                "history_candles": history, "history_context_bars": 200,
                "minutes": minutes, "observations": observations, "capture": capture,
                "zones": zones, "trades": trades, "history_days": HISTORY_DAYS,
                "volume": {"bars": volumes,
                           "reason": "Recorded contract volume appears only after its candle closes; contract changes are marked. Intraminute volume and original candle receipt times are not reconstructed."},
                "mode": "observations" if observations else "candles",
                "limitations": "Read-only visual reconstruction, not a strategy backtest. Recorded observations appear at their receive second; saved minute candles appear at their close. Original candle receipt times and complete exchange tick coverage are not established. Missing prices are never interpolated."}

    def _load_session(self, symbol, opening, closing):
        frame = self.terminal._history(symbol, closing)
        engine = getattr(self.terminal, "engine", None)
        if engine is not None:
            with engine.lock:
                current = engine.frames.get(symbol)
                current = current.copy() if current is not None else None
            if current is not None and not current.empty:
                frame = pd.concat([frame, current], ignore_index=True)
                frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
                frame = frame.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        observations, capture = recorded_seconds(self.data_dir, symbol, opening, closing)
        minutes = [bar for bar in chart_bars(frame, closing, symbol, 1)
                   if bar["time"] >= opening.timestamp() and bar["complete"]]
        if not minutes and not observations:
            raise ValueError("No saved candles or timestamped observations are available for this session")
        # Keep all confirmations for causal distance selection at the replay clock.
        structure = analyze_structure(frame, closing, symbol, lookback_days=HISTORY_DAYS,
                                      zone_limit_per_side=math.inf)
        _, future, _ = self.terminal._volume_series(symbol, closing, {})
        trades = [{k: trade.get(k) for k in ("id", "symbol", "contract_id", "option_type", "entry_ts", "exit_ts")}
                  for trade in self.terminal.store.list_records("trades", 10000) if trade.get("symbol") == symbol]
        return frame, observations, capture, minutes, structure["zones"], future, trades, closing
