"""Exploratory missing-price liquidation; never an observed candle or live fill."""
import math
import pandas as pd


def estimate_gap_exit(position, timestamp, previous_candle=None, haircut=0.05):
    """Use only the preceding minute, then liquidate instead of inventing a path."""
    if not 0 <= haircut <= .25:
        raise ValueError("Scenario haircut must be between 0 and 25 percent")
    timestamp=pd.Timestamp(timestamp)
    previous=timestamp-pd.Timedelta(minutes=1)
    if previous_candle is not None:
        if pd.Timestamp(previous_candle.get("observed_at")) != previous:
            return None
        if previous_candle.get("contract_id") != position["contract_id"]:
            return None
        base=previous_candle.get("close")
        basis="preceding_observed_close"
    elif pd.Timestamp(position["entry_time"]) == previous:
        base=position.get("entry_premium")
        basis="preceding_observed_entry"
    else:
        return None
    if not isinstance(base,(float,int)) or not math.isfinite(base) or base<=0:
        return None
    return {"price":round(base*(1-haircut),4),"basis":basis,
            "reference_price":base,"reference_time":previous.isoformat(),
            "estimated_at":timestamp.isoformat(),"haircut":haircut,
            "method":"previous_observation_exit_v1",
            "note":"Scenario exit, not a sourced historical quote or a guaranteed conservative fill."}
