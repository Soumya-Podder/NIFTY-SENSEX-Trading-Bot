"""Worker liveness is independent of market-data availability and strategy edge."""
from .session import now_ist, local_time


def execution_health(engine, broker, now=None):
    now=now or now_ist()
    stamp=engine.status.get("last_cycle")
    try: age=(local_time(now)-local_time(stamp)).total_seconds() if stamp else None
    except (ValueError,TypeError): age=None
    threads=getattr(engine,"threads",[])
    dead=[t.name for t in threads if not t.is_alive()]
    fresh=age is not None and 0<=age<=15
    errors={key:engine.status[key] for key in ("error","persistence_error","selector_error","feed_watch_error") if engine.status.get(key)}
    broker_health=broker.health()
    healthy=fresh and bool(threads) and not dead and not errors and broker_health["healthy"]
    return {"healthy":healthy,"heartbeat_age_seconds":age,"dead_workers":dead,
            "errors":errors,"broker":broker_health,"market_execution_validated":False}
