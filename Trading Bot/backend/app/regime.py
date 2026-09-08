import pandas as pd
from .models import RegimeResult

class RegimeEngine:
    def classify(self,row):
        keys=["ema9","ema21","ema50","atr"]
        if any(pd.isna(row[k]) for k in keys):
            return RegimeResult(regime="DATA_UNSAFE",confidence=0,evidence=["missing_feature"])
        has_vwap=pd.notna(row.get("vwap"))
        if row.ema9>row.ema21>row.ema50 and (not has_vwap or row.close>row.vwap):
            return RegimeResult(regime="TREND_UP",confidence=.75,evidence=["ema_stack_up","above_vwap" if has_vwap else "vwap_unavailable"])
        if row.ema9<row.ema21<row.ema50 and (not has_vwap or row.close<row.vwap):
            return RegimeResult(regime="TREND_DOWN",confidence=.75,evidence=["ema_stack_down","below_vwap" if has_vwap else "vwap_unavailable"])
        if row.atr_percentile>=.8:
            return RegimeResult(regime="VOLATILITY_EXPANSION",confidence=.7,evidence=["high_atr_percentile"])
        if row.atr_percentile<=.2:
            return RegimeResult(regime="VOLATILITY_COMPRESSION",confidence=.7,evidence=["low_atr_percentile"])
        return RegimeResult(regime="RANGE",confidence=.55,evidence=["no_trend_alignment"])
