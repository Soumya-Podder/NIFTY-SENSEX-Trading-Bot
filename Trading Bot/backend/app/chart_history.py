"""Retain missing index minute history for the terminal: python -m app.chart_history."""
from datetime import timedelta
from pathlib import Path
from .chart_terminal import HISTORY_DAYS
from .config import settings, current_credentials
from .market_data import DhanGateway
from .session import now_ist
from .store import Store


def download_futures_history(gateway, store, symbol, now):
    contract = gateway.futures_contract(symbol, now)
    end = now.date()
    start = end-timedelta(days=90)
    data = gateway.call(gateway.client.intraday_minute_data, contract["security_id"],
                        contract["exchange"]+"_FNO", "FUTIDX", str(start), str(end), 1, False,
                        cache_seconds=-1)
    store.save_bundle([("chart_futures_contracts", contract["contract_id"]+":"+contract["expiry"],
                       {**contract, "captured_at": now.isoformat()})])
    print(f"{symbol} futures {contract['contract_id']} expiry {contract['expiry']}: "
          f"{len(data.get('timestamp', []))} candles, "
          f"{sum(v > 0 for v in data.get('volume', []))} with reported volume", flush=True)


def main():
    root = Path(__file__).resolve().parents[2]
    store = Store(root / "backend" / "trading_bot.db")
    gateway = DhanGateway(settings, store, credential_provider=current_credentials)
    gateway.refresh_credentials()
    # Exclude the unfinished current session from permanent historical ranges.
    end = now_ist().date()
    start = end-timedelta(days=HISTORY_DAYS)
    for symbol in ("NIFTY", "SENSEX"):
        cursor, total = start, 0
        # Dhan accepts at most 90 days per intraday request; saved overlaps are reused.
        while cursor < end:
            stop = min(cursor+timedelta(days=90), end)
            frame = gateway.candles(symbol, cursor, stop, cache_seconds=-1)
            total += len(frame)
            print(f"{symbol}: {cursor} to {stop}: {len(frame)} minute observations retained", flush=True)
            cursor = stop
        print(f"{symbol}: {total} observations, requested {start} to {end}", flush=True)
        download_futures_history(gateway, store, symbol, now_ist())


if __name__ == "__main__":
    main()
