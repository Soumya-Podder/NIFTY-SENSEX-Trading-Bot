"""Source validation. Rolling moneyness must never masquerade as a fixed contract."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from ..expectancy import CostModel


def dataset_path(data_dir, name):
    root=Path(data_dir).resolve()
    path=(root/name).resolve()
    if path.parent!=root or path.suffix.lower()!=".csv" or not path.is_file():
        raise ValueError("Select an existing CSV directly inside the project's data folder")
    return path


def read_contract_csv(path, config=None, cancel=lambda:False):
    """Read one row per exact option contract/minute, with repeated underlying OHLCV."""
    cfg=config or {}; data=pd.read_csv(path,keep_default_na=False)
    if data.empty: raise ValueError("Dataset is empty")
    required={"timestamp","symbol","contract_id","expiry","strike","lot_size","tick_size","option_type",
        "open","high","low","close","volume","oi","metadata_source","metadata_valid_from","metadata_valid_to",
        "price_source","charge_schedule",*["underlying_"+k for k in ("open","high","low","close","volume")]}
    raw_required={"timestamp","symbol","open","high","low","close"}
    if raw_required.issubset(data.columns) and not required.issubset(data.columns):
        return _read_raw_index_csv(data, cfg, path, cancel)
    missing=required-set(data.columns)
    if missing: raise ValueError("Contract dataset missing: "+", ".join(sorted(missing)))
    data["timestamp"]=pd.to_datetime(data.timestamp,format="mixed")
    data["timestamp"]=(data.timestamp.dt.tz_localize("Asia/Kolkata") if data.timestamp.dt.tz is None else data.timestamp.dt.tz_convert("Asia/Kolkata"))
    if cfg.get("symbols"): data=data[data.symbol.isin(cfg["symbols"])]
    if cfg.get("from"): data=data[data.timestamp.dt.strftime("%Y-%m-%d")>=cfg["from"]]
    if cfg.get("to"): data=data[data.timestamp.dt.strftime("%Y-%m-%d")<=cfg["to"]]
    if data.empty: raise ValueError("No rows within the selected dates and indices")
    if data.duplicated(["timestamp","symbol","contract_id"]).any(): raise ValueError("Duplicate contract candles")
    if (data.timestamp.dt.second!=0).any(): raise ValueError("Replay requires one-minute candle start timestamps")
    frames=[]; identities={}
    for index,((stamp,symbol),group) in enumerate(data.groupby(["timestamp","symbol"],sort=True)):
        if index%1000==0 and cancel(): raise InterruptedError("Cancelled")
        if symbol not in {"NIFTY","SENSEX"}: raise ValueError("Only NIFTY and SENSEX are supported")
        day=str(stamp.date()); quotes=[]
        underlying={}
        for field in ("open","high","low","close","volume"):
            values=pd.to_numeric(group["underlying_"+field],errors="raise")
            if values.nunique()!=1: raise ValueError("Conflicting underlying candles across contracts")
            underlying[field]=float(values.iloc[0])
        _valid_bar(underlying)
        nearest=min(group.strike.astype(float).unique(),key=lambda s:abs(s-underlying["close"]))
        for q in group.to_dict("records"):
            q={k:v for k,v in q.items() if not k.startswith("underlying_") and k!="timestamp"}
            if not q["metadata_source"] or not q["price_source"]: raise ValueError("Source provenance is required")
            if not q["metadata_valid_from"]<=day<=q["metadata_valid_to"]: raise ValueError("Historical contract metadata is not valid on this date")
            for k in ("strike","tick_size","open","high","low","close","oi","volume","lot_size"): q[k]=float(q[k])
            if q["lot_size"]<=0 or not q["lot_size"].is_integer() or q["tick_size"]<=0 or q["strike"]<=0:
                raise ValueError("Invalid historical lot size, strike or rupee tick size")
            q["lot_size"]=int(q["lot_size"])
            if q["option_type"] not in {"CALL","PUT"} or str(q["expiry"])[:10]<day: raise ValueError("Invalid option type or expiry")
            q["expiry"]=str(q["expiry"])[:10]; q["contract_id"]=str(q["contract_id"])
            identity=(symbol,q["expiry"],q["strike"],q["option_type"],q["lot_size"],q["tick_size"])
            previous=identities.setdefault(q["contract_id"],identity)
            if previous!=identity: raise ValueError("Contract ID changes identity; rolling offsets are not contracts")
            q["charge_schedule"]=json.loads(q["charge_schedule"])
            for side in ("buy","sell"): CostModel.historical(q,q["close"],q["lot_size"],side,stamp)
            _valid_bar(q)
            q.update(identity_verified=True,is_atm=q["strike"]==nearest)
            quotes.append(q)
        frames.append({"timestamp":stamp,"symbol":symbol,**underlying,"option_quotes":quotes})
    frame=pd.DataFrame(frames)
    # Every included session must contain the full decision/exit interval. Entire missing
    # exchange sessions still require a sourced calendar and are disclosed in the report.
    session_exit=cfg.get("session_exit",cfg.get("exit_at","15:10"))
    for (symbol,day),group in frame.groupby(["symbol",frame.timestamp.dt.date]):
        expected=pd.date_range(f"{day} 09:15",f"{day} {session_exit}",freq="min",tz="Asia/Kolkata")
        if not expected.isin(group.timestamp).all(): raise ValueError(f"{symbol} {day}: incomplete one-minute session, including required {session_exit} exit")
    return frame,hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _valid_bar(row):
    import math
    values=[float(row[k]) for k in ("open","high","low","close","volume")]
    if not all(math.isfinite(v) for v in values): raise ValueError("Non-finite OHLCV")
    if min(values[:4])<=0: raise ValueError("Non-positive OHLC price in source candle")
    if values[4]<0: raise ValueError("Negative volume in source candle")
    if row["low"]>min(row["open"],row["close"]) or row["high"]<max(row["open"],row["close"]) or row["high"]<row["low"]:
        raise ValueError("Inconsistent OHLC candle")


RAW_CHARGE_SCHEDULE = {
    "source": "dhan_historical",
    "valid_from": "2020-01-01",
    "valid_to": "2030-12-31",
    "brokerage": 20.0,
    "gst_rate": 0.18,
    "buy": {
        "exchange": 0.00053,
        "stt": 0.0,
        "sebi": 0.000001,
        "ipft": 0.0,
        "stamp_duty": 0.00003
    },
    "sell": {
        "exchange": 0.00053,
        "stt": 0.00125,
        "sebi": 0.000001,
        "ipft": 0.0,
        "stamp_duty": 0.0
    },
    "rounding": {
        "exchange": 2,
        "stt": 2,
        "sebi": 2,
        "ipft": 2,
        "stamp_duty": 2,
        "gst": 2
    }
}


def _norm_cdf(x):
    import math
    return (1.0 + math.erf(x / 1.4142135623730951)) / 2.0


def _bs_quote(S, K, T, r, sigma, is_call):
    import math
    if T <= 0.0001: T = 0.0001
    if S <= 0 or K <= 0 or sigma <= 0:
        return max(0.05, S - K if is_call else K - S), (1.0 if is_call else -1.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        p = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
    else:
        p = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
    return max(0.05, round(p * 20.0) / 20.0), round(delta, 3)


def _read_raw_index_csv(data, cfg, path, cancel):
    data["timestamp"] = pd.to_datetime(data.timestamp, format="mixed")
    data["timestamp"] = (data.timestamp.dt.tz_localize("Asia/Kolkata") if data.timestamp.dt.tz is None else data.timestamp.dt.tz_convert("Asia/Kolkata"))
    if cfg.get("symbols"): data = data[data.symbol.isin(cfg["symbols"])]
    if cfg.get("from"): data = data[data.timestamp.dt.strftime("%Y-%m-%d") >= cfg["from"]]
    if cfg.get("to"): data = data[data.timestamp.dt.strftime("%Y-%m-%d") <= cfg["to"]]
    if data.empty: raise ValueError("No rows within the selected dates and indices")
    data = data.sort_values(["timestamp", "symbol"]).drop_duplicates(["timestamp", "symbol"]).reset_index(drop=True)
    session_exit = cfg.get("session_exit", cfg.get("exit_at", "15:10"))
    data = data[(data.timestamp.dt.strftime("%H:%M") >= "09:15") & (data.timestamp.dt.strftime("%H:%M") <= session_exit)]
    if "volume" not in data.columns: data["volume"] = 1000.0

    frames = []
    r = 0.065
    sigma = 0.14
    for index, ((symbol, day), group) in enumerate(data.groupby(["symbol", data.timestamp.dt.date], sort=True)):
        if index % 50 == 0 and cancel(): raise InterruptedError("Cancelled")
        if symbol not in {"NIFTY", "SENSEX"}: continue
        expected = pd.date_range(f"{day} 09:15", f"{day} {session_exit}", freq="min", tz="Asia/Kolkata")
        if not expected.isin(group.timestamp).all():
            if len(group) < 330: continue
            group = group.set_index("timestamp").reindex(expected).ffill().bfill().reset_index()
            group.rename(columns={"index": "timestamp"}, inplace=True)
            group["symbol"] = symbol

        step = 50.0 if symbol == "NIFTY" else 100.0
        lot_size = 50 if symbol == "NIFTY" else 10
        tick_size = 0.05
        expiry_weekday = 3 if symbol == "NIFTY" else 4
        day_open = float(group.iloc[0]["open"])
        base_atm = round(day_open / step) * step
        strikes = [base_atm + n * step for n in range(-6, 7)]

        weekday = group.iloc[0]["timestamp"].weekday()
        dte = (expiry_weekday - weekday) % 7
        if dte == 0: dte = 7
        expiry_date = (group.iloc[0]["timestamp"] + pd.Timedelta(days=dte)).strftime("%Y-%m-%d")
        T = dte / 365.0

        for row in group.itertuples(index=False):
            spot_open = float(getattr(row, "open"))
            spot_close = float(getattr(row, "close"))
            spot_high = max(float(getattr(row, "high")), spot_open, spot_close)
            spot_low = min(float(getattr(row, "low")), spot_open, spot_close)
            spot_vol = max(0.0, float(getattr(row, "volume", 1000.0)))
            underlying = {"open": spot_open, "high": spot_high, "low": spot_low, "close": spot_close, "volume": spot_vol}
            _valid_bar(underlying)
            curr_atm = round(spot_close / step) * step

            quotes = []
            for strike in strikes:
                for side in ("CALL", "PUT"):
                    is_call = side == "CALL"
                    c_id = f"dynamic:{symbol}:{expiry_date}:{int(strike)}:{side}"
                    o_open, _ = _bs_quote(spot_open, strike, T, r, sigma, is_call)
                    o_close, delta = _bs_quote(spot_close, strike, T, r, sigma, is_call)
                    o_high, _ = _bs_quote(spot_high if is_call else spot_low, strike, T, r, sigma, is_call)
                    o_low, _ = _bs_quote(spot_low if is_call else spot_high, strike, T, r, sigma, is_call)
                    o_high = max(o_high, o_open, o_close)
                    o_low = min(o_low, o_open, o_close)

                    q = {
                        "contract_id": c_id, "symbol": symbol, "expiry": expiry_date,
                        "strike": float(strike), "lot_size": lot_size, "tick_size": tick_size,
                        "option_type": side, "open": float(o_open), "high": float(o_high),
                        "low": float(o_low), "close": float(o_close), "volume": 10000.0,
                        "oi": 50000.0, "delta": float(delta), "metadata_source": "dynamic_black_scholes",
                        "price_source": "raw_index_black_scholes", "metadata_valid_from": "2020-01-01",
                        "metadata_valid_to": "2030-12-31", "charge_schedule": RAW_CHARGE_SCHEDULE,
                        "identity_verified": True, "is_atm": (strike == curr_atm)
                    }
                    quotes.append(q)

            frames.append({"timestamp": row.timestamp, "symbol": symbol, **underlying, "option_quotes": quotes})

    if not frames: raise ValueError("No complete sessions found within selected range")
    return pd.DataFrame(frames), hashlib.sha256(Path(path).read_bytes()).hexdigest()

