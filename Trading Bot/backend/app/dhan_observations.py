"""Retain documented market fields and compare like-for-like option observations."""
import json
import math
import re
import zlib
import pandas as pd
from .quote_recorder import QuoteRecorder

MARKET_METHODS = {"option_chain", "expiry_list", "quote_data", "ticker_data", "ohlc_data",
                  "intraday_minute_data", "historical_daily_data", "expired_options_data"}
MARKET_FIELDS = set("""data oc ce pe last_price average_price greeks delta gamma theta vega
    implied_volatility oi previous_oi previous_volume previous_close_price security_id
    top_ask_price top_ask_quantity top_bid_price top_bid_quantity volume open high low close
    timestamp start_Time strike spot iv depth buy sell price quantity orders ohlc
    last_quantity last_trade_time net_change oi_day_high oi_day_low upper_circuit_limit
    lower_circuit_limit average_volume buy_quantity sell_quantity NSE_EQ NSE_FNO BSE_EQ
    BSE_FNO IDX_I MCX_COMM NSE_CURRENCY BSE_CURRENCY open_interest""".split())
SAFE_VALUE = re.compile(r"(?:[0-9][0-9T :./+-]*|IDX_I|INDEX|OPTIDX|FUTIDX|NSE_FNO|BSE_FNO|CE|PE|CALL|PUT|ATM(?:[+-][0-9]+)?|WEEK|MONTH)")


def market_fields(value):
    """No headers, client IDs, tokens, free-text errors or account/order payloads."""
    if isinstance(value, dict):
        return {str(k): market_fields(v) for k, v in value.items()
                if str(k) in MARKET_FIELDS or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", str(k))}
    if isinstance(value, (list, tuple)):
        return [market_fields(v) for v in value]
    if value is None or isinstance(value, bool): return value
    if isinstance(value, (int, float)): return value if math.isfinite(value) else None
    if isinstance(value, str) and (value in MARKET_FIELDS or SAFE_VALUE.fullmatch(value)): return value
    return None


class DhanResponseRecorder(QuoteRecorder):
    def record_response(self,method,args,result,generation,received_at,*,outcome="SUCCESS"):
        if method not in MARKET_METHODS: return None
        payload={"method":method,"request":market_fields(args),"outcome":outcome,
                 "response":market_fields(result) if outcome=="SUCCESS" else None,
                 "timestamp_basis":"HTTP receipt, not exchange update time"}
        return self._enqueue("dhan_api",zlib.compress(json.dumps(payload,allow_nan=False).encode()),
                             generation,received_at)

    def read(self,identifier):
        result=super().read(identifier)
        if result: result["response"]=result.pop("quote")
        return result

    def status(self):
        return {**super().status(),"mode":"compressed_dhan_market_responses",
                "limitations":["Documented market fields only; no credentials, headers, order/account data or error text.",
                    "Cache hits are not new responses. Missing exchange timestamps cannot be reconstructed.",
                    "Queue drops, storage limits and unclean shutdowns leave coverage gaps; existing data is not deleted."]}


CHANGE_FIELDS = {"oi":"oi", "volume":"volume", "ltp":"last_price", "iv":"implied_volatility",
                 "bid":"top_bid_price", "ask":"top_ask_price", "bid_qty":"top_bid_quantity",
                 "ask_qty":"top_ask_quantity", "delta":"delta", "gamma":"gamma", "theta":"theta", "vega":"vega"}


def number(value, signed=False):
    if isinstance(value,bool): return None
    try:
        n=float(value)
        return n if math.isfinite(n) and (signed or n>=0) else None
    except (ValueError,TypeError): return None


def chain_legs(chain):
    rows={}; identities=set()
    for strike, legs in chain.get("oc",{}).items():
        strike_number=number(strike)
        if strike_number is None or strike_number<=0: continue
        for side in ("ce","pe"):
            leg=legs.get(side) or {}; sid=str(leg.get("security_id",""))
            if not sid.isdigit() or int(sid)<=0: continue
            # A provider ID reused across strikes/sides is ambiguous.
            if sid in identities: return None
            identities.add(sid)
            rows[(sid,strike_number,side)]={**leg,**(leg.get("greeks") or {})}
    return rows


def compare_chains(current,previous):
    unavailable={"status":"DATA_UNAVAILABLE","reason":"Awaiting a second fresh chain response"}
    if not previous: return unavailable
    if not current.get("_request_key") or current.get("_request_key")!=previous.get("_request_key"):
        return {**unavailable,"reason":"Underlying or expiry request changed"}
    try:
        before=pd.Timestamp(previous.get("_observed_at")); after=pd.Timestamp(current.get("_observed_at"))
        if before.tzinfo is None or after.tzinfo is None: return unavailable
        elapsed=(after-before).total_seconds()
        if elapsed<=0 or before.tz_convert("Asia/Kolkata").date()!=after.tz_convert("Asia/Kolkata").date():
            return {**unavailable,"reason":"No earlier same-session observation"}
    except (ValueError,TypeError): return unavailable
    old=chain_legs(previous); new=chain_legs(current)
    if old is None or new is None: return {**unavailable,"reason":"Ambiguous provider contract identities"}
    matched=old.keys() & new.keys(); changes={}
    for key in sorted(matched):
        sid,strike,side=key; differences={}
        for label,field in CHANGE_FIELDS.items():
            a=number(old[key].get(field),label in {"delta","theta"})
            b=number(new[key].get(field),label in {"delta","theta"})
            differences[label]=b-a if a is not None and b is not None else None
        volume_reset=differences["volume"] is not None and differences["volume"]<0
        if volume_reset: differences["volume"]=None
        changes[sid]={"security_id":sid,"strike":strike,"option_type":"CALL" if side=="ce" else "PUT",
                      "changes":differences,"volume_status":"RESET_OR_CORRECTION" if volume_reset else
                          "OBSERVED" if differences["volume"] is not None else "DATA_UNAVAILABLE"}
    return {"status":"OBSERVED" if matched else "DATA_UNAVAILABLE",
            "reason":None if matched else "No matching fixed contracts",
            "observed_at":current["_observed_at"],"previous_observed_at":previous["_observed_at"],
            "previous_response_id":previous.get("_api_capture_id"),"interval_seconds":elapsed,
            "long_gap":elapsed>120,"matched_contracts":len(matched),"added_contracts":len(new.keys()-old.keys()),
            "removed_contracts":len(old.keys()-new.keys()),"contracts":changes,
            "basis":"Same provider security ID, strike, side and request expiry; HTTP receipt timestamps",
            "interpretation":"Unsigned OI changes; volume is change in cumulative day volume, not buyer/seller identity"}
