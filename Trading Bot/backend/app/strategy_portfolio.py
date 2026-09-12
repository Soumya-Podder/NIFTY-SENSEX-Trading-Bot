"""Frozen, causal paper hypotheses. Scores are not probabilities of profit."""
import hashlib
import math
import pandas as pd
from .indicators import add_features
from .setups import opening_range_retest

PORTFOLIO_VERSION = "multi-strategy-paper-v1"
STRATEGIES = (
    {"id":"orb_retest","name":"Opening-range retest","version":"orb-retest-v1",
     "condition":"Opening-range break, retest and completed resumption","horizon_minutes":10},
    {"id":"trend_pullback","name":"Trend pullback","version":"trend-pullback-v1",
     "condition":"ADX >= 25, aligned EMA 9/21 and completed pullback resumption","horizon_minutes":10},
    {"id":"range_rejection","name":"Range rejection","version":"range-rejection-v1",
     "condition":"ADX <= 20, flat EMA 21 and rejection of a prior 30-minute range","horizon_minutes":5},
)


def closed_session(frame, now):
    if frame is None or frame.empty: return None,"Waiting for index candles"
    now=pd.Timestamp(now)
    now=now.tz_localize("Asia/Kolkata") if now.tzinfo is None else now.tz_convert("Asia/Kolkata")
    f=frame.copy()
    f["timestamp"]=pd.to_datetime(f.timestamp)
    if f.timestamp.dt.tz is None: f["timestamp"]=f.timestamp.dt.tz_localize("Asia/Kolkata")
    else: f["timestamp"]=f.timestamp.dt.tz_convert("Asia/Kolkata")
    # Cut before calculating ANY features; a future row cannot influence a score.
    f=f[f.timestamp+pd.Timedelta(minutes=1)<=now].sort_values("timestamp")
    start=now.normalize()+pd.Timedelta(hours=9,minutes=15)
    today=f[f.timestamp>=start]
    if today.empty: return None,"Waiting for today's completed candles"
    if now-today.timestamp.iloc[-1]>pd.Timedelta(seconds=125): return None,"Completed candle is stale"
    if list(today.timestamp)!=list(pd.date_range(start,periods=len(today),freq="min")):
        return None,"Missing or duplicate session candles"
    for k in ("open","high","low","close"):
        if not today[k].map(lambda v:isinstance(v,(int,float)) and math.isfinite(v) and v>0).all():
            return None,"Invalid session OHLC"
    if ((today.high<today[["open","close"]].max(axis=1)) | (today.low>today[["open","close"]].min(axis=1))).any():
        return None,"Inconsistent session OHLC"
    if len(today)<20: return None,"Building opening range and warm-up candles"
    if "volume" not in f: f["volume"]=float("nan")
    featured=add_features(f)
    return featured[featured.timestamp>=start].reset_index(drop=True),None


def signal_for(candidate,spec,symbol,regime):
    stamp=candidate["timestamp"]
    identity=f"{PORTFOLIO_VERSION}|{spec['version']}|{symbol}|{stamp}|{candidate['option_type']}"
    return {**candidate,"id":hashlib.sha256(identity.encode()).hexdigest()[:24],"symbol":symbol,
        "strategy_id":spec["id"],"strategy_name":spec["name"],"strategy_version":spec["version"],
        "portfolio_version":PORTFOLIO_VERSION,"regime":regime,"horizon_minutes":spec["horizon_minutes"],
        "agent_contexts":{"Scanner":"completed_bars","Regime":regime,"Setup":candidate["setup"],
                          "Confirmation":"completed_resumption"},"policy_versions":{},
        "evidence_mode":"paper_observation","execution_ready":False}


def evaluate_strategies(frame,now,symbol):
    bars,problem=closed_session(frame,now)
    return evaluate_completed_bars(bars,now,symbol,problem)


def evaluate_completed_bars(bars,now,symbol,problem=None,*,orb_candidate="evaluate"):
    """Shared rules for live prefixes and a validated, causal historical prefix.

    Replay must validate continuity/OHLC and compute features from the same
    seven-calendar-day warmup before calling this lower-level entry point.
    An optional precomputed ORB candidate avoids rescanning each prefix.
    """
    rows=[{**s,"symbol":symbol,"status":"WAITING","reason":problem or "Setup conditions not met",
           "evidence":"UNVALIDATED_PAPER","checked_at":pd.Timestamp(now).isoformat()} for s in STRATEGIES]
    if bars is None: return [],rows
    last=bars.iloc[-1]; prev=bars.iloc[-2]; atr=float(last.atr)
    for row in rows: row["last_bar"]=last.timestamp.isoformat()
    if not math.isfinite(atr) or atr<=0: return [],rows
    slope=(float(last.ema21)-float(bars.iloc[-6].ema21))/atr
    regime="TREND_UP" if last.adx>=25 and last.ema9>last.ema21 and slope>=.2 else (
        "TREND_DOWN" if last.adx>=25 and last.ema9<last.ema21 and slope<=-.2 else
        "RANGE" if last.adx<=20 and abs(slope)<=.15 else "TRANSITION")
    for row in rows: row["regime"]=regime
    signals=[]
    orb=opening_range_retest(bars,now) if orb_candidate=="evaluate" else orb_candidate
    if orb:
        signals.append(signal_for(orb,STRATEGIES[0],symbol,regime))
        rows[0].update(status="CANDIDATE",reason="Completed opening-range breakout, retest and resumption")
    else: rows[0]["reason"]="No completed opening-range retest/resumption"
    base={"timestamp":last.timestamp.isoformat(),"available_at":(last.timestamp+pd.Timedelta(minutes=1)).isoformat(),
          "retest_timestamp":prev.timestamp.isoformat(),"underlying_entry":float(last.close)}
    direction=None
    if regime=="TREND_UP" and prev.low<=prev.ema21+.25*atr and prev.close>prev.ema21 and last.close>prev.high:
        direction="CALL"
    elif regime=="TREND_DOWN" and prev.high>=prev.ema21-.25*atr and prev.close<prev.ema21 and last.close<prev.low:
        direction="PUT"
    if direction and abs(last.close-last.ema21)<=1.5*atr:
        c={**base,"option_type":direction,"setup":"TREND_PULLBACK_"+("LONG" if direction=="CALL" else "SHORT"),
           "invalidation":float(min(prev.low,last.ema21) if direction=="CALL" else max(prev.high,last.ema21)),
           "evidence":["ema9_21_alignment","adx_trend","ema21_pullback","completed_resumption"]}
        signals.append(signal_for(c,STRATEGIES[1],symbol,regime))
        rows[1].update(status="CANDIDATE",reason="Trend pullback resumed without excessive extension")
    else: rows[1]["reason"]="Trend strength, EMA pullback or resumption not confirmed"
    if regime=="RANGE" and len(bars)>=32:
        window=bars.iloc[-32:-2]; low=float(window.low.min()); high=float(window.high.max()); mid=(high+low)/2
        direction=None
        if high-low>=2*atr:
            if prev.low<=low+.15*atr and prev.close>low and last.close>prev.high and mid-last.close>=1.2*atr: direction="CALL"
            elif prev.high>=high-.15*atr and prev.close<high and last.close<prev.low and last.close-mid>=1.2*atr: direction="PUT"
        if direction:
            c={**base,"option_type":direction,"setup":"RANGE_REJECTION_"+("LONG" if direction=="CALL" else "SHORT"),
               "invalidation":float(prev.low if direction=="CALL" else prev.high),"underlying_target":mid,
               "evidence":["low_adx_flat_ema","prior_30m_range","boundary_rejection","room_to_midpoint"]}
            signals.append(signal_for(c,STRATEGIES[2],symbol,regime))
            rows[2].update(status="CANDIDATE",reason="Range boundary rejected; price has room to return toward midpoint")
        else: rows[2]["reason"]="No confirmed range rejection with sufficient room to midpoint"
    else: rows[2]["reason"]="Range regime or 32 completed session bars not available"
    feature_row={k:(None if pd.isna(last.get(k)) else last.get(k)) for k in
        ("timestamp","close","atr","adx","vwap_distance_atr","relative_volume","rsi")}
    feature_row["timestamp"]=str(last.timestamp)
    feature_row["ema_slope_atr"]=slope
    for signal in signals: signal["feature_row"]=feature_row
    return signals,rows


def rank_opportunities(offers):
    """Rank only eligible offers; statistical support precedes observation economics.

    Observation ranking uses reward-at-target / all-in stop risk, not an invented
    win probability. Stable ties avoid an incidental NIFTY-first execution bias.
    """
    return sorted(offers,key=lambda o:(
        -int(o["ev"]["status"]=="PASS"),
        -float((o["ev"].get("lower_bound_rupees") or 0)/o["risk"]),
        -o["net_reward_risk"],o["contract"]["spread_pct"],
        o["signal"]["strategy_id"],o["signal"]["symbol"],o["contract"]["contract_id"]))
