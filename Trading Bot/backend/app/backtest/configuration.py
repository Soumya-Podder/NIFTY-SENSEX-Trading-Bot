"""One settings snapshot for dashboard, command-line and observed-session replay."""
from dataclasses import asdict, replace
import math
from .engine import BacktestConfig
from ..option_screen import VERSION as SCREEN_VERSION
from ..risk import PlanRiskPolicy


def resolve_backtest_budgets(config, settings):
    result=dict(config)
    result.setdefault("capital",settings.paper_capital)
    result.setdefault("risk_per_trade",settings.max_trade_risk_rupees)
    for key,base in (("daily_loss_limit",settings.daily_loss_limit_rupees),("correlated_risk_limit",settings.max_correlated_risk_rupees)):
        if result.get(key) is None: result[key]=result["risk_per_trade"]*(base/settings.max_trade_risk_rupees)
    for key in ("capital","risk_per_trade","daily_loss_limit","correlated_risk_limit"):
        if not math.isfinite(result[key]) or result[key]<=0: raise ValueError(f"{key} must resolve to a positive finite number")
    result.setdefault("monthly_target",settings.monthly_profit_target)
    result.setdefault("monthly_target_basis",settings.monthly_profit_target_basis)
    if result.get("option_screen") is None:
        result["option_screen"]="legacy" if result.get("source")=="dhan" else SCREEN_VERSION
    if result["option_screen"] not in {"legacy",SCREEN_VERSION}: raise ValueError("Unknown option screen")
    if result.get("source")=="dhan" and result["option_screen"]!="legacy":
        raise ValueError("Current option screen requires exact-contract observations; rolling research cannot test it")
    return result


def build_replay_config(settings, config):
    resolved=resolve_backtest_budgets(config,settings)
    base=PlanRiskPolicy.from_settings(settings)
    ratio=resolved["daily_loss_limit"]/(base.loss_allocation+base.emergency_reserve)
    plan=replace(base,trade_risk=resolved["risk_per_trade"],loss_allocation=base.loss_allocation*ratio,
        emergency_reserve=base.emergency_reserve*ratio,
        premium_limit=resolved["capital"]*(base.premium_limit/settings.paper_capital),
        cash_reserve=resolved["capital"]*(base.cash_reserve/settings.paper_capital),
        weekly_loss=base.weekly_loss*ratio,max_drawdown=base.max_drawdown*ratio)
    cfg=BacktestConfig(initial_capital=resolved["capital"],risk_per_trade=resolved["risk_per_trade"],
        daily_loss_limit=resolved["daily_loss_limit"],correlated_risk_limit=resolved["correlated_risk_limit"],
        max_positions=settings.max_open_positions,monthly_target=resolved["monthly_target"],
        monthly_target_basis=resolved["monthly_target_basis"],entry_cutoff=settings.entry_cutoff,
        exit_at=settings.session_exit,trade_from=resolved.get("from",""),adaptive_exits=bool(resolved.get("strategy_mode")),
        strategy_mode=resolved.get("strategy_mode"),option_screen=resolved["option_screen"],
        max_spread_pct=settings.max_spread_pct,min_net_reward_risk=resolved.get("min_net_reward_risk",settings.min_net_reward_risk))
    if resolved.get("strategy_version")=="orb-retest-v1" or cfg.strategy_mode:
        cfg=replace(cfg,plan_policy=plan,max_positions=1,cooldown_bars=plan.cooldown_minutes)
    resolved.update(entry_cutoff=cfg.entry_cutoff,session_exit=cfg.exit_at,replay_policy=asdict(cfg))
    return cfg,resolved
