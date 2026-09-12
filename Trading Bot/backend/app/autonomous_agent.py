"""Paper research coordinator. Execution belongs exclusively to the portfolio engine."""

from __future__ import annotations
import json
import threading
from datetime import timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


from .config import settings, current_credentials
from .session import now_ist, session_state
from .market_data import DhanGateway
from .store import Store
from .ai import LearningService
from .backtest.jobs import BacktestJobs
from .strategy_portfolio import STRATEGIES
from .telemetry.event_bus import event_bus
from .telemetry.decision_trace import event


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
    Research coordinator observing the sole portfolio execution authority.
    Learning may propose validated models for a future session; it cannot
    independently enter, exit or alter a position owned by the paper engine.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.store = Store(project_root / "backend" / "trading_bot.db")
        self.gateway = DhanGateway(settings, self.store, credential_provider=current_credentials)
        
        self.paper_broker = None  # Set by main.py after creation
        self.market_data = None
        self.engine = None
        self.ml_frozen = {}
        self.last_cycle = None
        self.execution_observation = {}
        self.prepared_session = None
        
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
        if hasattr(engine, "learning"):
            self.learning = engine.learning

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
                if session != "WEEKEND" and self.prepared_session != str(now_ist().date()):
                    self._prepare_session()
                
                if session in {"ENTRY_WINDOW", "MANAGE_ONLY"}:
                    self._evaluate_and_decide()
                elif session == "EXIT_ONLY":
                    self._end_of_session()
                self.last_cycle = now_ist().isoformat()
                    
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
        self.prepared_session = today
        
        # Validate data connectivity
        snapshot = self.market_data.snapshot() if self.market_data else {}
        if snapshot.get("symbols"):
            self._publish_event("Agent", "SYSTEM", "READY", f"Pre-market ready: {snapshot['symbols']}")

    def _evaluate_and_decide(self):
        """Observe decisions; only the shared engine is allowed to execute them."""
        if self.engine is None:
            self.execution_observation = {"status": "UNAVAILABLE", "reason": "Execution engine not attached"}
            return
        self.ml_frozen = dict(getattr(self.engine, "ml_frozen", {}))
        status = self.engine.status
        self.execution_observation = {
            "owner": type(self.engine).__name__, "state": status.get("state"),
            "last_cycle": status.get("last_cycle"),
            "portfolio": status.get("portfolio", {}),
            "order_authority": False,
        }
        return

    def _execute_entry(self, decision, market):
        raise RuntimeError("Only the shared paper engine may execute entries")

    def _execute_exit(self, position, decision):
        raise RuntimeError("Only the shared paper engine may execute exits")

    def _retrain_models(self):
        """Retrain ML models from latest backtest/paper results."""
        try:
            # Get latest backtest report
            pointer = self.store.get_record("backtest", "latest", {})
            report = self.store.get_record("reports", pointer.get("report_id", ""), {})
            
            if report.get("trades"):
                import hashlib
                from .learning_validation import VERSION
                fingerprint=hashlib.sha256(json.dumps({"report":report,"guard":VERSION},sort_keys=True,default=str).encode()).hexdigest()
                if self.store.get_record("agent_research_inputs",fingerprint):
                    return
                run_id = f"auto-{now_ist().strftime('%Y%m%d-%H%M')}"
                result = self.learning.train(report, run_id)
                self.store.put_record("agent_research_inputs",fingerprint,{"run_id":run_id,"status":result["status"],"observed_at":now_ist().isoformat()})
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
        day = str(now_ist().date())
        if self.store.get_record("agent_session_completed", day):
            return
        if self.paper_broker and self.paper_broker.snapshot().get("positions"):
            return  # The shared engine must continue managing pending exits.
        if self.state.session_date != str(now_ist().date()):
            return  # Already processed
            
        # Save state
        self._save_state()
        
        # Run backtest on today's data if available
        if settings.paper_collect_evidence:
            self._run_daily_backtest()
            
        # Reset for next session
        self.state = AgentState(session_date=str(now_ist().date()))
        self.store.put_record("agent_session_completed", day, {"completed_at": now_ist().isoformat()})

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
            "dynamic_params_applied_to_execution": False,
            "ml_frozen": self.ml_frozen if hasattr(self, "ml_frozen") else {},
            "last_cycle": self.last_cycle,
            "role": "research_coordinator",
            "order_authority": False,
            "execution_owner": type(self.engine).__name__ if self.engine else None,
            "execution_observation": self.execution_observation,
        }


# Singleton instance
_agent_instance: Optional[AutonomousTradingAgent] = None


def get_autonomous_agent(project_root: Path) -> AutonomousTradingAgent:
    """Get or create the singleton autonomous agent."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AutonomousTradingAgent(project_root)
    return _agent_instance
