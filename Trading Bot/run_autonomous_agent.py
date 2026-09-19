#!/usr/bin/env python3
"""
Autonomous Trading Agent - Standalone runner.
Run this to start the autonomous agent with the full trading system.
"""
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings
from app.store import Store
from app.market_data import DhanGateway, DhanMarketData
from app.broker import PaperBroker
from app.expectancy import CostModel
from app.risk import PlanRiskPolicy
from app.paper_engine import PaperEngine
from app.portfolio_engine import MultiStrategyPaperEngine
from app.autonomous_agent import AutonomousTradingAgent, get_autonomous_agent


def main():
    print("=" * 60)
    print("AUTONOMOUS TRADING AGENT - NIFTY/SENSEX")
    print("=" * 60)
    print(f"Project: {PROJECT_ROOT}")
    print(f"Mode: {settings.app_mode}")
    print(f"Paper Trading: {settings.paper_only}")
    print(f"Capital: ₹{settings.paper_capital:,.0f}")
    print(f"Max Trade Risk: ₹{settings.max_trade_risk_rupees:,.0f}")
    print(f"Daily Loss Limit: ₹{settings.daily_loss_limit_rupees:,.0f}")
    print(f"Monthly Gross Target: ₹{settings.monthly_profit_target:,.0f}")
    print(f"Strategy Mode: {settings.paper_strategy_mode}")
    print("-" * 60)
    
    # Initialize components
    store = Store(PROJECT_ROOT / "backend" / "trading_bot.db")
    gateway = DhanGateway(settings, store, credential_provider=lambda: (
        settings.dhan_client_id, settings.dhan_access_token
    ))
    plan_policy = PlanRiskPolicy.from_settings(settings)
    paper = PaperBroker(store, settings.paper_capital, CostModel(store), 
                        settings.max_quote_age_seconds, entry_cutoff=settings.entry_cutoff, 
                        policy=plan_policy)
    market_data = DhanMarketData(settings.dhan_client_id, settings.dhan_access_token,
                                 "NIFTY,SENSEX", gateway, store)
    
    engine_class = MultiStrategyPaperEngine if settings.paper_strategy_mode == "portfolio" else PaperEngine
    engine = engine_class(settings, store, gateway, paper, market_data)
    
    # Create and start autonomous agent
    agent = get_autonomous_agent(PROJECT_ROOT)
    agent.set_dependencies(paper, market_data, engine)
    
    print("\nStarting autonomous agent...")
    print("Press Ctrl+C to stop\n")
    
    try:
        agent.start()
        
        # Keep running
        import time
        while True:
            time.sleep(10)
            status = agent.get_status()
            print(f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] "
                  f"Running: {status['running']} | "
                  f"Trades: {status['state']['total_trades']} | "
                  f"PnL: ₹{status['state']['net_pnl']:,.2f} | "
                  f"Regime: {status.get('ml_frozen', {}).get('session', 'N/A')}")
                  
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        agent.stop()
        print("Agent stopped.")


if __name__ == "__main__":
    main()