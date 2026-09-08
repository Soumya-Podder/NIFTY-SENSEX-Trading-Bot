from .models import RiskDecision
import math
from dataclasses import dataclass,asdict
from datetime import timedelta
from .session import local_time


@dataclass(frozen=True)
class PlanRiskPolicy:
    """Plan v1 risk envelope. Values are frozen configuration, not learned parameters."""
    trade_risk: float=300
    loss_allocation: float=650
    emergency_reserve: float=200
    premium_limit: float=24000
    cash_reserve: float=6000
    max_entries: int=3
    max_losses: int=2
    cooldown_minutes: int=5
    gross_target: float=1200
    weekly_loss: float=1700
    max_drawdown: float=2550
    entry_cutoff: str="14:30"
    exit_at: str="15:05"

    @classmethod
    def from_settings(cls,s):
        if s.planned_daily_loss_rupees+s.emergency_execution_reserve_rupees>s.daily_loss_limit_rupees:
            raise ValueError("Planned loss allocation plus execution reserve exceeds the configured daily loss budget")
        return cls(trade_risk=s.max_trade_risk_rupees,loss_allocation=s.planned_daily_loss_rupees,
            emergency_reserve=s.emergency_execution_reserve_rupees,premium_limit=s.max_premium_commitment_rupees,
            cash_reserve=s.cash_reserve_rupees,max_entries=s.max_entry_attempts,max_losses=s.max_losing_trades,
            cooldown_minutes=s.exit_cooldown_minutes,gross_target=s.daily_profit_target,
            weekly_loss=s.weekly_loss_pause_rupees,max_drawdown=s.drawdown_pause_rupees,
            entry_cutoff=s.entry_cutoff,exit_at=s.session_exit)

    def remaining(self,ledger,open_risk=0,pending_risk=0):
        return max(0,self.loss_allocation-ledger["loss_spend"]-open_risk-pending_risk)

    def entry_veto(self,ledger,now):
        if ledger.get("lock_reason"): return ledger["lock_reason"]
        if ledger["entries"]>=self.max_entries: return "MAX_ENTRY_ATTEMPTS"
        if ledger["losses"]>=self.max_losses: return "MAX_LOSING_TRADES"
        if ledger["loss_spend"]>=self.loss_allocation: return "LOSS_ALLOCATION_EXHAUSTED"
        if ledger.get("last_exit") and local_time(now)<local_time(ledger["last_exit"])+timedelta(minutes=self.cooldown_minutes): return "EXIT_COOLDOWN"
        return None

    def describe(self): return asdict(self)

def available_risk(max_trade_risk,daily_loss_limit,session_pnl,open_risk,correlated_limit,correlated_risk):
    """One policy for paper and historical replay; data/fill adapters supply observations."""
    return max(0,min(max_trade_risk,daily_loss_limit+min(session_pnl,0)-open_risk,correlated_limit-correlated_risk))

class RiskEngine:
    def __init__(self,max_trade_risk=300,daily_loss_limit=850,hard_halt=850,max_positions=1):
        self.max_trade_risk=max_trade_risk; self.daily_loss_limit=daily_loss_limit
        self.hard_halt=hard_halt; self.max_positions=max_positions
    def approve(self,entry,stop_pct,lot,realized_pnl,open_positions, *, cash=math.inf,
                open_risk=0, estimated_cost=0, exit_slippage=0, correlated_risk=0,
                correlated_limit=math.inf, halted=False):
        if halted: return RiskDecision(approved=False,reason="halted")
        if realized_pnl<=-self.hard_halt: return RiskDecision(approved=False,reason="hard_daily_halt")
        if realized_pnl<=-self.daily_loss_limit: return RiskDecision(approved=False,reason="daily_loss_limit")
        if open_positions>=self.max_positions: return RiskDecision(approved=False,reason="max_open_positions")
        if entry<=0 or not 0<stop_pct<1 or lot<=0 or int(lot)!=lot or min(open_risk,estimated_cost,exit_slippage,correlated_risk,cash)<0: return RiskDecision(approved=False,reason="invalid_inputs")
        if math.isnan(cash) or math.isnan(correlated_limit) or not all(math.isfinite(v) for v in (entry,stop_pct,lot,realized_pnl,open_risk,estimated_cost,exit_slippage,correlated_risk)):
            return RiskDecision(approved=False,reason="invalid_inputs")
        risk_per_lot=(entry*stop_pct+exit_slippage)*lot
        remaining=available_risk(self.max_trade_risk,self.daily_loss_limit,realized_pnl,open_risk,correlated_limit,correlated_risk)-estimated_cost
        lots=max(0,int(remaining//risk_per_lot))
        if math.isfinite(cash): lots=min(lots,max(0,int((cash-estimated_cost)//(entry*lot))))
        if lots<1: return RiskDecision(approved=False,reason="risk_budget_exceeded")
        qty=lots*lot; risk=lots*risk_per_lot+estimated_cost
        return RiskDecision(approved=True,quantity=qty,risk_rupees=risk,reason="approved")
