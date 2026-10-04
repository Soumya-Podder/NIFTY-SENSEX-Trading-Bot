from dataclasses import replace
import pandas as pd
import pytest
from app.backtest.configuration import build_replay_config
from app.backtest.engine import BacktestEngine, BacktestConfig
from app.backtest.metrics import metrics
from app.backtest.observed_session import verified_replay
from app.backtest.reports import report_from_run
from app.config import Settings
from app.option_screen import VERSION as SCREEN_VERSION
from app.paper_performance import monthly_progress
from app.risk import PlanRiskPolicy
from tests.test_portfolio_replay import orb_frame


def test_monthly_target_uses_net_charges_not_gross():
    days=[{"date":"2026-09-01","gross_pnl":16000,"pnl":14000,"trades":1}]
    trades=[{"pnl":14000,"gross_pnl":16000,"costs":2000}]
    net=metrics(trades,[30000,44000],days)
    assert net["monthly_target"]==15000 and net["monthly_target_basis"]=="net"
    assert net["average_monthly_pnl"]==14000 and net["target_month_rate"]==0
    assert net["monthly_pnl"]=={"2026-09":14000}
    gross=metrics(trades,[30000,44000],days,15000,"gross")
    assert gross["target_month_rate"]==1 and gross["average_monthly_pnl"]==16000


def test_paper_monthly_progress_does_not_double_count_today_or_charges():
    account={"session_date":"2026-09-23","daily_results":{"2026-08-31":9000,"2026-09-22":1000,"2026-09-23":9999,"2026-09-24":7000},
        "liquidation_complete":True,"liquidation_pnl":-100,"charges":300}
    result=monthly_progress(account,15000)
    assert result["estimated_liquidation_net"]==900 and result["remaining"]==14100
    assert result["affects_entries"] is False
    account["liquidation_complete"]=False
    result=monthly_progress(account,15000)
    assert result["estimated_liquidation_net"] is None and result["achieved"] is None


def test_replay_inherits_current_paper_limits_without_a_profit_lock():
    settings=Settings(_env_file=None)
    cfg,record=build_replay_config(settings,{"strategy_mode":"portfolio"})
    assert (cfg.initial_capital,cfg.risk_per_trade,cfg.daily_loss_limit)==(30000,650,1200)
    assert (cfg.plan_policy.loss_allocation,cfg.plan_policy.emergency_reserve)==(1000,200)
    assert cfg.plan_policy==PlanRiskPolicy.from_settings(settings)
    assert cfg.option_screen==SCREEN_VERSION and cfg.monthly_target==18000 and cfg.monthly_target_basis=="net"
    assert cfg.plan_policy.gross_target is None and cfg.max_positions==1
    assert record["replay_policy"]["min_net_reward_risk"]==settings.min_net_reward_risk


def test_explicit_research_budget_preserves_ratios_without_changing_paper():
    settings=Settings(_env_file=None)
    cfg,_=build_replay_config(settings,{"strategy_mode":"portfolio","capital":60000,"risk_per_trade":1300,"option_screen":"legacy"})
    assert cfg.daily_loss_limit==2400 and cfg.plan_policy.loss_allocation==2000
    assert cfg.plan_policy.cash_reserve==12000 and cfg.option_screen=="legacy"
    assert settings.daily_loss_limit_rupees==1200


def test_current_screen_missing_depth_never_reports_zero_as_complete_performance():
    cfg,_=build_replay_config(Settings(_env_file=None),{"strategy_mode":"portfolio"})
    result=BacktestEngine(cfg).run(orb_frame())
    assert result["option_screen_validation"]["counts"]["WAITING_DATA"]>0
    assert result["status"]=="research_partial" and result["learning_eligible"] is False
    assert result["metrics"]["total_pnl"] is None and result["metrics"]["monthly_pnl"]=={}
    assert result["option_screen_validation"]["specialist_review_validated"] is False


def test_cost_receipts_cannot_override_current_screen_learning_exclusion(tmp_path,monkeypatch):
    result={"quality":"research_net","status":"research_partial","learning_eligible":False,"issues":["Missing current execution inputs"],"trades":[]}
    monkeypatch.setattr(BacktestEngine,"run",lambda *_:result)
    saved,_=verified_replay(orb_frame(),BacktestConfig(),tmp_path,"portfolio",None)
    assert saved["learning_eligible"] is False and saved["fee_evidence"]=="No completed trades to certify"


def test_realised_payoff_and_exit_analysis_use_actual_net_outcomes():
    trades=[{"pnl":900,"gross_pnl":960,"costs":60,"reason":"TARGET","holding_minutes":4},
            {"pnl":-600,"gross_pnl":-540,"costs":60,"reason":"TIME_EXIT","holding_minutes":10}]
    stats=metrics(trades,[30000,30900,30300])
    assert stats["realized_payoff_ratio"]==1.5 and stats["breakeven_win_rate"]==.4
    report=report_from_run({"quality":"verified","trades":trades,"metrics":stats},{"capital":30000})
    exits={r["reason"]:r for r in report["exit_analysis"]["groups"]}
    assert exits["TIME_EXIT"]["pnl"]==-600 and exits["TIME_EXIT"]["average_holding_minutes"]==10


def test_weekly_replay_pause_releases_only_at_new_week():
    first=orb_frame()
    next_week=orb_frame()
    next_week["timestamp"]+=pd.Timedelta(days=3)
    # Extend fixture identity and fees over both sessions, using distinct observations.
    for frame in (first,next_week):
        for quotes in frame.option_quotes:
            for q in quotes:
                q["expiry"]="2026-09-30"
                q["charge_schedule"].update(valid_from="2026-09-01",valid_to="2026-09-30")
    cfg=BacktestConfig(plan_policy=replace(PlanRiskPolicy(),weekly_loss=.01),strategy_mode="portfolio")
    result=BacktestEngine(cfg).run(pd.concat([first,next_week],ignore_index=True))
    assert len(result["trades"])==2
    assert result["trades"][0]["pnl"]<0
    assert {str(t["entry_ts"].date()) for t in result["trades"]}=={"2026-09-04","2026-09-07"}
