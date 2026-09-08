import math
from .models import Direction


def greek_scenario(contract, underlying_change, iv_change, elapsed_time, *,
                   iv_change_unit="decimal", time_unit="day", actual_option_path=False):
    """Return a unit-checked local Greek scenario, or an explicit unavailable result.

    This is explanatory risk math only. When actual option candles are replayed,
    their observed premium path already includes these effects and this function
    must not be subtracted from P&L a second time.
    """
    value=lambda key: contract.get(key) if isinstance(contract, dict) else getattr(contract, key, None)
    if actual_option_path:
        return {"available":False,"reason":"actual_option_candles_already_include_greek_effects",
                "double_counting":True}
    units=value("greek_units") or {}
    required_units={"delta":"premium_per_index_point","gamma":"premium_per_index_point_squared",
                    "vega":"premium_per_iv_decimal" if iv_change_unit=="decimal" else "premium_per_iv_percentage_point",
                    "theta":f"premium_per_{time_unit}"}
    if any(units.get(key)!=expected for key,expected in required_units.items()):
        return {"available":False,"reason":"greek_units_unverified","required_units":required_units,
                "observed_units":units or None}
    if not all(_finite(value(key)) for key in ("delta","gamma","vega","theta","lot_size")):
        return {"available":False,"reason":"greeks_or_lot_size_unavailable"}
    if not all(_finite(v) for v in (underlying_change,iv_change,elapsed_time)):
        return {"available":False,"reason":"scenario_input_unavailable"}
    per_unit=(float(value("delta"))*float(underlying_change)
              +.5*float(value("gamma"))*float(underlying_change)**2
              +float(value("vega"))*float(iv_change)
              +float(value("theta"))*float(elapsed_time))
    lot_size=float(value("lot_size"))
    return {"available":True,"per_option_unit":per_unit,"per_lot":per_unit*lot_size,
            "lot_size":int(lot_size),"iv_change_unit":iv_change_unit,"time_unit":time_unit,
            "greeks_source":value("greeks_source"),"greeks_observed_at":value("greeks_observed_at"),
            "greek_age_seconds":value("greek_age_seconds")}


def _finite(value):
    try: return math.isfinite(float(value))
    except (TypeError,ValueError): return False


class OptionSelector:
    def __init__(self,min_oi=100,max_spread_pct=.08): self.min_oi=min_oi; self.max_spread_pct=max_spread_pct
    def score(self,c,target_delta=.5):
        if not all(_finite(getattr(c,key,None)) for key in ("ltp","bid","ask","oi","volume","delta")):
            c.score=-1; return c
        c.spread_pct=max(c.ask-c.bid,0)/max(c.ltp,1e-9)
        if c.ltp<=0 or c.oi<self.min_oi or c.spread_pct>self.max_spread_pct: c.score=-1; return c
        liq=min(1,c.volume/1000+c.oi/10000)
        delta=max(0,1-abs(abs(c.delta)-target_delta))
        c.score=.45*liq+.35*delta+.20*(1-c.spread_pct/self.max_spread_pct)
        return c
    def select(self,contracts,direction):
        want="CE" if direction==Direction.CALL else "PE"
        cs=[self.score(c) for c in contracts if c.option_type==want]
        cs=[c for c in cs if c.score>=0]
        return max(cs,key=lambda c:c.score) if cs else None
