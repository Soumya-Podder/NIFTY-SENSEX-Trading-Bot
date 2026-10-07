"""Worker liveness is independent of market-data availability and strategy edge."""
from .session import now_ist, local_time, session_state, quote_is_fresh
import pandas as pd


def completed_candles_ready(frames,health,now):
    return {symbol:frame is not None and not frame.empty and
        frame.timestamp.iloc[-1].date()==now.date() and
        60<=(pd.Timestamp(now)-frame.timestamp.iloc[-1]).total_seconds()<=125 and
        health.get(symbol,{}).get("candle_status") not in {"ERROR","WAITING"}
        for symbol,frame in frames.items()}


def execution_health(engine, broker, now=None):
    now=now or now_ist()
    stamp=engine.status.get("last_cycle")
    try: age=(local_time(now)-local_time(stamp)).total_seconds() if stamp else None
    except (ValueError,TypeError): age=None
    threads=getattr(engine,"threads",[])
    dead=[t.name for t in threads if not t.is_alive()]
    # A parallel heartbeat may advance after the caller captured ``now``.
    # Treat that recent heartbeat as current, while still rejecting large
    # clock discrepancies and genuinely old heartbeats.
    if age is not None and -15<=age<0: age=0.0
    fresh=age is not None and 0<=age<=15
    errors={key:engine.status[key] for key in ("error","persistence_error","selector_error","feed_watch_error",
            "data_error","quote_error","entry_error","exit_error","protection_error") if engine.status.get(key)}
    broker_health=broker.health()
    healthy=fresh and bool(threads) and not dead and not errors and broker_health["healthy"]
    # A rejected entry is an audit result, not a permanent readiness latch.
    symbol_error=bool(errors.get("data_error")) and any(
        health.get("error")==errors["data_error"] for health in engine.status.get("data_symbols",{}).values())
    operational=fresh and bool(threads) and not dead and not {k:v for k,v in errors.items()
        if k!="entry_error" and not (k=="data_error" and symbol_error)} and broker_health["healthy"]
    advisory={key:engine.status[key] for key in ("feedback_error","context_errors","signal_journal_error","management_error","paper_learning_error","fee_preparation_error","recovery_journal_error") if engine.status.get(key)}
    renewal=engine.status.get("credential_renewal") or {}
    if renewal.get("status") in {"EXPIRED","RENEWAL_FAILED"}: advisory["credential_renewal"]=renewal
    return {"healthy":healthy,"operational":operational,"heartbeat_age_seconds":age,"dead_workers":dead,
            "workers":[{"name":t.name,"alive":t.is_alive()} for t in threads],
            "advisory_errors":advisory,
            "errors":errors,"broker":broker_health,"market_execution_validated":False}


def trading_readiness(runtime,account,market,quotes,recorder,settings,now=None,*,candles_ready=None):
    """Readiness is separate from process liveness and never predicts a fill."""
    now=now or now_ist()
    session=session_state(now,start=settings.session_start,cutoff=settings.entry_cutoff,exit_at=settings.session_exit)
    blockers=[]
    if not runtime.get("operational",runtime["healthy"]): blockers.append("WORKERS_OR_PERSISTENCE_UNHEALTHY")
    if session!="ENTRY_WINDOW": blockers.append(session)
    if not account["enabled"]: blockers.append("PAPER_PAUSED")
    if account["halted"]: blockers.append("PAPER_HALTED")
    if account["positions"]: blockers.append("POSITION_ALREADY_OPEN")
    if not market.get("connected"): blockers.append("FEED_DISCONNECTED")
    if not recorder.get("worker_alive") or recorder.get("error"): blockers.append("QUOTE_RECORDER_UNAVAILABLE")
    symbols={}
    for symbol in ("NIFTY","SENSEX"):
        missing=[]
        if candles_ready is not None and not candles_ready.get(symbol): missing.append("COMPLETED_CANDLES_UNAVAILABLE")
        if not quote_is_fresh(market.get("symbols",{}).get(symbol,{}),now,settings.underlying_quote_age_seconds):
            missing.append("INDEX_QUOTE_STALE")
        if not market.get("options_by_symbol",{}).get(symbol,{}).get("fresh_depth",0): missing.append("OPTION_DEPTH_UNAVAILABLE")
        symbols[symbol]={"data_ready":not missing,"blockers":missing}
    if not any(v["data_ready"] for v in symbols.values()): blockers.append("NO_INDEX_HAS_ENTRY_DATA")
    exits=[]
    for p in account["positions"]:
        q=quotes.get(p["contract_id"],{})
        executable=quote_is_fresh(q,now,settings.max_quote_age_seconds) and q.get("bid",0)>0 and q.get("bid_qty",0)>=p["lot_size"]
        exits.append({"position_id":p["id"],"contract_id":p["contract_id"],"executable":executable,
            "full_depth":bool(executable and q.get("bid_qty",0)>=p["qty"]),"pending":p.get("exit_request"),
            "reason":None if executable else "FRESH_HELD_CONTRACT_DEPTH_UNAVAILABLE"})
    return {"session":session,"entry_ready":not blockers,"entry_blockers":blockers,"symbols":symbols,
        "exit_status":"NO_POSITION" if not exits else "EXECUTABLE" if all(p["executable"] for p in exits) else "WAITING_FOR_DEPTH",
        "positions":exits,"recorder":recorder,"scope":"Data and operating readiness only; every candidate still requires risk approval."}
