"""Autonomous Trading Agent: Dynamic market evaluation, strategy synthesis, and self-learning."""

from __future__ import annotations
import asyncio
import json
import math
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import settings, current_credentials
from .session import now_ist, session_state, quote_is_fresh
from .market_data import DhanGateway
from .store import Store
from .paper_engine import PaperEngine
from .portfolio_engine import MultiStrategyPaperEngine
from .ai import LearningService, extract_features, MLTradeQualityModel
from .backtest.jobs import BacktestJobs
from .backtest.engine import BacktestConfig, BacktestEngine
from .backtest.reconstruction import dhan_research
from .risk import PlanRiskPolicy, available_risk
from .pipeline import DecisionPipeline, execution_context, plan_protection
from .expectancy import CostModel
from .strategy_portfolio import STRATEGIES, evaluate_strategies
from .telemetry.event_bus import event_bus
from .telemetry.decision_trace import event


@dataclass
class MarketSnapshot:
    """Current market state for agent evaluation."""
    timestamp: datetime
    nifty_spot: float
    sensex_spot: float
    nifty_atr: float
    sensex_atr: float
    regime: str  # TREND_UP, TREND_DOWN, RANGE, TRANSITION
    adx: float
    vwap_dist_atr: float
    ema_slope: float
    relative_volume: float
    rsi: float
    option_chain_nifty: dict
    option_chain_sensex: dict
    data_quality: str  # complete, partial, insufficient


@dataclass
class TradeDecision:
    """Agent's trading decision with full reasoning."""
    action: str  # ENTER, EXIT, HOLD, SKIP
    symbol: str
    strategy: str
    contract_id: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    quantity: int = 0
    risk_rupees: float = 0
    reward_risk: float = 0
    confidence: float = 0.0
    reasoning: str = ""
    ml_probability: Optional[float] = None
    adaptive_exit_params: dict = field(default_factory=dict)
    exit_reason: Optional[str] = None


@dataclass
class AgentState:
    """Persistent agent state across sessions."""
    session_date: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    net_pnl: float = 0.0
    gross_pnl: float = 0.0
    max_drawdown: float = 0.0
    daily_target_hit: bool = False
    daily_loss_limit_hit: bool = False
    last_model_retrain: Optional[str] = None
    current_strategy_weights: dict = field(default_factory=dict)
    regime_performance: dict = field(default_factory=dict)


class AutonomousTradingAgent:
    """
    Fully autonomous agent that:
    1. Evaluates market conditions every 2 seconds
    2. Dynamically selects/adapts strategies based on regime
    3. Makes entry/exit decisions with profit-taking logic
    4. Self-learns from backtest and paper outcomes
    5. Manages risk within hard limits
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.store = Store(project_root / "backend" / "trading_bot.db")
        self.gateway = DhanGateway(settings, self.store, credential_provider=current_credentials)
        
        self.paper_broker = None  # Set by main.py after creation
        self.market_data = None
        self.engine = None
        
        self.learning = LearningService(self.store)
        self.backtest_jobs = BacktestJobs(self.store, self.gateway, settings, project_root / "data")
        
        self.state = AgentState(session_date=str(now_ist().date()))
        self.running = False
        self.stop_event = threading.Event()
        self.agent_thread: Optional[threading.Thread] = None
        self.learning_thread: Optional[threading.Thread] = None
        
        # Strategy performance tracking
        self.strategy_stats = {s["id"]: {"trades": 0, "wins": 0, "pnl": 0.0, "max_dd": 0.0} for s in STRATEGIES}
        
        # Dynamic parameters (adapted based on learning)
        self.dynamic_params = {
            "orb_retest": {"entry_buffer_atr": 0.1, "retest_bars": 5, "horizon": 10, "target_r": 2.0},
            "trend_pullback": {"adx_min": 25, "pullback_atr": 0.25, "horizon": 10, "target_r": 2.0},
            "range_rejection": {"adx_max": 20, "range_atr_mult": 2.0, "horizon": 5, "target_r": 1.5},
        }
        
        # Regime-specific adjustments
        self.regime_multipliers = {
            "TREND_UP": {"trend_pullback": 1.2, "orb_retest": 1.0, "range_rejection": 0.5},
            "TREND_DOWN": {"trend_pullback": 1.2, "orb_retest": 1.0, "range_rejection": 0.5},
            "RANGE": {"range_rejection": 1.3, "orb_retest": 0.8, "trend_pullback": 0.5},
            "TRANSITION": {"orb_retest": 1.0, "trend_pullback": 0.8, "range_rejection": 0.8},
        }

    def set_dependencies(self, paper_broker, market_data, engine):
        """Set runtime dependencies after initialization."""
        self.paper_broker = paper_broker
        self.market_data = market_data
        self.engine = engine

    def start(self):
        """Start the autonomous agent loop."""
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        
        self.agent_thread = threading.Thread(target=self._agent_loop, name="autonomous-agent", daemon=True)
        self.agent_thread.start()
        
        self.learning_thread = threading.Thread(target=self._learning_loop, name="agent-learning", daemon=True)
        self.learning_thread.start()
        
        self._publish_event("Agent", "SYSTEM", "STARTED", "Autonomous agent started")

    def stop(self):
        """Stop the autonomous agent."""
        self.running = False
        self.stop_event.set()
        if self.agent_thread:
            self.agent_thread.join(timeout=5)
        if self.learning_thread:
            self.learning_thread.join(timeout=5)
        self._publish_event("Agent", "SYSTEM", "STOPPED", "Autonomous agent stopped")

    def _agent_loop(self):
        """Main agent loop - runs every 2 seconds during market hours."""
        while not self.stop_event.is_set():
            try:
                session = session_state(
                    start=settings.session_start,
                    cutoff=settings.entry_cutoff,
                    exit_at=settings.session_exit
                )
                
                if session in {"ENTRY_WINDOW", "MANAGE_ONLY"}:
                    self._evaluate_and_decide()
                elif session == "PREOPEN":
                    self._prepare_session()
                elif session in {"CLOSED", "POST_CLOSE"}:
                    self._end_of_session()
                    
            except Exception as exc:
                self._publish_event("Agent", "SYSTEM", "ERROR", f"Agent loop error: {exc}")
                
            self.stop_event.wait(2)  # 2-second cadence

    def _learning_loop(self):
        """Background learning loop - retrains models periodically."""
        while not self.stop_event.is_set():
            try:
                # Retrain every 30 minutes during market hours, or once after session
                session = session_state()
                if session in {"ENTRY_WINDOW", "MANAGE_ONLY"}:
                    self.stop_event.wait(1800)  # 30 min
                else:
                    self._retrain_models()
                    self.stop_event.wait(3600)  # 1 hour off-market
            except Exception as exc:
                self._publish_event("Agent", "LEARNING", "ERROR", f"Learning loop error: {exc}")
                self.stop_event.wait(300)

    def _prepare_session(self):
        """Pre-market preparation: load models, validate data, check risk limits."""
        today = str(now_ist().date())
        if self.state.session_date != today:
            self.state = AgentState(session_date=today)
            self._load_state()
            
        # Refresh credentials
        self.gateway.refresh_credentials()
        
        # Load frozen ML models for today
        self.ml_frozen = self.learning.freeze(now_ist())
        
        # Validate data connectivity
        snapshot = self.market_data.snapshot() if self.market_data else {}
        if snapshot.get("symbols"):
            self._publish_event("Agent", "SYSTEM", "READY", f"Pre-market ready: {snapshot['symbols']}")

    def _evaluate_and_decide(self):
        """Core evaluation: market regime -> strategy selection -> entry/exit decisions."""
        # Get current market snapshot
        market = self._get_market_snapshot()
        if market.data_quality == "insufficient":
            return
            
        # Update regime detection
        regime = self._detect_regime(market)
        market.regime = regime
        
        # Get current positions
        account = self.paper_broker.snapshot() if self.paper_broker else {"positions": [], "halted": True}
        positions = account.get("positions", [])
        
        # Manage existing positions first
        for position in positions:
            decision = self._evaluate_exit(position, market)
            if decision.action == "EXIT":
                self._execute_exit(position, decision)
                
        # Check if we can enter new positions
        if session_state() != "ENTRY_WINDOW":
            return
            
        if account.get("halted") or not account.get("enabled") or not account.get("valuation_complete"):
            return
            
        # Single position limit
        if positions:
            return
            
        # Evaluate entry opportunities for each strategy
        opportunities = self._evaluate_entries(market)
        
        # Select best opportunity
        if opportunities:
            best = self._select_best_opportunity(opportunities, market)
            if best and best.confidence > 0.6:
                self._execute_entry(best, market)

    def _get_market_snapshot(self) -> MarketSnapshot:
        """Build comprehensive market snapshot from live data."""
        snapshot = self.market_data.snapshot() if self.market_data else {}
        symbols = snapshot.get("symbols", {})
        
        nifty = symbols.get("NIFTY", {})
        sensex = symbols.get("SENSEX", {})
        
        # Get option chains
        nifty_chain = self.gateway.chain("NIFTY") if hasattr(self.gateway, "chain") else []
        sensex_chain = self.gateway.chain("SENSEX") if hasattr(self.gateway, "chain") else []
        
        # Get latest completed candle for features
        nifty_frame = self.engine.frames.get("NIFTY") if self.engine else None
        sensex_frame = self.engine.frames.get("SENSEX") if self.engine else None
        
        nifty_atr = nifty_frame.iloc[-1].get("atr", 0) if nifty_frame is not None and not nifty_frame.empty else 0
        sensex_atr = sensex_frame.iloc[-1].get("atr", 0) if sensex_frame is not None and not sensex_frame.empty else 0
        
        return MarketSnapshot(
            timestamp=now_ist(),
            nifty_spot=nifty.get("ltp", 0),
            sensex_spot=sensex.get("ltp", 0),
            nifty_atr=nifty_atr,
            sensex_atr=sensex_atr,
            regime="UNKNOWN",
            adx=nifty_frame.iloc[-1].get("adx", 0) if nifty_frame is not None and not nifty_frame.empty else 0,
            vwap_dist_atr=nifty_frame.iloc[-1].get("vwap_distance_atr", 0) if nifty_frame is not None and not nifty_frame.empty else 0,
            ema_slope=nifty_frame.iloc[-1].get("ema_slope_atr", 0) if nifty_frame is not None and not nifty_frame.empty else 0,
            relative_volume=nifty_frame.iloc[-1].get("relative_volume", 1) if nifty_frame is not None and not nifty_frame.empty else 1,
            rsi=nifty_frame.iloc[-1].get("rsi", 50) if nifty_frame is not None and not nifty_frame.empty else 50,
            option_chain_nifty={c["contract_id"]: c for c in nifty_chain},
            option_chain_sensex={c["contract_id"]: c for c in sensex_chain},
            data_quality="complete" if nifty.get("ltp") and sensex.get("ltp") else "partial"
        )

    def _detect_regime(self, market: MarketSnapshot) -> str:
        """Detect market regime from current snapshot."""
        adx = market.adx
        ema_slope = market.ema_slope
        
        if adx >= 25 and ema_slope >= 0.2:
            return "TREND_UP"
        elif adx >= 25 and ema_slope <= -0.2:
            return "TREND_DOWN"
        elif adx <= 20 and abs(ema_slope) <= 0.15:
            return "RANGE"
        else:
            return "TRANSITION"

    def _evaluate_entries(self, market: MarketSnapshot) -> list[TradeDecision]:
        """Evaluate all strategy entry conditions."""
        opportunities = []
        
        # Get frames from engine
        frames = {}
        if self.engine:
            with self.engine.lock:
                frames = dict(self.engine.frames)
                
        for symbol in ("NIFTY", "SENSEX"):
            frame = frames.get(symbol)
            if frame is None or frame.empty:
                continue
                
            # Evaluate each strategy
            signals, _ = evaluate_strategies(frame, now_ist(), symbol)
            
            for signal in signals:
                strategy_id = signal["strategy_id"]
                decision = self._build_entry_decision(signal, market, symbol)
                if decision:
                    # Apply regime multiplier
                    mult = self.regime_multipliers.get(market.regime, {}).get(strategy_id, 1.0)
                    decision.confidence *= mult
                    decision.reasoning += f" | Regime: {market.regime} (mult: {mult:.2f})"
                    opportunities.append(decision)
                    
        return opportunities

    def _build_entry_decision(self, signal: dict, market: MarketSnapshot, symbol: str) -> Optional[TradeDecision]:
        """Build a trade decision from a strategy signal."""
        # Get fresh quotes for option selection
        quotes = self.engine.quotes if self.engine else {}
        options = [q for q in quotes.values() if q["symbol"] == symbol and quote_is_fresh(q, now_ist(), settings.max_quote_age_seconds)]
        
        if not options:
            return None
            
        # Select best contract (non-ATM, adequate liquidity)
        underlying_ltp = market.nifty_spot if symbol == "NIFTY" else market.sensex_spot
        if self.market_data:
            underlying = self.market_data.snapshot().get("symbols", {}).get(symbol, {})
            if quote_is_fresh(underlying, now_ist(), settings.max_quote_age_seconds):
                underlying_ltp = underlying.get("ltp", underlying_ltp)
                
        # Filter non-ATM
        strikes = [q["strike"] for q in options]
        atm = min(strikes, key=lambda s: abs(s - underlying_ltp)) if strikes else 0
        non_atm = [q for q in options if abs(q["strike"] - atm) > 1e-8]
        
        if not non_atm:
            return None
            
        # Rank by OI and distance
        non_atm.sort(key=lambda q: (-q.get("oi", 0), abs(q["strike"] - underlying_ltp)))
        contract = non_atm[0]
        
        # Calculate risk/reward
        price = contract["ask"]
        lot_size = contract["lot_size"]
        strategy_id = signal["strategy_id"]
        params = self.dynamic_params.get(strategy_id, {})
        
        stop_pct = signal.get("stop_percent", 0.02)
        target_pct = signal.get("target_percent", stop_pct * params.get("target_r", 2.0))
        
        stop_price = price * (1 - stop_pct)
        target_price = price * (1 + target_pct)
        
        # Risk calculation
        spread = contract["ask"] - contract["bid"]
        risk_per_lot = (price - stop_price + spread) * lot_size
        fee = CostModel.estimate_round_trip(price, stop_price, lot_size)
        total_risk = risk_per_lot + fee
        
        # Check risk budget
        account = self.paper_broker.snapshot() if self.paper_broker else {}
        budget = available_risk(
            settings.max_trade_risk_rupees,
            settings.daily_loss_limit_rupees,
            account.get("session_pnl", 0),
            account.get("open_risk_rupees", 0),
            settings.max_correlated_risk_rupees,
            0
        )
        
        if total_risk > budget:
            return None
            
        # ML quality gate
        ml_prob = None
        if self.ml_frozen:
            features = extract_features(signal.get("feature_row", {}), signal, contract, now_ist())
            signal_with_features = {**signal, "entry_features": features}
            quality = self.learning.score(signal_with_features, self.ml_frozen)
            if not quality["allowed"]:
                return None
            ml_prob = quality.get("probability")
            
        # Build decision
        reward_risk = (target_price - price) / (price - stop_price + spread) if price > stop_price + spread else 0
        
        confidence = 0.5
        if ml_prob:
            confidence = (confidence + ml_prob) / 2
        if signal.get("setup") == "ORB_RETEST":
            confidence += 0.1
        if market.regime in ("TREND_UP", "TREND_DOWN") and strategy_id == "trend_pullback":
            confidence += 0.15
        if market.regime == "RANGE" and strategy_id == "range_rejection":
            confidence += 0.15
            
        return TradeDecision(
            action="ENTER",
            symbol=symbol,
            strategy=strategy_id,
            contract_id=contract["contract_id"],
            entry_price=price,
            stop_price=stop_price,
            target_price=target_price,
            quantity=lot_size,
            risk_rupees=total_risk,
            reward_risk=reward_risk,
            confidence=min(confidence, 0.95),
            reasoning=f"{signal['strategy_name']}: {signal['setup']} | {signal.get('evidence', [])}",
            ml_probability=ml_prob,
            adaptive_exit_params={
                "version": "adaptive_observed_v1",
                "trail_at_1r": True,
                "trail_atr_mult": 0.5,
                "tighten_after": "13:00"
            }
        )

    def _select_best_opportunity(self, opportunities: list[TradeDecision], market: MarketSnapshot) -> Optional[TradeDecision]:
        """Select best opportunity using multi-criteria ranking."""
        if not opportunities:
            return None
            
        # Rank by: ML validated > evidence strength > reward/risk > confidence
        def score(d: TradeDecision):
            ml_bonus = 1.0 if d.ml_probability and d.ml_probability > 0.55 else 0.0
            evidence_bonus = 0.5 if "PASS" in d.reasoning else 0.0
            return (ml_bonus + evidence_bonus, d.reward_risk, d.confidence)
            
        opportunities.sort(key=score, reverse=True)
        return opportunities[0]

    def _execute_entry(self, decision: TradeDecision, market: MarketSnapshot):
        """Execute entry via paper broker."""
        if not self.paper_broker:
            return
            
        contract = self.engine.quotes.get(decision.contract_id) if self.engine else None
        if not contract:
            return
            
        signal = {
            "id": str(uuid.uuid4())[:24],
            "symbol": decision.symbol,
            "strategy_id": decision.strategy,
            "strategy_name": next(s["name"] for s in STRATEGIES if s["id"] == decision.strategy),
            "strategy_version": next(s["version"] for s in STRATEGIES if s["id"] == decision.strategy),
            "portfolio_version": "multi-strategy-paper-v1",
            "regime": market.regime,
            "option_type": contract["option_type"],
            "setup": decision.strategy.upper(),
            "stop_percent": 1 - decision.stop_price / decision.entry_price,
            "target_percent": decision.target_price / decision.entry_price - 1,
            "horizon_minutes": self.dynamic_params[decision.strategy]["horizon"],
            "invalidation": decision.stop_price,
            "entry_features": {},  # Will be filled by engine
            "agent_contexts": {},
            "policy_versions": {},
            "evidence_mode": "paper_observation",
            "execution_ready": True,
        }
        
        try:
            order = self.paper_broker.place_order(
                contract=contract,
                quote=contract,
                quantity=decision.quantity,
                signal=signal,
                now=now_ist()
            )
            self._publish_event("Agent", decision.symbol, "ENTERED", 
                f"{decision.strategy} entry at {decision.entry_price:.2f}, SL: {decision.stop_price:.2f}, Target: {decision.target_price:.2f}",
                evaluation=order)
            self.state.total_trades += 1
        except Exception as exc:
            self._publish_event("Agent", decision.symbol, "ERROR", f"Entry failed: {exc}")

    def _evaluate_exit(self, position: dict, market: MarketSnapshot) -> TradeDecision:
        """Evaluate exit for an open position."""
        contract_id = position["contract_id"]
        quote = self.engine.quotes.get(contract_id) if self.engine else {}
        
        if not quote or not quote_is_fresh(quote, now_ist(), settings.max_quote_age_seconds):
            return TradeDecision(action="HOLD", symbol=position["symbol"], strategy="", exit_reason="Stale quote")
            
        bid = quote.get("bid", 0)
        current_price = quote.get("close", bid)
        entry = position["entry"]
        stop = position.get("stop", entry * 0.98)
        target = position.get("target", entry * 1.04)
        
        # Adaptive exit logic
        exit_policy = position.get("exit_policy", "orb-retest-v1")
        adaptive = position.get("option_atr")
        
        # Check hard stops first
        if bid <= stop:
            return TradeDecision(action="EXIT", symbol=position["symbol"], strategy=position["setup"],
                exit_reason="STOP", stop_price=stop)
                
        if bid >= target:
            return TradeDecision(action="EXIT", symbol=position["symbol"], strategy=position["setup"],
                exit_reason="TARGET", target_price=target)
                
        # Adaptive trailing (simplified)
        if adaptive and current_price > entry:
            r_multiple = (current_price - entry) / (entry - stop) if entry > stop else 0
            if r_multiple >= 1.0:
                trail = adaptive * 0.5
                new_stop = current_price - trail
                if new_stop > stop:
                    return TradeDecision(action="EXIT", symbol=position["symbol"], strategy=position["setup"],
                        exit_reason="TRAIL", stop_price=new_stop)
                        
        # Session exit
        session = session_state()
        if session == "EXIT_ONLY" or session == "CLOSED":
            return TradeDecision(action="EXIT", symbol=position["symbol"], strategy=position["setup"],
                exit_reason="SESSION_EXIT")
                
        # Time-based exit
        horizon = position.get("horizon_minutes", 10)
        entry_time = pd.Timestamp(position.get("entry_ts", now_ist()))
        if (now_ist() - entry_time).total_seconds() > horizon * 60:
            return TradeDecision(action="EXIT", symbol=position["symbol"], strategy=position["setup"],
                exit_reason="TIME_EXIT")
                
        return TradeDecision(action="HOLD", symbol=position["symbol"], strategy=position["setup"])

    def _execute_exit(self, position: dict, decision: TradeDecision):
        """Execute exit via paper broker."""
        if not self.paper_broker:
            return
            
        contract_id = position["contract_id"]
        quote = self.engine.quotes.get(contract_id) if self.engine else {}
        
        try:
            trade = self.paper_broker.close(position["id"], quote, decision.exit_reason, now_ist())
            if trade:
                pnl = trade.get("pnl", 0)
                self.state.net_pnl += pnl
                self.state.gross_pnl += trade.get("gross_pnl", pnl)
                if pnl > 0:
                    self.state.winning_trades += 1
                else:
                    self.state.losing_trades += 1
                    
                # Update strategy stats
                strat = position.get("setup", "").lower().replace("_", "")
                for key in self.strategy_stats:
                    if key in strat:
                        self.strategy_stats[key]["trades"] += 1
                        self.strategy_stats[key]["pnl"] += pnl
                        if pnl > 0:
                            self.strategy_stats[key]["wins"] += 1
                            
                self._publish_event("Agent", position["symbol"], "EXITED",
                    f"{decision.exit_reason} at {trade.get('exit', 0):.2f}, PnL: {pnl:.2f}",
                    evaluation=trade)
        except Exception as exc:
            self._publish_event("Agent", position["symbol"], "ERROR", f"Exit failed: {exc}")

    def _retrain_models(self):
        """Retrain ML models from latest backtest/paper results."""
        try:
            # Get latest backtest report
            pointer = self.store.get_record("backtest", "latest", {})
            report = self.store.get_record("reports", pointer.get("report_id", ""), {})
            
            if report.get("trades"):
                run_id = f"auto-{now_ist().strftime('%Y%m%d-%H%M')}"
                result = self.learning.train(report, run_id)
                if any(m.get("fitted") for m in result.get("models", [])):
                    self.state.last_model_retrain = now_ist().isoformat()
                    self._publish_event("Agent", "LEARNING", "RETRAINED", 
                        f"Models retrained: {result['status']}")
                    
                    # Update dynamic parameters from learning
                    # A fitted entry classifier does not validate a different exit target.
                    # Keep exit parameters fixed until separately replayed.
        except Exception as exc:
            self._publish_event("Agent", "LEARNING", "ERROR", f"Retrain failed: {exc}")

    def _adapt_parameters_from_learning(self, learning_result: dict):
        """Entry-filter validation cannot authorize an untested exit-policy change."""
        return {"status": "SEPARATE_EXIT_VALIDATION_REQUIRED", "applied": False}
                        
    def _end_of_session(self):
        """End of session processing."""
        if self.state.session_date != str(now_ist().date()):
            return  # Already processed
            
        # Save state
        self._save_state()
        
        # Run backtest on today's data if available
        if settings.paper_collect_evidence:
            self._run_daily_backtest()
            
        # Reset for next session
        self.state = AgentState(session_date=str(now_ist().date()))

    def _run_daily_backtest(self):
        """Run backtest on recent data to validate strategies."""
        try:
            end = (now_ist() - timedelta(days=1)).date()
            start = end - timedelta(days=30)
            
            config = {
                "source": "dhan",
                "symbols": ["NIFTY", "SENSEX"],
                "underlying": "PARALLEL",
                "from": str(start),
                "to": str(end),
                "capital": settings.paper_capital,
                "risk_per_trade": settings.max_trade_risk_rupees,
                "daily_loss_limit": settings.daily_loss_limit_rupees,
                "correlated_risk_limit": settings.max_correlated_risk_rupees,
                "strategy_version": "orb-retest-v1",
                "history_cache_only": True,
            }
            
            self.backtest_jobs.start(config)
            self._publish_event("Agent", "BACKTEST", "STARTED", f"Daily backtest {start} to {end}")
        except Exception as exc:
            self._publish_event("Agent", "BACKTEST", "ERROR", f"Backtest start failed: {exc}")

    def _load_state(self):
        """Load persistent agent state."""
        saved = self.store.get_record("agent_state", self.state.session_date)
        if saved:
            for key, value in saved.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)

    def _save_state(self):
        """Save persistent agent state."""
        state_dict = {
            "session_date": self.state.session_date,
            "total_trades": self.state.total_trades,
            "winning_trades": self.state.winning_trades,
            "losing_trades": self.state.losing_trades,
            "net_pnl": self.state.net_pnl,
            "gross_pnl": self.state.gross_pnl,
            "max_drawdown": self.state.max_drawdown,
            "daily_target_hit": self.state.daily_target_hit,
            "daily_loss_limit_hit": self.state.daily_loss_limit_hit,
            "last_model_retrain": self.state.last_model_retrain,
            "current_strategy_weights": self.state.current_strategy_weights,
            "regime_performance": self.state.regime_performance,
        }
        self.store.put_record("agent_state", self.state.session_date, state_dict)

    def _publish_event(self, agent: str, symbol: str, status: str, summary: str, **kwargs):
        """Publish event to telemetry."""
        evt = event(agent, symbol, status, summary, **kwargs)
        self.store.record_event(evt)
        event_bus.publish(evt)

    def get_status(self) -> dict:
        """Get current agent status for dashboard."""
        return {
            "running": self.running,
            "state": self.state.__dict__,
            "strategy_stats": self.strategy_stats,
            "dynamic_params": self.dynamic_params,
            "ml_frozen": self.ml_frozen if hasattr(self, "ml_frozen") else {},
            "last_cycle": now_ist().isoformat(),
        }


# Singleton instance
_agent_instance: Optional[AutonomousTradingAgent] = None


def get_autonomous_agent(project_root: Path) -> AutonomousTradingAgent:
    """Get or create the singleton autonomous agent."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AutonomousTradingAgent(project_root)
    return _agent_instance
