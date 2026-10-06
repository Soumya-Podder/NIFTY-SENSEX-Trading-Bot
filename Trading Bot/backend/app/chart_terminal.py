"""Read-only terminal projection. No broker requests, fills, or forecast authority."""
import hashlib
import json
import math
import threading
import time
from copy import deepcopy

import pandas as pd
from .market_structure import TIMEFRAMES, analyze_structure, completed_minutes
from .market_calendar import calendar_info
from .session import now_ist, session_state

PERIODS = {k: v for k, v in TIMEFRAMES.items() if k != "1d"}
HISTORY_DAYS = 365


def chart_bars(frame, now, symbol, size, ticks=(), volume=False):
    """Historical bars need continuous minutes; partial current bars stay labelled."""
    x = completed_minutes(frame, now, symbol, lookback_days=HISTORY_DAYS)
    rows = {row.timestamp: row._asdict() for row in x.itertuples(index=False)}
    completed_stamps = set(rows)
    now = pd.Timestamp(now)
    now = now.tz_localize("Asia/Kolkata") if now.tzinfo is None else now.tz_convert("Asia/Kolkata")
    # Only actual exchange-timed ticks, never an LTP carried across sessions.
    for tick in sorted(ticks, key=lambda t: t.get("exchange_timestamp") or ""):
        try:
            stamp = pd.Timestamp(tick.get("exchange_timestamp"))
            if pd.isna(stamp) or stamp.tzinfo is None:
                continue
            stamp = stamp.tz_convert("Asia/Kolkata")
            price = float(tick["ltp"])
            if tick.get("symbol") != symbol or not math.isfinite(price) or price <= 0 or not -5 <= (now-stamp).total_seconds() <= 120:
                continue
            if stamp.date() != now.date() or stamp.weekday() >= 5 or calendar_info(stamp.date())["closed"]:
                continue
            minute = stamp.floor("min")
            if minute > now.floor("min"):
                continue
            if not 555 <= minute.hour*60+minute.minute < 930 or minute in completed_stamps:
                continue
            row = rows.setdefault(minute, {"timestamp": minute, "open": price, "high": price, "low": price, "close": price, "tick_only": True})
            row.update(high=max(row["high"], price), low=min(row["low"], price), close=price)
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return []
    x = pd.DataFrame(rows.values()).sort_values("timestamp")
    start = x.timestamp.dt.normalize()+pd.Timedelta(hours=9, minutes=15)
    x["bucket"] = start+pd.to_timedelta(((x.timestamp-start).dt.total_seconds()//(size*60))*size, unit="min")
    x["tick_only"] = x.get("tick_only", pd.Series(False, index=x.index)).eq(True)
    x["aligned"] = x.timestamp == x.timestamp.dt.floor("min")
    aggregations = dict(first=("timestamp", "first"), last=("timestamp", "last"), count=("timestamp", "size"),
                        aligned=("aligned", "all"), tick_only=("tick_only", "any"),
                        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    if volume:
        x["volume"] = pd.to_numeric(x.get("volume", pd.Series(float("nan"), index=x.index)), errors="coerce")
        x["valid_volume"] = x.volume.map(lambda v: math.isfinite(v) and v >= 0)
        aggregations.update(value=("volume", "sum"), valid_volume=("valid_volume", "all"))
    groups = x.groupby("bucket", sort=True).agg(**aggregations).reset_index()
    end = groups.bucket+pd.Timedelta(minutes=size)
    close = groups.bucket.dt.normalize()+pd.Timedelta(hours=15, minutes=30)
    end = end.where(end <= close, close)
    expected = (end-groups.bucket).dt.total_seconds()/60
    continuous = groups.aligned & (groups["first"] == groups.bucket) & (
        groups["last"] == groups.bucket+pd.to_timedelta(groups["count"]-1, unit="min"))
    groups["complete"] = (groups["count"] == expected) & continuous & ~groups.tick_only
    groups["partial_observation"] = ~continuous | groups.tick_only
    groups["shortened"] = expected < size
    groups["time"] = groups.bucket.map(lambda stamp: int(stamp.timestamp()))
    groups["end_time"] = end.map(lambda stamp: int(stamp.timestamp()))
    valid = groups.complete | ((groups.bucket <= now) & (now < end))
    if volume:
        valid &= groups.complete & groups.valid_volume
    fields = ["time", "open", "high", "low", "close", "complete", "partial_observation", "shortened", "end_time"]
    return groups.loc[valid, fields+(["value"] if volume else [])].to_dict("records")


class ChartTerminal:
    def __init__(self, store, engine, market):
        self.store, self.engine, self.market = store, engine, market
        self.cache = {}
        self.lock = threading.Lock()

    def _history(self, symbol, now, contract=None):
        """Read existing Dhan history ranges only. Missing ranges remain missing."""
        identity = ([contract["security_id"], contract["exchange"]+"_FNO", "FUTIDX", 1, False] if contract else
                    ["13" if symbol == "NIFTY" else "51", "IDX_I", "INDEX", 1, False])
        family = hashlib.sha256(("intraday_minute_data"+json.dumps(identity, sort_keys=True)).encode()).hexdigest()
        start, end = str(now.date()-pd.Timedelta(days=HISTORY_DAYS)), str(now.date()+pd.Timedelta(days=1))
        fields = ["open", "high", "low", "close", "volume"]
        ranges = self.store.history_ranges(family, start, end, fields, include_expired=True)
        parts = []
        for key, _, _ in ranges:
            raw = self.store.cache_get(key, include_expired=True) or {}
            stamps = raw.get("timestamp", [])
            if not stamps or any(len(raw.get(k, [])) != len(stamps) for k in fields):
                continue
            part = pd.DataFrame({k: raw[k] for k in ["timestamp", *fields]})
            part["timestamp"] = pd.to_datetime(part.timestamp, unit="s", utc=True)
            part["symbol"] = symbol
            parts.append(part[(part.timestamp >= pd.Timestamp(start, tz="Asia/Kolkata")) &
                              (part.timestamp < pd.Timestamp(end, tz="Asia/Kolkata"))])
        frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if not frame.empty:
            # Identical overlaps are harmless; conflicting candles remain unavailable.
            frame = frame.drop_duplicates()
            frame = frame[~frame.timestamp.duplicated(keep=False)].sort_values("timestamp")
        return frame

    def _volume_history(self, symbol, now, context):
        retained = [c for c in self.store.list_records("chart_futures_contracts", 100)
                    if c.get("symbol") == symbol and c.get("identity_verified")]
        current = context.get("futures_contract", {})
        active = sorted((c for c in retained if c.get("expiry", "") >= str(now.date())), key=lambda c: c["expiry"])
        contract = (current if current.get("identity_verified") and current.get("expiry", "") >= str(now.date())
                    else active[0] if active else retained[0] if retained else {})
        if not contract:
            return {}, pd.DataFrame(), None
        frame = self._history(symbol, now, contract)
        same_contract = (current.get("contract_id"), current.get("expiry")) == (contract["contract_id"], contract["expiry"])
        if same_contract and context.get("futures_candles"):
            recent = pd.DataFrame(context["futures_candles"])
            recent["timestamp"] = pd.to_datetime(recent.timestamp, utc=True)
            recent["symbol"] = symbol
            frame = pd.concat([frame, recent], ignore_index=True).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        captures = [contract.get("captured_at"), context.get("captured_at") if same_contract else None]
        captures.extend(c.get("captured_at") for c in retained if
                        (c.get("contract_id"), c.get("expiry")) == (contract["contract_id"], contract["expiry"]))
        return contract, frame, max((stamp for stamp in captures if stamp), default=None)

    def _volume_series(self, symbol, now, context):
        """One observed contract per session; never sum overlapping expiries."""
        current, current_frame, captured = self._volume_history(symbol, now, context)
        retained = self.store.list_records("chart_futures_contracts", 100)
        contracts = {(c.get("contract_id"), c.get("expiry")): c for c in retained
                     if c.get("symbol") == symbol and c.get("identity_verified")}
        if current:
            contracts[(current["contract_id"], current["expiry"])] = current
        selected = {}
        for key, contract in sorted(contracts.items(), key=lambda item: item[0][1]):
            frame = current_frame if key == (current.get("contract_id"), current.get("expiry")) else self._history(symbol, now, contract)
            if frame.empty:
                continue
            frame = frame.copy()
            frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
            days = frame.timestamp.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")
            frame = frame[days <= contract["expiry"]]
            frame["contract_id"], frame["expiry"] = contract["contract_id"], contract["expiry"]
            for day, part in frame.groupby(frame.timestamp.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")):
                # Prefer the earliest unexpired retained contract with data for this day.
                # A missing minute within it is not patched with another expiry.
                selected.setdefault(day, part)
        frame = pd.concat(selected.values(), ignore_index=True).sort_values("timestamp") if selected else pd.DataFrame()
        return current, frame, captured

    @staticmethod
    def volume_bars(frame, now, symbol, size):
        if frame is None or frame.empty:
            return []
        if "contract_id" not in frame:
            return chart_bars(frame, now, symbol, size, volume=True)
        bars = []
        for (identifier, expiry), part in frame.groupby(["contract_id", "expiry"]):
            bars.extend({**bar, "contract_id": identifier, "expiry": expiry}
                        for bar in chart_bars(part, now, symbol, size, volume=True))
        return sorted(bars, key=lambda bar: bar["time"])

    def snapshot(self, symbol, period):
        now = now_ist()
        with self.engine.lock:
            frame = self.engine.frames.get(symbol)
            frame = frame.copy() if frame is not None else None
            state = deepcopy(self.engine.status)
        # Expensive disk/structure projection is cached; live ticks are projected every poll.
        key = (symbol, str(now.date()), str(frame.timestamp.iloc[-1]) if frame is not None and not frame.empty else "disk")
        with self.lock:
            saved = self.cache.get(symbol)
            if saved is None or saved[0] != key or time.monotonic()-saved[1] >= 30:
                history = self._history(symbol, now)
                if frame is None or frame.empty:
                    frame = history
                elif not history.empty:
                    # Current engine candles supersede saved versions at the same timestamp.
                    frame = pd.concat([history, frame], ignore_index=True)
                    frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
                    frame = frame.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
                source = "Retained Dhan history + current engine candles"
                structure = analyze_structure(frame, now, symbol, lookback_days=HISTORY_DAYS, zone_limit_per_side=24)
                contexts = self.store.list_records("market_context_inputs", 30)
                context = next((c for c in contexts if c.get("symbol") == symbol and c.get("futures_candles")), {})
                volume_contract, future, volume_captured = self._volume_series(symbol, now, context)
                trades = [{k: t.get(k) for k in ("id", "symbol", "contract_id", "option_type", "entry_ts", "exit_ts", "entry", "exit", "pnl")}
                          for t in self.store.list_records("trades", 300) if t.get("symbol") == symbol]
                saved = (key, time.monotonic(), frame, structure, source, volume_contract, future, volume_captured, trades, {}, {})
                self.cache[symbol] = saved
            _, _, frame, structure, source, volume_contract, future, volume_captured, trades, bar_cache, volume_cache = saved
            if period not in bar_cache:
                bar_cache[period] = chart_bars(frame, now, symbol, PERIODS[period])
            retained_bars = bar_cache[period]
            if period not in volume_cache:
                volume_cache[period] = self.volume_bars(future, now, symbol, PERIODS[period])
            volumes = volume_cache[period]
        with self.market.lock:
            tick = deepcopy(self.market.latest.get(symbol, {}))
            ticks = [e.get("normalized", {}) for e in list(self.market.recent_market_events) if e.get("event_type") == "market_feed"]
            connected = self.market.connected
        now = now_ist()  # Compare fresh ticks after potentially slow history work.
        ticks.append(tick)
        start_today = pd.Timestamp(now).normalize()
        today = frame[frame.timestamp >= start_today] if frame is not None and not frame.empty else frame
        bars = [bar for bar in retained_bars if bar["time"] < start_today.timestamp()]
        bars += chart_bars(today, now, symbol, PERIODS[period], ticks)
        exchange_stamp = tick.get("exchange_timestamp")
        try:
            age = (pd.Timestamp(now)-pd.Timestamp(exchange_stamp)).total_seconds() if exchange_stamp else None
        except (ValueError, TypeError):
            age = None
        # The exchange clock can lead the receive clock by a few seconds.
        # Keep the actual timestamp; future minutes remain excluded above.
        live = bool(connected and age is not None and -5 <= age <= 5 and now.weekday() < 5 and
                    not calendar_info(now.date())["closed"] and "09:15" <= now.strftime("%H:%M") < "15:30")
        portfolio = state.get("portfolio", {})
        evaluations = [r for r in portfolio.get("evaluations", []) if r.get("symbol") == symbol]
        return {"symbol": symbol, "period": period, "generated_at": now.isoformat(), "session": session_state(now),
                "live": live, "tick_age_seconds": age, "tick": tick, "candles": bars, "source": source,
                "history_days": HISTORY_DAYS,
                "structure": structure,
                "volume": {"bars": volumes, "contract": volume_contract,
                           "captured_at": volume_captured, "source": "Dhan fixed-contract futures minute candles",
                           "from": volumes[0]["time"] if volumes else None,
                           "to": volumes[-1]["end_time"] if volumes else None,
                           "contracts": list({(bar.get("contract_id"), bar.get("expiry")): {"contract_id": bar.get("contract_id"), "expiry": bar.get("expiry")} for bar in volumes if bar.get("contract_id")}.values()),
                           "reason": "Recorded futures contracts by session; earliest unexpired contract with saved data. Contract changes are marked, volumes are not summed across expiries, and missing minutes remain gaps. Colours follow futures candle direction." if volumes else "No recorded futures volume available for this timeframe."},
                "decision": {"evaluations": evaluations, "scan": state.get("scans", {}).get(symbol, {}),
                             "reason": portfolio.get("reason"), "selected": portfolio.get("selected")},
                "outcomes": state.get("outcome_estimates", {}).get(symbol, {}),
                "trades": trades,
                "probabilities": {"status": "INSUFFICIENT_EVIDENCE", "calibrated": False,
                                  "reason": "No validated directional or zone-response probability model is deployed."}}
