"""One completed-bar trend rule feeding the existing virtual paper broker."""
import hashlib
import logging
import math
from datetime import timedelta

import pandas as pd

from .option_screen import assess as assess_option, net_economics
from .paper_engine import PaperEngine
from .risk import size_plan_order
from .session import now_ist, quote_is_fresh
from .strategy_portfolio import closed_session
from .telemetry.decision_trace import event


VERSION = "simple-trend-paper-v2"
MIN_STOP_ATR = 1.0
MAX_SPREAD_TO_STOP = .10
MAX_GREEKS_AGE_SECONDS = 45


def trend_signal(frame, now, symbol):
    bars, problem = closed_session(frame, now)
    if problem:
        return None, problem
    if len(bars) < 21:
        return None, "Waiting for trend candles"
    last, previous = bars.iloc[-1], bars.iloc[-2]
    if not all(math.isfinite(float(last[k])) for k in ("adx", "ema9", "ema21", "atr")) or last.atr <= 0:
        return None, "Trend indicators unavailable"
    side = None
    if last.adx >= 20 and last.ema9 > last.ema21 and last.close > last.ema9 and last.close > previous.high:
        side = "CALL"
    elif last.adx >= 20 and last.ema9 < last.ema21 and last.close < last.ema9 and last.close < previous.low:
        side = "PUT"
    if side is None:
        return None, "No completed trend continuation"
    recent = bars.iloc[-4:-1]
    invalidation = float(recent.low.min() if side == "CALL" else recent.high.max())
    if (side == "CALL" and invalidation >= last.close) or (side == "PUT" and invalidation <= last.close):
        return None, "Trend invalidation is not beyond entry"
    stamp = last.timestamp.isoformat()
    identifier = hashlib.sha256(f"{VERSION}|{symbol}|{stamp}|{side}".encode()).hexdigest()[:24]
    return {"id": identifier, "symbol": symbol, "timestamp": stamp, "option_type": side,
            "setup": "COMPLETED_TREND_CONTINUATION", "regime": "TREND_UP" if side == "CALL" else "TREND_DOWN",
            "invalidation": invalidation, "signal_close": float(last.close),
            "underlying_atr": float(last.atr), "horizon_minutes": 10,
            "max_greeks_age_seconds": MAX_GREEKS_AGE_SECONDS, "strategy_id": "simple_trend",
            "strategy_name": "Completed trend continuation", "strategy_version": VERSION,
            "portfolio_version": VERSION, "evidence_mode": "paper_observation",
            "agent_contexts": {"Scanner": "completed_bars", "Setup": "trend_continuation"}}, None


def protection(signal, contract, spot):
    """Map a completed-bar index invalidation through observed Delta."""
    try:
        entry, bid, delta, tick = (float(contract[k]) for k in ("ask", "bid", "delta", "tick_size"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (entry, bid, delta, tick)) or tick <= 0:
        return None
    distance = abs(spot - signal["invalidation"])
    if not MIN_STOP_ATR * signal["underlying_atr"] <= distance <= 4 * signal["underlying_atr"]:
        return None
    premium_distance = distance * abs(delta)
    if entry - bid > MAX_SPREAD_TO_STOP * premium_distance:
        return None
    stop = math.floor((entry - premium_distance) / tick + 1e-9) * tick
    target = math.ceil((entry + 2 * (entry - stop)) / tick - 1e-9) * tick
    if not 0 < stop < entry < target:
        return None
    return {**signal, "stop_price": round(stop, 8), "target_price": round(target, 8),
            "underlying_target": spot + (2 * distance if signal["option_type"] == "CALL" else -2 * distance),
            "exit_policy": "underlying_invalidation_and_premium_risk_v1",
            "protection_evidence": {"source": "completed_index_bars_and_observed_delta",
                                    "invalidation": signal["invalidation"], "delta": delta,
                                    "underlying_at_entry": spot, "tick_size": tick,
                                    "stop_distance_atr": distance / signal["underlying_atr"],
                                    "spread_to_premium_stop": (entry - bid) / premium_distance}}


class SimplePaperEngine(PaperEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._journal_scanned_bar = {}
        self.status["portfolio"] = {"version": VERSION, "reason": "Waiting for session", "selected": None,
                                    "evaluations": [], "evidence": "UNVALIDATED_PAPER"}

    def _freeze_policies(self, now):
        # Learned filters and the research-agent review have no order authority.
        self.pipeline.policies = {}
        self.policy_day = str(now.date())

    def _journal_candidate(self, symbol, frame):
        if frame.empty:
            return
        bar = str(frame.timestamp.max())
        if self._journal_scanned_bar.get(symbol) == bar:
            return
        observed = now_ist()
        signal, _ = trend_signal(frame, observed, symbol)
        if signal and self.store.get_record("signal_observations", signal["id"]) is None:
            snapshot = self.market.execution_snapshot(symbol) if self.market else {}
            self.store.put_record("signal_observations", signal["id"], {
                "id": signal["id"], "strategy_version": VERSION, "observed_at": observed.isoformat(),
                "signal": signal, "index_quote": snapshot.get("underlying"),
                "subscribed_option_quotes": list(snapshot.get("options", {}).values()),
                "position_open": bool(self.broker.snapshot()["positions"]),
                "status": "OBSERVED_ONLY", "outcome": "NOT_SIMULATED",
                "limitations": "Subscribed quotes only; no hypothetical fill, exit or P&L"})
        self._journal_scanned_bar[symbol] = bar

    def _data_loop(self, only_symbol=None):
        while not self.stop_event.is_set():
            if self._session() in {"ENTRY_WINDOW", "MANAGE_ONLY"}:
                for symbol in ((only_symbol,) if only_symbol else ("NIFTY", "SENSEX")):
                    try:
                        day = now_ist().date()
                        frame = self.gateway.candles(symbol, day - timedelta(days=7), day + timedelta(days=1), cache_seconds=5)
                        frame = frame[frame.timestamp + pd.Timedelta(minutes=1) <= pd.Timestamp(now_ist())]
                        with self.lock:
                            self.frames[symbol] = frame
                            self.status.setdefault("data_symbols", {}).setdefault(symbol, {}).update(
                                updated_at=now_ist().isoformat(),
                                last_bar=str(frame.timestamp.max()) if not frame.empty else None, rows=len(frame))
                        chain = self.gateway.chain(symbol, exclude_expiry_day=True, include_atm=True)
                        contracts = []
                        for side in ("CALL", "PUT"):
                            contracts.extend(sorted((c for c in chain if c.get("option_type") == side and
                                c.get("ltp") and c.get("identity_verified")),
                                key=lambda c: abs(abs(c.get("delta") or 0) - .5))[:4])
                        with self.lock:
                            self.frames[symbol] = frame
                            self.contracts = [c for c in self.contracts if c["symbol"] != symbol] + contracts
                            self.status.setdefault("data_symbols", {})[symbol] = {
                                "updated_at": now_ist().isoformat(), "last_bar": str(frame.timestamp.max()) if not frame.empty else None,
                                "rows": len(frame), "subscribed_candidates": len(contracts)}
                            self.status["data_error"] = next((item["error"] for item in self.status["data_symbols"].values()
                                                               if item.get("error")), None)
                        try:
                            self._journal_candidate(symbol, frame)
                            self.status["signal_journal_error"] = None
                        except Exception as exc:
                            self.status["signal_journal_error"] = type(exc).__name__
                    except Exception as exc:
                        with self.lock:
                            self.status.setdefault("data_symbols", {})[symbol] = {"error": type(exc).__name__,
                                                                                "updated_at": now_ist().isoformat()}
                            self.status["data_error"] = type(exc).__name__
            self.stop_event.wait(10)

    def evaluate_entries(self, frames, quotes, now):
        state = self.status["portfolio"]
        state["checked_at"] = now.isoformat()
        state["selected"] = None
        state["evaluations"] = []
        state["reason"] = "Waiting for a completed trend and executable option"
        account = self.broker.snapshot()
        if account["positions"] or self.broker.policy.entry_veto(account["loss_ledger"], now):
            state["reason"] = "Position open or paper risk limit active"
            return
        offers = []
        for symbol in ("NIFTY", "SENSEX"):
            signal, reason = trend_signal(frames.get(symbol), now, symbol)
            state["evaluations"].append({"symbol": symbol, "id": "simple_trend", "name": "Completed trend continuation",
                                         "status": "CANDIDATE" if signal else "WAITING", "reason": reason or "Trend confirmed"})
            if not signal:
                self.scan_wait(symbol, reason, now)
                continue
            if signal["id"] in account["consumed_signals"]:
                state["evaluations"][-1].update(status="WAITING", reason="Signal already used")
                continue
            if not self.market:
                self.scan_wait(symbol, "Live Dhan market feed unavailable", now)
                continue
            snapshot = self.market.execution_snapshot(symbol)
            observed = now_ist()
            underlying = snapshot["underlying"]
            if not quote_is_fresh(underlying, observed, self.settings.underlying_quote_age_seconds):
                self.scan_wait(symbol, "Fresh index quote unavailable", observed)
                continue
            spot = float(underlying["ltp"])
            if (signal["option_type"] == "CALL" and spot <= signal["invalidation"]) or (
                    signal["option_type"] == "PUT" and spot >= signal["invalidation"]):
                self.scan_wait(symbol, "Trend invalidated before entry", observed)
                continue
            if abs(spot - signal["signal_close"]) > signal["underlying_atr"]:
                self.scan_wait(symbol, "Index moved over one ATR beyond the completed signal close", observed)
                continue
            books = [q for q in snapshot["options"].values() if q.get("option_type") == signal["option_type"]]
            books.sort(key=lambda q: (abs(float(q["strike"]) - spot), abs(abs(float(q.get("delta") or 0)) - .5)))
            reason = "No current, liquid near-ATM option fits the paper risk budget"
            for contract in books[:6]:
                observed = now_ist()
                screen = assess_option(contract, signal, observed, max_spread=self.settings.max_spread_pct,
                                       max_quote_age=self.settings.max_quote_age_seconds)
                if screen["status"] != "PASS":
                    reason = "; ".join(screen["reasons"])
                    continue
                planned = protection(signal, contract, spot)
                if planned is None:
                    reason = "Stop below one ATR, beyond four ATR, or spread too large for stop distance"
                    continue
                sizing = size_plan_order(self.broker.policy, account, contract, planned["stop_price"], self.broker.cost)
                if sizing is None:
                    reason = f"No whole lot fits cash, depth and ₹{self.broker.policy.trade_risk:g} risk"
                    continue
                quantity = sizing["quantity"]
                economics = net_economics(contract["ask"], contract["bid"], planned["stop_price"],
                    planned["target_price"], quantity, sizing["stop_cost"],
                    self.broker.cost.quote(contract, contract["ask"], planned["target_price"], quantity)["total"])
                if economics["net_reward_risk"] < self.settings.min_net_reward_risk:
                    reason = "Net target reward does not cover planned risk"
                    continue
                planned["risk_rupees"] = economics["risk"]
                offers.append((symbol, contract, planned, sizing, economics, screen))
            if not any(offer[0] == symbol for offer in offers):
                self.scan_wait(symbol, reason, now_ist())
                state["evaluations"][-1].update(status="WAITING", reason=reason)
                state["reason"] = reason
        offers.sort(key=lambda item: (
            item[4]["net_reward_risk"], -item[4]["spread_reserve"] / item[4]["risk"],
            -abs(item[5]["abs_delta"] - .5), item[1]["contract_id"]), reverse=True)
        for symbol, contract, planned, sizing, economics, screen in offers:
            planned["selection_evidence"] = {
                "rule": "highest observed net reward per all-in planned risk among eligible contracts",
                "eligible_contracts": len(offers), "net_reward_risk": economics["net_reward_risk"],
                "spread_reserve_fraction": economics["spread_reserve"] / economics["risk"],
                "greeks_age_seconds": screen["greeks_age_seconds"],
                "expiry": contract["expiry"], "strike": contract["strike"],
                "delta": contract["delta"]}
            # The virtual broker rechecks current depth, costs, sizing and
            # daily loss atomically. No Dhan order method is called.
            try:
                order = self.broker.place_order(contract=contract, quote=contract,
                    quantity=sizing["quantity"], signal=planned, now=now_ist())
            except Exception as exc:
                logging.getLogger("simple_paper").warning("Paper admission failed for %s: %s",
                    contract["contract_id"], type(exc).__name__)
                state["reason"] = str(exc)[:160] if isinstance(exc, ValueError) else type(exc).__name__
                continue
            state["selected"] = {"symbol": symbol, "strategy": "simple_trend", "contract_id": contract["contract_id"],
                                 "quantity": sizing["quantity"], "risk": economics["risk"], "order_id": order["id"],
                                 "net_reward_risk": economics["net_reward_risk"]}
            state["reason"] = "Virtual paper position opened"
            self.publish(event("Execution", symbol, "FILLED", "Simple trend paper BUY", evaluation=order))
            return

    def describe_strategies(self):
        return {**self.status["portfolio"], "data_health": self.status.get("data_symbols", {}),
            "selection_rule": "Completed-bar trend; one-to-four ATR invalidation, spread at most 10% of stop distance, Greeks at most 45 seconds old; rank eligible paper contracts by observed net reward/risk",
            "strategies": [{"id": "simple_trend", "name": "Completed trend continuation",
            "version": VERSION, "evidence": "UNVALIDATED_PAPER"}],
            "historical_scope": "Paper observations only; no profitability claim"}
