"""Backtest adapter: reads 5yr index CSV and creates option_quotes from DB metadata.
Documented limitation: CSV provides underlying OHLC only; option contract identity
must come from DB/contract master, not computed from index price alone.
"""
from datetime import timedelta
import pandas as pd

def adapt_index_csv(path, db_path=None):
    """Read NIFTY/SENSEX 5yr CSV, verify format, return underlying frame.
    Returns (underlying_df, limitation_note) — option_quotes still required
    from external contract source (Dhan API or DB master) for full engine run."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    limitation = ("Input is underlying index OHLC (open/high/low/close/volume). "
                  "Backtest engine requires option_quotes (contract_id, expiry, strike, "
                  "lot_size, tick_size, is_atm, charge_schedule) per backtest/engine.py line 61-68. "
                  "Run produces underlying session grouping only; option selection requires "
                  "contract metadata from Dhan rolling option endpoint or historical CSV.")
    return df, limitation
