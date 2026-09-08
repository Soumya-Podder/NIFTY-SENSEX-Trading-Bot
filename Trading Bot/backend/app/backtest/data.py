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
