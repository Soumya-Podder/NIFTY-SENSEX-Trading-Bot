"""Replay captured inputs through the active autonomous paper engine, without HTTP/orders."""
from collections import defaultdict, Counter
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import sqlite3
import uuid
import zlib
import pandas as pd

from ..autonomous_paper import AutonomousPaperEngine
from ..autonomous_policy import VERSION
from ..broker import PaperBroker
from ..store import Store, json_safe
from ..risk import PlanRiskPolicy, SIZING_VERSION
from ..session import session_state, quote_is_fresh
from ..market_structure import analyze_structure
from ..market_context import build_context
from ..dhan_observations import compare_chains
from ..expectancy import CostModel
from .reports import report_from_run
from .metrics import metrics


def captured_events(data_dir, start, end, cancel=lambda: False, *, compact_books=False):
    if cancel(): raise InterruptedError("Cancelled")
    files = sorted((Path(data_dir)/"market_observations").glob("*.db"))
    files += [p for p in (Path(data_dir)/"market_observations.db", Path(data_dir)/"dhan_api_observations.db") if p.exists()]
    events, seen, contracts = [], set(), {}
    begin = str(pd.Timestamp(start)-pd.Timedelta(days=7))[:10]
    for path in files:
        if cancel(): raise InterruptedError("Cancelled")
        # API responses supply indicator warmup. Normalized quote archives
        # supply this session's executable books and daily policy marker.
        lower = begin if path.name == "dhan_api_observations.db" else start
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            connection.set_progress_handler(lambda: int(cancel()), 10000)
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='observations'").fetchone(): continue
            # One bounded time-index walk avoids SQLite's multi-index OR and
            # disk-backed sort on the retained multi-gigabyte legacy archive.
            query = "SELECT id,received_at,kind,generation,payload FROM observations WHERE received_at>=? AND received_at<? AND (kind IN ('dhan_api','runtime_policy') OR received_at>=?) ORDER BY received_at,id"
            try:
                for identifier, stamp, kind, generation, raw in connection.execute(query, (lower, str(pd.Timestamp(end)+pd.Timedelta(days=1))[:10], start)):
                    if cancel(): raise InterruptedError("Cancelled")
                    if identifier in seen or kind not in {"dhan_api", "option_depth", "underlying", "feed_disconnected", "runtime_policy"}: continue
                    seen.add(identifier)
                    payload = raw if kind == "dhan_api" else json.loads(zlib.decompress(raw) if isinstance(raw, bytes) else raw)
                    event={"id": identifier, "at": pd.Timestamp(stamp), "kind": kind, "generation": generation, "payload": payload}
                    if compact_books and kind=="option_depth":
                        # Millions of decoded books otherwise exhaust memory before replay starts.
                        cid=payload.get("contract_id")
                        if cid and payload.get("identity_verified"):
                            event["contract"]=contracts.setdefault(cid,payload)
                        event["payload"]=raw if isinstance(raw,bytes) else zlib.compress(raw.encode(),1)
                    events.append(event)
            except sqlite3.OperationalError:
                if cancel(): raise InterruptedError("Cancelled")
                raise
    return sorted(events, key=lambda e: (e["at"], e["id"]))


def candle_frame(raw):
    fields = ("timestamp", "open", "high", "low", "close", "volume")
    stamps = raw.get("timestamp", [])
    if not stamps or any(len(raw.get(k, [])) != len(stamps) for k in fields): return pd.DataFrame(columns=fields)
    frame = pd.DataFrame({k: raw[k] for k in fields})
    frame["timestamp"] = pd.to_datetime(frame.timestamp, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    return frame.sort_values("timestamp")


class ReplayStore(Store):
    """Reconstructable replay ledger; the primary account keeps FULL durability."""
    @contextmanager
    def _conn(self, timeout=30):
        with super()._conn(timeout) as connection:
            # WAL remains consistent across application crashes. An interrupted
            # run after power loss must be rerun before a report can be accepted.
            connection.execute("PRAGMA synchronous=NORMAL")
            yield connection


class ReplayMarket:
    def __init__(self):
        self.latest, self.books, self.chain = {}, {}, {}
        self.generation = 0
        self.recorder = None

    def executable_quotes(self):
        result = {}
        for cid, book in self.books.items():
            contract = self.chain.get(book.get("symbol"), {}).get(cid)
            if contract: result[cid] = {**contract, **book, "strike_universe": contract["strike_universe"]}
        return result

    def snapshot(self): return {"symbols": deepcopy(self.latest)}

    def execution_snapshot(self, symbol):
        return {"underlying": dict(self.latest.get(symbol, {})),
                "options": {k: v for k, v in self.executable_quotes().items() if v.get("symbol") == symbol}}


class ReplayGateway:
    def __init__(self):
        self.frames = {}
        self.credential_generation = 0
        self.credential_provider = None

    def contract_candles(self, contract, start, end, *, cache_seconds=30):
        frame = self.frames.get(str(contract["security_id"]))
        if frame is None: raise ValueError("Recorded selected-contract candle response unavailable at this time")
        return frame.copy()


class RecordedFeeScenario(CostModel):
    def __init__(self, store, contracts, clock):
        super().__init__()
        self.clock = clock
        self.templates = defaultdict(list)
        self.unknown_receipt_time = False
        with store._conn() as connection:
            fees = [json.loads(zlib.decompress(r[0])) for r in connection.execute("SELECT payload FROM history_cache WHERE key GLOB 'charges:*'")]
            fees.extend(json.loads(r[0]) for r in connection.execute("SELECT payload FROM records WHERE namespace='broker_fee_receipts'"))
        contracts_by_id = {c["contract_id"]: c for c in contracts}
        seen = set()
        for fee in fees:
            if not fee or fee.get("kind") != "broker_calculator_quote": continue
            receipt_key = (fee.get("request_fingerprint"), fee.get("as_of"), fee.get("captured_at"))
            if receipt_key in seen: continue
            seen.add(receipt_key)
            matching = [contracts_by_id[fee["contract_id"]]] if fee.get("contract_id") in contracts_by_id else contracts
            for contract in matching:
                body = {"source": "N", "data": {"exchange": contract["exchange"], "segment": "D", "txn_type": "S",
                    "qty": int(fee["quantity"]//contract["lot_size"]), "window": "SHORT_TRADE", "security_id": str(contract["security_id"]),
                    "sell_price": fee["sell_price"], "buy_price": fee["buy_price"], "product": "I", "instrument": "OPTIDX", "exchange1": ""}}
                digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
                if digest == fee.get("request_fingerprint"):
                    self.templates[contract["contract_id"]].append(fee)

    def quote(self, contract, buy_price, sell_price, qty):
        templates = [f for f in self.templates[contract["contract_id"]]
                     if f["quantity"] == qty and f["as_of"] == str(self.clock().date()) and
                     bool(f["sell_price"]) == bool(sell_price) and bool(f["buy_price"]) == bool(buy_price) and
                     (not f.get("captured_at") or pd.Timestamp(f["captured_at"]) <= self.clock())]
        if not templates: raise ValueError("No same-day recorded broker fee scenario for this contract and quantity")
        chosen = max(templates, key=lambda f: f["total"])
        if not chosen.get("captured_at"): self.unknown_receipt_time = True
        multiplier = max(1, (buy_price+sell_price)/(chosen["buy_price"]+chosen["sell_price"]))
        return {**chosen, "total": chosen["total"]*multiplier, "estimated": True,
                "kind": "recorded_prequote_fee_scenario", "basis": "Conservative same-day broker prequote; historical executed charges are unavailable"}


class ReplayEngine(AutonomousPaperEngine):
    def publish(self, item):
        item["timestamp"] = self._now().isoformat()
        self.store.record_event(item)  # Never publish replay events to the live UI bus.

    def _request_protection(self, signal, contract):
        key = (signal["id"], contract["contract_id"])
        self.prepare_protection(key, {"signal": signal, "contract": contract, "generation": self.gateway.credential_generation})
        result = self.protection_results.get(key, {})
        return result.get("candle"), result.get("reason")


def decision_blocker_history(store):
    """Keep earlier data waits when a candidate's final state later expires."""
    reasons, data_waits = {}, set()
    with store._conn() as connection:
        for (payload,) in connection.execute("SELECT payload FROM records WHERE namespace='events'"):
            item = json.loads(payload)
            if item.get("agent") == "Option Selector" and item.get("status") == "WAITING" and item.get("signal_id"):
                data_waits.add(item["signal_id"])
            if item.get("agent") != "Orchestrator" or item.get("status") != "WAIT": continue
            reason = item.get("evaluation", {}).get("evidence")
            if not isinstance(reason, str) or not reason: continue
            stamp, symbol = item["timestamp"], item.get("symbol", "SYSTEM")
            row = reasons.setdefault(reason, {"reason": reason, "checks": 0, "first_at": stamp, "last_at": stamp, "by_symbol": {}})
            row["checks"] += 1
            row["first_at"], row["last_at"] = min(row["first_at"], stamp), max(row["last_at"], stamp)
            row["by_symbol"][symbol] = row["by_symbol"].get(symbol, 0)+1
    return sorted(reasons.values(), key=lambda row: (-row["checks"], row["reason"])), data_waits


def normalized_chain(event, metadata, index_ids, previous):
    request, raw = event["payload"].get("request", []), event["payload"].get("response") or {}
    if len(request) < 3 or str(request[0]) not in index_ids: return None
    symbol, expiry = index_ids[str(request[0])], str(request[2])[:10]
    if expiry <= str(event["at"].date()): return None
    strikes = [float(k) for k in raw.get("oc", {})]
    spot = float(raw.get("last_price") or 0)
    if not strikes or spot <= 0: return None
    raw = {**raw, "_observed_at": event["at"].isoformat(), "_request_key": symbol+expiry, "_api_capture_id": event["id"]}
    comparison = compare_chains(raw, previous.get(symbol))
    previous[symbol] = raw
    rows = []
    for strike, legs in raw["oc"].items():
        for side, option_type in (("ce", "CALL"), ("pe", "PUT")):
            leg = legs.get(side) or {}
            contract = metadata.get((str(event["at"].date()), str(leg.get("security_id"))))
            if not contract or contract.get("expiry") != expiry or contract.get("strike") != float(strike) or contract.get("option_type") != option_type: continue
            rows.append({**contract, **(leg.get("greeks") or {}), "spot": spot, "ltp": leg.get("last_price"),
                "oi": leg.get("oi"), "previous_oi": leg.get("previous_oi"), "volume": leg.get("volume"), "iv": leg.get("implied_volatility"),
                "greeks_observed_at": event["at"].isoformat(), "greeks_source": "dhan_option_chain",
                "chain_observed_at": event["at"].isoformat(), "api_response_id": event["id"], "strike_universe": strikes,
                "is_atm": float(strike) == min(strikes, key=lambda k: abs(k-spot)),
                "observation_change": {**{k: v for k, v in comparison.items() if k != "contracts"}, "contract": comparison.get("contracts", {}).get(contract["security_id"])}})
    return symbol, rows


def run_replay(*, store, gateway, settings, data_dir, start, end, cancel=lambda: False, progress=None, candidate=None, symbols=("NIFTY", "SENSEX")):
    if progress: progress("Loading archived quote and API inputs", 0, 1)
    events = captured_events(data_dir, start, start, cancel, compact_books=True)
    if progress: progress("Preparing fixed contracts and recorded fee scenarios", 0, 1)
    metadata = {(r["metadata_observed_on"], str(r["security_id"])): r for r in store.list_records("contract_metadata", 100000)}
    index_ids = {str(e["payload"]["security_id"]): e["payload"]["symbol"] for e in events if e["kind"] == "underlying" and "security_id" in e["payload"]}
    catalog = {e["contract"]["contract_id"]: e["contract"] for e in events if e.get("contract")}
    clock = {"now": pd.Timestamp(start+" 09:15", tz="Asia/Kolkata")}
    if candidate and pd.Timestamp(candidate["training_end"]) >= clock["now"]: raise ValueError("Challenger training overlaps the requested replay")
    replay_dir = Path(data_dir)/"autonomous_replays"/uuid.uuid4().hex
    replay_dir.mkdir(parents=True, exist_ok=True)
    isolated = ReplayStore(replay_dir/"account.db", keep_open=True)
    costs = RecordedFeeScenario(store, list(catalog.values()), lambda: clock["now"])
    adapter, feed = ReplayGateway(), ReplayMarket()
    broker = PaperBroker(isolated, settings.paper_capital, costs, settings.max_quote_age_seconds,
        clock=lambda: clock["now"], entry_cutoff=settings.entry_cutoff, policy=PlanRiskPolicy.from_settings(settings),
        option_screen_limits=(settings.max_spread_pct, settings.min_net_reward_risk))
    engine = ReplayEngine(settings, isolated, adapter, broker, feed, clock=lambda: clock["now"])
    cursor, previous, curve, daily, coverage, missing = 0, {}, [], [], [], Counter()
    # Only futures identity/receipt metadata is needed here; avoid loading the
    # repeatedly archived candle arrays into memory for every context snapshot.
    with store._conn() as connection:
        context_inputs = [{"symbol": s, "captured_at": t, "futures_contract": json.loads(c or "{}")} for s, t, c in connection.execute(
            "SELECT json_extract(payload,'$.symbol'),json_extract(payload,'$.captured_at'),json_extract(payload,'$.futures_contract') FROM records WHERE namespace='market_context_inputs' ORDER BY json_extract(payload,'$.captured_at')")]
    futures = {r["symbol"]: r.get("futures_contract", {}) for r in context_inputs if r["captured_at"][:10] <= start}
    try:
        input_digest = hashlib.sha256()
        fee_time_unknown = False
        for day in pd.date_range(start, end, freq="D"):
            opening = day.tz_localize("Asia/Kolkata")+pd.Timedelta(hours=9, minutes=15)
            if session_state(opening) in {"WEEKEND", "HOLIDAY", "CALENDAR_UNSUPPORTED"}: continue
            if str(day.date()) != start:
                events = captured_events(data_dir, str(day.date()), str(day.date()), cancel, compact_books=True)
                cursor = 0
                index_ids.update({str(e["payload"]["security_id"]): e["payload"]["symbol"] for e in events if e["kind"] == "underlying" and "security_id" in e["payload"]})
                new_catalog = {e["contract"]["contract_id"]: e["contract"] for e in events if e.get("contract")}
                if set(new_catalog)-set(catalog):
                    fee_time_unknown |= costs.unknown_receipt_time
                    catalog.update(new_catalog)
                    costs = RecordedFeeScenario(store, list(catalog.values()), lambda: clock["now"])
                    broker.cost = costs
            input_digest.update(json.dumps([(e["id"], e["at"].isoformat()) for e in events]).encode())
            observed = [e for e in events if str(e["at"].date()) == str(day.date()) and e["kind"] == "underlying"]
            by_symbol = {s: [e["at"] for e in observed if e["payload"].get("symbol") == s] for s in symbols}
            full = all(v and v[0] <= opening+pd.Timedelta(seconds=10) and v[-1] >= opening+pd.Timedelta(hours=5, minutes=50) and
                       max((b-a).total_seconds() for a, b in zip(v, v[1:])) <= 10 for v in by_symbol.values())
            coverage.append({"date": str(day.date()), "full_sessions": full, "underlying_observations": len(observed)})
            if not observed:
                missing["Market-session quote observations absent"] += 1
                continue
            if not any(e["kind"] == "runtime_policy" and e["payload"].get("source") == VERSION and opening.normalize() <= e["at"] <= opening+pd.Timedelta(seconds=10) for e in events):
                missing["Active-policy capture marker missing; historical subscription universe is unverified"] += 1
            for now in pd.date_range(opening, opening+pd.Timedelta(hours=6), freq="2s"):
                if cancel(): raise InterruptedError("Cancelled")
                clock["now"] = now
                updated_frames = set()
                while cursor < len(events) and events[cursor]["at"] <= now:
                    event = events[cursor]; cursor += 1
                    payload = event["payload"]
                    if isinstance(payload,(bytes,str)):
                        payload = json.loads(zlib.decompress(payload) if isinstance(payload, bytes) else payload)
                        event = {**event, "payload": payload}
                    # REST rotations and WebSocket reconnects have independent
                    # counters. Comparing them would erase candles on every
                    # alternating API/tick event after an ordinary reconnect.
                    if event["kind"] == "dhan_api" and event["generation"] != adapter.credential_generation:
                        adapter.frames.clear(); engine.frames.clear(); feed.chain.clear(); previous.clear()
                        engine.status["market_context"].clear(); engine.status["market_structure"].clear()
                        updated_frames.clear()
                        adapter.credential_generation = event["generation"]
                    elif event["kind"] in {"underlying", "option_depth", "feed_disconnected"} and event["generation"] != feed.generation:
                        feed.latest.clear(); feed.books.clear()
                        feed.generation = event["generation"]
                    if event["kind"] == "feed_disconnected":
                        feed.latest.clear(); feed.books.clear()
                    if event["kind"] == "underlying": feed.latest[payload["symbol"]] = {**payload, "observation_id": event["id"]}
                    elif event["kind"] == "option_depth": feed.books[payload["contract_id"]] = {**payload, "observation_id": event["id"]}
                    elif event["kind"] == "dhan_api" and payload.get("outcome") == "SUCCESS":
                        request = payload.get("request", [])
                        if payload.get("method") == "intraday_minute_data" and len(request) >= 3:
                            frame = candle_frame(payload.get("response") or {})
                            if not frame.empty:
                                adapter.frames[str(request[0])] = frame
                                if request[2] == "INDEX" and str(request[0]) in index_ids:
                                    symbol = index_ids[str(request[0])]
                                    engine.frames[symbol] = frame
                                    updated_frames.add(symbol)
                        elif payload.get("method") == "option_chain":
                            chain = normalized_chain(event, metadata, index_ids, previous)
                            if chain:
                                symbol, rows = chain
                                feed.chain[symbol] = {r["contract_id"]: r for r in rows}
                                matching = [r for r in context_inputs if r["symbol"] == symbol and pd.Timestamp(r["captured_at"]) <= now]
                                if matching: futures[symbol] = matching[-1].get("futures_contract", {})
                                contract = futures.get(symbol, {})
                                frame = adapter.frames.get(str(contract.get("security_id")), pd.DataFrame())
                                context = build_context(symbol, rows, contract, frame, now.to_pydatetime(), settings.session_exit, full_chain=True)
                                context.update(credential_generation=adapter.credential_generation)
                                engine.status["market_context"][symbol] = context
                for symbol in updated_frames:
                    engine.status["market_structure"][symbol] = analyze_structure(engine.frames[symbol], now, symbol)
                engine._freeze_policies(now)
                if candidate: engine.ml_frozen = {"models": {VERSION: candidate}}
                # With a flat account and no fresh index input, no fill is
                # possible. Skip identical idle ticks, retaining equity marks.
                if not broker.positions()["positions"] and not any(quote_is_fresh(q, now, settings.underlying_quote_age_seconds) for q in feed.latest.values()):
                    if now.second == 0: curve.append({"timestamp": now.isoformat(), "value": broker.snapshot()["equity"]})
                    continue
                engine.manage_positions()
                engine.cycle()
                engine._protect_once()
                if now.strftime("%H:%M") < settings.entry_cutoff: engine.portfolio_cycle()
                state = broker.snapshot()
                if now.second == 0:
                    curve.append({"timestamp": now.isoformat(), "value": state["equity"]})
                    if progress: progress("Replaying autonomous paper inputs: "+str(day.date()), cursor, max(len(events), 1))
                if now.strftime("%H:%M") >= settings.session_exit and not state["positions"]: break
            trades = [r for r in isolated.list_records("episodes", 100000) if r["exit_ts"][:10] == str(day.date())]
            daily.append({"date": str(day.date()), "pnl": sum(t["pnl"] for t in trades), "gross_pnl": sum(t["gross_pnl"] for t in trades), "trades": len(trades)})
        trades = sorted(isolated.list_records("episodes", 100000), key=lambda t: t["entry_ts"])
        unresolved = broker.positions()["positions"]
        if costs.unknown_receipt_time or fee_time_unknown: missing["Legacy fee receipt time unavailable; fee scenario only"] += 1
        full_sessions = bool(coverage) and all(c["full_sessions"] for c in coverage) and not missing and not unresolved
        opportunities = isolated.list_records("strategy_opportunities", 10000)
        blockers = Counter(o.get("reason", "Unknown admission blocker") for o in opportunities if o.get("status") != "SELECTED")
        decision_blockers, data_waits = decision_blocker_history(isolated)
        selected = {o["id"] for o in opportunities if o.get("status") == "SELECTED"}
        if data_waits-selected or any(o.get("status") == "WAITING_DATA" for o in opportunities):
            missing["Unresolved mandatory data gaps affected candidate admission"] += 1
            full_sessions = False
        result = {"status": "research_complete" if full_sessions else "research_partial", "quality": "research_net",
            "source": "autonomous_observed_quote_replay", "strategy_mode": "autonomous", "strategy_version": VERSION,
            "fidelity": "observed_quote_estimated_fees", "pnl_basis": "net", "trades": trades, "curve": curve, "daily": daily,
            "metrics": metrics(trades, [p["value"] for p in curve], daily, settings.monthly_profit_target), "coverage": coverage,
            "unresolved": unresolved, "issues": list(missing)+([] if full_sessions else ["Incomplete full-session input coverage"]),
            "assumptions": ["The active autonomous selector, broker, sizing and exit policy are shared with runtime",
                            "Only responses received by replay time are visible; future candles and quotes are excluded",
                            "Simulated fills use recorded bid/ask and visible quantity, not actual exchange fills",
                            "Fees use conservative same-day saved broker prequotes; recorded quotes do not prove live execution"],
            "learning_eligible": False, "deployment_ready": False, "opportunities": opportunities}
        report = report_from_run(result, {"from": start, "to": end, "capital": settings.paper_capital, "source": "observed", "strategy_mode": "autonomous", "monthly_target": settings.monthly_profit_target})
        report.update(policy_version=VERSION, sizing_policy_version=SIZING_VERSION, requested_start=start, requested_end=end, source=result["source"],
            coverage_summary={"full_sessions": full_sessions}, unresolved_positions=unresolved,
            daily_pnl={r["date"]: r["pnl"] for r in daily}, net_pnl=sum(t["pnl"] for t in trades),
            estimated_charges=sum(t["costs"] for t in trades), max_drawdown=result["metrics"]["max_drawdown"],
            replay_storage=str(replay_dir), admission_blockers=dict(blockers), decision_blockers=decision_blockers,
            data_blocked_candidates=len(data_waits), unresolved_data_blocked_candidates=len(data_waits-selected),
            input_digest=input_digest.hexdigest(),
            policy_settings_digest=hashlib.sha256(json.dumps({"sizing_policy_version":SIZING_VERSION, **{k: v for k, v in settings.model_dump().items()
                if k.startswith(("max_", "min_net_")) or k in {"paper_capital", "cash_reserve_rupees", "daily_loss_limit_rupees",
                   "hard_daily_halt_rupees", "planned_daily_loss_rupees", "emergency_execution_reserve_rupees", "session_start",
                   "entry_cutoff", "session_exit", "underlying_quote_age_seconds", "exit_cooldown_minutes",
                   "weekly_loss_pause_rupees", "drawdown_pause_rupees"}}}, sort_keys=True).encode()).hexdigest())
        (replay_dir/"report.json").write_text(json.dumps(json_safe(report), indent=2, allow_nan=False), encoding="utf-8")
        return report
    finally: isolated.close()
