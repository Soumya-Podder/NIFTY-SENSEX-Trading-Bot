from .models import Direction, SetupCandidate
import math
import pandas as pd


def opening_range_retest(frame, now, buffer_atr=.1, retest_bars=5, *, all_candidates=False):
    """Causal baseline candidate from start-stamped, completed one-minute bars.

    A strict three-minute close breaks the range plus its ATR buffer. A later
    minute must touch the broken boundary and close strictly outside it; a
    subsequent close beyond the retest extreme confirms resumption. Equality
    never confirms a break/resumption. Missing/duplicate session bars invalidate
    the sequence. This price-only setup does not invent index volume or fills.
    """
    empty=[] if all_candidates else None
    if frame.empty:
        return empty
    if not math.isfinite(buffer_atr) or buffer_atr < 0 or retest_bars < 1:
        raise ValueError("Invalid opening-range configuration")
    now = pd.Timestamp(now)
    now = now.tz_localize("Asia/Kolkata") if now.tzinfo is None else now.tz_convert("Asia/Kolkata")
    bars = frame.copy()
    stamps = pd.to_datetime(bars.timestamp)
    stamps = stamps.dt.tz_localize("Asia/Kolkata") if stamps.dt.tz is None else stamps.dt.tz_convert("Asia/Kolkata")
    bars["timestamp"] = stamps
    start = now.normalize() + pd.Timedelta(hours=9, minutes=15)
    bars = bars[(stamps >= start) & (stamps + pd.Timedelta(minutes=1) <= now)].sort_values("timestamp")
    if all_candidates:
        # A later gap must not erase an earlier decision. Stop at the first
        # unavailable/invalid bar, matching online prefix evaluation exactly.
        count=0
        duplicate_stamps=set(bars.loc[bars.timestamp.duplicated(keep=False),"timestamp"])
        for row in bars.itertuples(index=False):
            values=[getattr(row,k) for k in ("open","high","low","close")]
            if (row.timestamp != start+pd.Timedelta(minutes=count) or row.timestamp in duplicate_stamps or
                not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in values) or
                row.high<max(row.open,row.close) or row.low>min(row.open,row.close)):
                break
            count+=1
        bars=bars.iloc[:count]
    if len(bars) < 20 or bars.timestamp.duplicated().any():
        return empty
    expected = pd.date_range(start, periods=len(bars), freq="min")
    if list(bars.timestamp) != list(expected):
        return empty
    for key in ("open", "high", "low", "close"):
        if not bars[key].map(lambda v: isinstance(v, (int, float)) and math.isfinite(v) and v > 0).all():
            return empty
    if ((bars.high < bars[["open", "close"]].max(axis=1)) | (bars.low > bars[["open", "close"]].min(axis=1))).any():
        return empty
    bars = bars.reset_index(drop=True)
    high, low = float(bars.iloc[:15].high.max()), float(bars.iloc[:15].low.min())
    pending = None; candidates=[]
    for i in range(15, len(bars)):
        row = bars.iloc[i]
        if pending:
            sign, boundary = pending["sign"], pending["boundary"]
            if sign * (row.close - boundary) <= 0 or i - pending["break_index"] > retest_bars:
                pending = None
            elif pending.get("retest_index") is not None:
                if sign * (row.close - pending["resumption"]) > 0:
                    if not all_candidates and i != len(bars) - 1:
                        pending = None
                        continue
                    candidate={"setup": "ORB_RETEST_LONG" if sign == 1 else "ORB_RETEST_SHORT",
                            "option_type": "CALL" if sign == 1 else "PUT",
                            "timestamp": row.timestamp.isoformat(),
                            "available_at": (row.timestamp + pd.Timedelta(minutes=1)).isoformat(),
                            "underlying_entry": float(row.close), "invalidation": boundary,
                            "opening_high": high, "opening_low": low,
                            "break_timestamp": bars.iloc[pending["break_index"]].timestamp.isoformat(),
                            "retest_timestamp": bars.iloc[pending["retest_index"]].timestamp.isoformat(),
                            "evidence": ["completed_3m_break", "completed_1m_retest", "later_1m_resumption", "price_only"]}
                    if not all_candidates: return candidate
                    candidates.append(candidate); pending=None
                    continue
            elif (row.low <= boundary if sign == 1 else row.high >= boundary):
                pending.update(retest_index=i, resumption=float(row.high if sign == 1 else row.low))
        if pending is None and (i + 1) % 3 == 0:
            atr = row.get("atr")
            if atr is None or not math.isfinite(float(atr)) or atr <= 0:
                continue
            sign = 1 if row.close > high + buffer_atr * atr else -1 if row.close < low - buffer_atr * atr else 0
            if sign:
                pending = {"sign": sign, "boundary": high if sign == 1 else low, "break_index": i}
    return candidates if all_candidates else None

class SetupEngine:
    def evaluate(self,row,orh,orl):
        c=float(row.close); a=max(float(row.atr),1e-9); out=[]
        if orh is not None and c>orh and row.relative_volume>=1.2:
            out.append(SetupCandidate(setup_id="ORB_LONG",direction=Direction.CALL,confidence=.72,
                entry_reference=c,invalidation=orh,stop_percent=.12,target_percent=.24,
                evidence=["orb_breakout","volume_expansion"]))
        if orl is not None and c<orl and row.relative_volume>=1.2:
            out.append(SetupCandidate(setup_id="ORB_SHORT",direction=Direction.PUT,confidence=.72,
                entry_reference=c,invalidation=orl,stop_percent=.12,target_percent=.24,
                evidence=["orb_breakdown","volume_expansion"]))
        if c>row.vwap and row.ema9>row.ema21 and row.relative_volume>=1.1:
            out.append(SetupCandidate(setup_id="VWAP_LONG",direction=Direction.CALL,confidence=.65,
                entry_reference=c,invalidation=float(row.vwap),stop_percent=.10,target_percent=.20,
                evidence=["above_vwap","ema_confirmation"]))
        if c<row.vwap and row.ema9<row.ema21 and row.relative_volume>=1.1:
            out.append(SetupCandidate(setup_id="VWAP_SHORT",direction=Direction.PUT,confidence=.65,
                entry_reference=c,invalidation=float(row.vwap),stop_percent=.10,target_percent=.20,
                evidence=["below_vwap","ema_confirmation"]))
        if row.ema9>row.ema21 and c>=row.ema21 and abs(c-row.ema21)<=.5*a:
            out.append(SetupCandidate(setup_id="EMA_PULLBACK_LONG",direction=Direction.CALL,confidence=.60,
                entry_reference=c,invalidation=float(row.ema21)-a,stop_percent=.10,target_percent=.18,
                evidence=["uptrend","ema21_pullback"]))
        if row.ema9<row.ema21 and c<=row.ema21 and abs(c-row.ema21)<=.5*a:
            out.append(SetupCandidate(setup_id="EMA_PULLBACK_SHORT",direction=Direction.PUT,confidence=.60,
                entry_reference=c,invalidation=float(row.ema21)+a,stop_percent=.10,target_percent=.18,
                evidence=["downtrend","ema21_pullback"]))
        if row.atr_percentile<=.25 and row.relative_volume>=1.5:
            d=Direction.CALL if c>row.vwap else Direction.PUT
            out.append(SetupCandidate(setup_id="COMPRESSION_BREAKOUT",direction=d,confidence=.58,
                entry_reference=c,invalidation=c-a if d==Direction.CALL else c+a,
                stop_percent=.12,target_percent=.25,evidence=["atr_compression","volume_expansion"]))
        return out
