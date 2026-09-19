from app.backtest.presentation import report_view, history_row
from app.backtest.reports import report_from_run
from app.backtest.reconstruction import ResearchReplay
from app.config import Settings


def test_partial_net_report_never_gets_complete_performance_label():
    report={"status":"research_partial","quality":"research_net","metrics":{"trades":2,"total_pnl":None},"daily":[{"date":"2026-09-01","pnl":150}],"coverage":[{"missing_index_minutes":3}]}
    view=report_view(report)
    assert not view["presentation"]["performance_available"]
    assert any("3 missing index" in s for s in view["presentation"]["blockers"])
    assert history_row({"id":"partial"}, report)["report"]["metrics"] == {}
    assert view["daily"] == report["daily"]  # retained for audit, not a full-period total


def test_synthetic_gross_series_and_metrics_are_quarantined():
    view=report_view({"status":"complete","quality":"verified","source":"black_scholes","gross_equity":[{"value":50000}],"gross_metrics":{"total_pnl":20000}})
    assert not view["presentation"]["performance_available"]
    assert view["gross_equity"] == [] and view["gross_metrics"] == {}


def test_completed_net_scenario_and_legacy_assumption_are_explicit():
    report={"status":"research_complete","quality":"research_net","metrics":{"total_pnl":-280.82},"config":{"from":"2026-09-06","to":"2026-09-12"},"daily":[{"date":"2026-09-07"},{"date":"2026-09-11"}],"assumptions":["No fees: net P&L and charges are unavailable."]}
    result=report_view(report)
    assert result["presentation"]["performance_available"]
    assert result["presentation"]["observed_sessions"] == 2
    assert result["presentation"]["observed_to"] == "2026-09-11"
    assert not result["presentation"]["full_exchange_calendar_verified"]
    assert "unavailable" not in " ".join(result["assumptions"])
    assert "unavailable" in report["assumptions"][0]


def test_research_metrics_use_configured_target_and_export_gross_curve():
    replay=ResearchReplay({"capital":30000,"risk_per_trade":600,"symbols":["NIFTY"],"net_costs":True},Settings(_env_file=None,monthly_profit_target=20000),{})
    result=replay.result([])
    assert result["metrics"]["monthly_target"] == 20000
    result["gross_curve"]=[{"timestamp":"2026-09-07T15:05:00+05:30","value":30100}]
    report=report_from_run(result,{"capital":30000})
    assert report["gross_equity"][0]["value"] == 30100
