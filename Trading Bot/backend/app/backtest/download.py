"""Download raw 5-year historical market data from Dhan directly into local project storage."""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from ..config import Settings, current_credentials
from ..store import Store
from ..market_data import DhanGateway
from ..session import now_ist

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def download_index_candles(gateway, symbol, start_date, end_date, chunk_days=28):
    """Download continuous minute candles from Dhan in chunks with permanent SQLite caching."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    chunks = []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=chunk_days), end)
        chunks.append((str(cursor.date()), str(stop.date())))
        cursor = stop

    frames = []
    total = len(chunks)
    print(f"\n=======================================================")
    print(f"Downloading {symbol} 1-minute data from {start_date} to {end_date}")
    print(f"Total chunks: {total} (each ~{chunk_days} days)")
    print(f"Target: {DATA_DIR / f'{symbol}_5yr_1min.csv'}")
    print(f"=======================================================")

    for i, (a, b) in enumerate(chunks, 1):
        try:
            df = gateway.candles(symbol, a, b, cache_seconds=-1)
            if not df.empty:
                frames.append(df)
            print(f"[{i:02d}/{total:02d}] {symbol} {a} to {b}: {len(df):>5d} candles")
            time.sleep(0.15)
        except Exception as exc:
            print(f"[{i:02d}/{total:02d}] {symbol} {a} to {b} [ERROR]: {exc}")
            time.sleep(0.5)

    if not frames:
        print(f"No candles retrieved for {symbol}.")
        return None

    full_df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    out_csv = DATA_DIR / f"{symbol}_5yr_1min.csv"
    full_df.to_csv(out_csv, index=False)
    size_mb = out_csv.stat().st_size / (1024 * 1024)
    print(f"\n>> SUCCESS: {symbol} complete!")
    print(f"   Total bars: {len(full_df):,}")
    print(f"   Range: {full_df['timestamp'].iloc[0]} to {full_df['timestamp'].iloc[-1]}")
    print(f"   File size: {size_mb:.2f} MB")
    print(f"   Saved at: {out_csv}\n")
    return out_csv


def main():
    parser = argparse.ArgumentParser(description="Download raw 5-year historical NIFTY and SENSEX data from Dhan")
    parser.add_argument("--years", type=int, default=5, help="Number of years of history to download (default: 5)")
    parser.add_argument("--symbols", nargs="+", default=["NIFTY", "SENSEX"], help="Symbols to download (default: NIFTY SENSEX)")
    parser.add_argument("--end-date", type=str, default=None, help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    settings = Settings()
    store = Store(Path(__file__).resolve().parents[2] / "trading_bot.db")
    gateway = DhanGateway(settings, store, credential_provider=current_credentials)

    end = pd.Timestamp(args.end_date).date() if args.end_date else now_ist().date()
    start = (pd.Timestamp(end) - pd.DateOffset(years=args.years)).date()

    print(f"Initiating Dhan 5-year data download for: {', '.join(args.symbols)}")
    print(f"Timeframe: {start} to {end} ({args.years} years)")
    print(f"Destination: {DATA_DIR}")

    for sym in args.symbols:
        download_index_candles(gateway, sym, str(start), str(end))


if __name__ == "__main__":
    main()
