"""Causal portfolio-rule replay with the same seven-day warmup as the live scanner."""
import pandas as pd
import math
from ..indicators import add_features
from ..strategy_portfolio import evaluate_completed_bars, STRATEGIES
from ..setups import opening_range_retest

MODES={s['id'] for s in STRATEGIES}|{'portfolio'}


def historical_signals(frame, mode, cancel=lambda:False):
    if mode not in MODES: raise ValueError('Unknown strategy replay mode')
    result={}
    for symbol, history in frame.groupby('symbol'):
        history=history.sort_values('timestamp').copy()
        stamps=pd.to_datetime(history.timestamp)
        if stamps.dt.tz is None: stamps=stamps.dt.tz_localize('Asia/Kolkata')
        else: stamps=stamps.dt.tz_convert('Asia/Kolkata')
        history['timestamp']=stamps
        for day in sorted(set(stamps.dt.normalize())):
            if cancel(): raise InterruptedError('Cancelled')
            # All feature operators are trailing. Calculate once per session,
            # preserving the same bounded seed history used by the live loader.
            warm=history[(history.timestamp>=day-pd.Timedelta(days=7)) & (history.timestamp<day+pd.Timedelta(days=1))]
            featured=add_features(warm)
            bars=featured[featured.timestamp>=day].reset_index(drop=True)
            expected=pd.date_range(day+pd.Timedelta(hours=9,minutes=15),periods=len(bars),freq='min')
            orbs={c['timestamp']:c for c in opening_range_retest(bars,bars.timestamp.max()+pd.Timedelta(minutes=1),all_candidates=True)}
            for index in range(len(bars)):
                if index%100==0 and cancel(): raise InterruptedError('Cancelled')
                row=bars.iloc[index]
                # A missing/duplicate bar invalidates every later prefix that day.
                if row.timestamp!=expected[index]: break
                if not all(pd.notna(row[k]) and math.isfinite(row[k]) and row[k]>0 for k in ('open','high','low','close')): break
                if row.low>min(row.open,row.close) or row.high<max(row.open,row.close): break
                if index<19: continue
                stamp=row.timestamp
                signals,_=evaluate_completed_bars(bars.iloc[:index+1],stamp+pd.Timedelta(minutes=1),symbol,
                                                 orb_candidate=orbs.get(stamp.isoformat()))
                result[(stamp.isoformat(),symbol)]=[s for s in signals if mode=='portfolio' or s['strategy_id']==mode]
    return result
