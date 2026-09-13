from datetime import datetime, time
from zoneinfo import ZoneInfo
from .market_calendar import calendar_info

IST=ZoneInfo("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)


def local_time(value):
    if isinstance(value,str): value=datetime.fromisoformat(value.replace("Z","+00:00"))
    return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


def session_state(now=None, *, start="09:15", cutoff="14:30", exit_at="15:05"):
    now=local_time(now or now_ist())
    if now.weekday()>=5: return "WEEKEND"
    if calendar_info(now.date())["closed"]: return "HOLIDAY"
    clock=now.time().replace(tzinfo=None)
    if clock<time.fromisoformat(start): return "PREOPEN"
    if clock>=time.fromisoformat(exit_at): return "EXIT_ONLY"
    if clock>=time.fromisoformat(cutoff): return "MANAGE_ONLY"
    return "ENTRY_WINDOW"


def quote_is_fresh(quote, now=None, max_age=2):
    # A last-trade timestamp is not evidence that the bid/ask book was
    # refreshed. Runtime adapters must provide quote_update_timestamp. The
    # fallback keeps isolated legacy fixtures readable; Dhan REST snapshots
    # explicitly set the field to None and therefore fail closed.
    if "quote_update_timestamp" in quote:
        stamp=quote.get("quote_update_timestamp")
    else:
        stamp=quote.get("exchange_timestamp")
    if not stamp: return False
    try:
        age=(local_time(now or now_ist())-local_time(stamp)).total_seconds()
        return 0<=age<=max_age and quote.get("source") not in {"dhan_quote_snapshot","unavailable"}
    except (ValueError,TypeError): return False
