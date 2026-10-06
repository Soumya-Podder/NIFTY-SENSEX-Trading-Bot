"""Autonomous paper selector with independent protection and auditable research."""
from copy import deepcopy
from pathlib import Path
import pandas as pd

from .portfolio_engine import MultiStrategyPaperEngine
from .autonomous_policy import VERSION, STRATEGY_SPECS, evaluate_market, strategy_order, plan_candidate, management_decision
from .paper_learning import PaperResearchLearning
from .strategy_portfolio import closed_session
from .market_structure import structure_evidence


class AutonomousPaperEngine(MultiStrategyPaperEngine):
    version = VERSION
    strategy_specs = STRATEGY_SPECS
    full_chain_context = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.learning = PaperResearchLearning(self.store)
        self.strategies = list(STRATEGY_SPECS)
        self.status["management"] = {}
        self.management_bars = {}
        self.analysis_cache = {}

    def evaluate_market(self, frame, now, symbol, structure):
        tail=frame.tail(6)[["timestamp","open","high","low","close"]].to_json(date_format="iso") if frame is not None and not frame.empty else None
        completed=frame[frame.timestamp+pd.Timedelta(minutes=1)<=pd.Timestamp(now)] if tail is not None else None
        fresh=completed is not None and not completed.empty and (pd.Timestamp(now)-completed.timestamp.iloc[-1]).total_seconds()<=125
        key=(id(frame), tail, pd.Timestamp(now).floor("min").isoformat(), fresh, structure.get("as_of"))
        if symbol not in self.analysis_cache or self.analysis_cache[symbol][0]!=key:
            self.analysis_cache[symbol]=(key,evaluate_market(frame, now, symbol, structure))
        return deepcopy(self.analysis_cache[symbol][1])

    def strategy_order(self, regime):
        return strategy_order(regime)

    def _freeze_policies(self, now):
        changed=self.policy_day!=str(now.date())
        super()._freeze_policies(now)
        if changed and self.market and getattr(self.market, "recorder", None):
            self.market.recorder.record("runtime_policy", {"source":self.version,"symbol":"SYSTEM"}, getattr(self.market,"credential_generation",0))

    def plan_candidate(self, signal, contract, candle):
        return plan_candidate(signal, contract, candle)

    def _current_signal(self, signal, now):
        with self.lock: frame = self.frames.get(signal["symbol"])
        current, rows = self.evaluate_market(frame, now, signal["symbol"], self.status["market_structure"].get(signal["symbol"], {}))
        match = next((s for s in current if s["id"] == signal["id"]), None)
        if match: return match,None
        if not self._signal_fresh(signal,now): return None,"Setup expired before candidate review"
        bars,problem=closed_session(frame,now)
        if problem: return None,problem
        # Reconfirm the original causal trigger, rather than requiring a new
        # candle to reproduce its ID. The existing three-bar lifetime applies.
        original,_=evaluate_market(frame,pd.Timestamp(signal["timestamp"])+pd.Timedelta(minutes=1),
                                  signal["symbol"],self.status["market_structure"].get(signal["symbol"], {}))
        confirmed=next((s for s in original if s["id"]==signal["id"]),None)
        if not confirmed: return None,"Original completed setup is no longer confirmed"
        following=bars[bars.timestamp>pd.Timestamp(signal["timestamp"])]
        call=signal["option_type"]=="CALL"
        if ((following.low<=signal["invalidation"]).any() if call else
                (following.high>=signal["invalidation"]).any()):
            return None,"Underlying has invalidated the setup on a completed bar"
        row=next((r for r in rows if r["id"]==signal["strategy_id"]),{})
        if not row.get("feature_row") or row.get("regime")!=confirmed["regime"]:
            return None,"Current completed-bar regime no longer supports the setup"
        last=bars.iloc[-1]
        if signal["strategy_id"] in {"trend_continuation","trend_pullback"}:
            if (last.close<=last.ema21 if call else last.close>=last.ema21) or abs(last.close-last.ema21)>2*last.atr:
                return None,"Current trend is contradictory or extended beyond two ATR from EMA 21"
        snapshot=self.status["market_structure"].get(signal["symbol"], {})
        evidence=structure_evidence(snapshot,signal["option_type"],now)
        relation="RESISTANCE" if call else "SUPPORT"
        zones=[z for z in snapshot.get("zones",[]) if z["relation"]==relation and z["timeframe"]!="2m"]
        evidence["target_obstacle"]=min(zones,key=lambda z:z["distance_points"],default=None)
        return {**confirmed,"feature_row":row["feature_row"],"regime":row["regime"],"market_structure":evidence},None

    def _assess_offer(self, signal, contract, account, outcomes, now, review):
        context = self.context_at(signal["symbol"], now, signal["horizon_minutes"])
        positioning = context.get("positioning", {})
        ready = positioning.get("status") == "OBSERVED" and positioning.get("scope") == "FULL_RETURNED_FIXED_CONTRACT_CHAIN"
        review["checks"]["full_chain_context"] = {"status": "PASS" if ready else "BLOCKED", "evidence": positioning,
                                                "reason": "Fresh full returned fixed-contract chain required"}
        if not ready: return None, "Whole-chain context unavailable: "+positioning.get("reason", context.get("reason", "waiting for chain collection"))
        return super()._assess_offer(signal, contract, account, outcomes, now, review)

    def manage_positions(self):
        now = self._now()
        positions = self.broker.positions()["positions"]
        self.status["management"] = {k: v for k, v in self.status["management"].items() if any(p["symbol"] == k for p in positions)}
        for position in positions:
            with self.lock: frame = self.frames.get(position["symbol"])
            completed = frame[frame.timestamp+pd.Timedelta(minutes=1) <= now] if frame is not None else None
            bar = str(completed.timestamp.max()) if completed is not None and not completed.empty else None
            if self.management_bars.get(position["id"]) == bar: continue
            decision = management_decision(position, frame, now)
            self.status["management"][position["symbol"]] = decision
            self.management_bars[position["id"]] = bar
            if decision["action"] == "EXIT":
                self.broker.request_management_exit(position["id"], decision["reason"])

    def _management_loop(self):
        # Market-context analysis never occupies the independent bid/stop worker.
        while not self.stop_event.is_set():
            try:
                self.manage_positions()
                self.status["management_error"] = None
            except Exception as exc: self.status["management_error"] = self._safe_error(exc)
            self.stop_event.wait(1)

    def start(self):
        if any(t.is_alive() for t in self.threads): return
        if self.market and getattr(self.market, "recorder", None):
            self.market.recorder.record("runtime_policy", {"source": self.version, "symbol": "SYSTEM"}, getattr(self.market, "credential_generation", 0))
        super().start()
        self._start_worker("paper-research-learning",self._learning_loop)
        self._start_worker("paper-position-manager",self._management_loop)

    def _learning_loop(self):
        while not self.stop_event.is_set():
            try:
                self.learning.train(self._now())
                pending = [c for c in self.store.list_records("paper_learning_candidates", 1000)
                           if c.get("status") == "AWAITING_FULL_ACCOUNT_REPLAY"]
                if self._session() in {"EXIT_ONLY", "HOLIDAY", "WEEKEND", "PREOPEN"} and pending:
                    candidate = max(pending, key=lambda c: c["validation_end"])
                    if candidate:
                        from .backtest.autonomous_replay import run_replay
                        kwargs = dict(store=self.store, gateway=self.gateway, settings=self.settings,
                                      data_dir=Path(self.store.path).parents[1]/"data", start=candidate["validation_start"],
                                      end=candidate["validation_end"], cancel=self.stop_event.is_set)
                        baseline = run_replay(**kwargs)
                        challenger = run_replay(**kwargs, candidate=candidate)
                        self.learning.validate_replay(candidate, baseline, challenger, self._now())
                self.status["paper_learning_error"] = None
            except Exception as exc: self.status["paper_learning_error"] = self._safe_error(exc)
            self.stop_event.wait(30)

    def autonomy_status(self):
        return {"mode": "autonomous_paper", "policy_version": self.version, "strategies": list(self.strategy_specs),
                "authority": "PAPER_ONLY", "monthly_net_objective": self.settings.monthly_profit_target,
                "selection": "Current regime, completed setups, target room, full returned OI context, fresh option depth, net economics and atomic account risk",
                "management": self.status.get("management", {}), "learning": self.learning.status(),
                "learning_error": self.status.get("paper_learning_error"),
                "limitations": ["OI does not identify institutional buyers or option writers", "Paper fills and fee estimates do not establish live profitability",
                                "No calibrated direction or target-before-stop probability is deployed", "Learning can filter paper entries after independent replay; it cannot change risk or live authority"]}
