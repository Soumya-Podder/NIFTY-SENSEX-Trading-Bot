"""Causal paper exit state. A stop is a request, never a guaranteed fill."""
import math
from .session import local_time

VERSION = "adaptive_observed_v1"


def update_exit(position, bid, now, exit_cost=None, completed_bar=None):
    """Persistable state; only fresh observed bids may call this function.

    ATR must come from completed same-contract candles before entry. No index
    ATR, delta conversion, or guessed volatility is substituted for option ATR.
    A completed bar supplied by replay is processed after that bar's old stop.
    """
    if position.get("exit_policy") != VERSION or not math.isfinite(bid) or bid <= 0:
        return
    p = position
    initial = p.setdefault("initial_stop", p["stop"])
    risk = p["entry"] - initial
    if risk <= 0:
        return
    p["peak_bid"] = max(p.get("peak_bid", p["entry"]), bid)
    tick = float(p.get("tick_size") or .05)
    peak = p["peak_bid"]
    if exit_cost is not None and math.isfinite(exit_cost) and exit_cost >= 0 and peak >= p["entry"] + risk:
        fees = p.get("entry_charges_remaining", p.get("entry_charges", {}).get("total", 0)) + exit_cost
        fee_stop = math.ceil((p["entry"] + fees / p["qty"] + tick) / tick) * tick
        # Do not move a stop above the currently executable bid.
        if fee_stop < bid:
            p["stop"] = max(p["stop"], round(fee_stop, 8))
            p["adaptive_state"] = "COST_COVERING_STOP_REQUESTED"
    atr = p.get("option_atr")
    if not isinstance(atr, (float, int)) or not math.isfinite(atr) or atr <= 0:
        p["adaptive_data_status"] = "Option ATR unavailable; trailing and stall checks withheld"
        return
    if peak >= p["entry"] + 1.2 * risk:
        distance = (.35 if local_time(now).hour >= 13 else .5) * atr
        stop = math.floor((peak - distance) / tick) * tick
        if stop < bid:
            p["stop"] = max(p["stop"], round(stop, 8))
            p["adaptive_state"] = "TRAILING"
    # Track completed minute bid bars, rejecting partial entry-minute bars and
    # gaps over five seconds. Restart gaps therefore cannot imply momentum stall.
    minute = local_time(now).replace(second=0, microsecond=0)
    if completed_bar is None:
        bar = p.get("adaptive_bar")
        previous = p.get("adaptive_last_quote")
        if bar and previous and (local_time(now) - local_time(previous)).total_seconds() > 5:
            bar["complete"] = False
        if bar and bar["timestamp"] != minute.isoformat():
            if bar["complete"] and (minute-local_time(bar["timestamp"])).total_seconds() == 60:
                completed_bar = bar
            else:
                p["stall_bars"] = []
            bar = None
        if not bar:
            bar = {"timestamp": minute.isoformat(), "high": bid, "low": bid,
                   "complete": local_time(now).second <= 5 and minute > local_time(p["entry_ts"])}
        bar.update(high=max(bar["high"], bid), low=min(bar["low"], bid))
        p["adaptive_bar"] = bar
        p["adaptive_last_quote"] = local_time(now).isoformat()
    if completed_bar:
        bars = p.setdefault("stall_bars", [])
        if bars and bars[-1]["timestamp"] == str(completed_bar["timestamp"]):
            return
        if bars and (local_time(completed_bar["timestamp"])-local_time(bars[-1]["timestamp"])).total_seconds() != 60:
            bars.clear()
        bars.append({"timestamp": str(completed_bar["timestamp"]), "high": completed_bar["high"], "low": completed_bar["low"]})
        p["stall_bars"] = bars[-5:]
        bars = p["stall_bars"]
        if len(bars) == 5 and all(b["high"] <= bars[0]["high"] and b["high"]-b["low"] < .5*atr for b in bars[1:]):
            p["adaptive_exit_request"] = "MOMENTUM_STALL"
