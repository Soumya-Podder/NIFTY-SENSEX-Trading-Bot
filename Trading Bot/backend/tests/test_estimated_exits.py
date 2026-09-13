import pandas as pd
import pytest
from app.backtest.estimation import estimate_gap_exit
from app.backtest.presentation import report_view
from app.backtest.reports import report_from_run
from app.ai import LearningService
from app.store import Store
from tests.test_reconstruction import run_fixture


def test_only_previous_minute_same_contract_can_price_an_estimated_exit():
    p={"contract_id":"A","entry_time":"2023-03-31T12:07:00+05:30","entry_premium":20.}
    t=pd.Timestamp("2023-03-31T12:09:00+05:30")
    q={"contract_id":"A","observed_at":"2023-03-31T12:08:00+05:30","close":21.}
    assert estimate_gap_exit(p,t,q,.05)["price"] == pytest.approx(19.95)
    assert estimate_gap_exit(p,t,{**q,"observed_at":"2023-03-31T12:10:00+05:30"}) is None
    assert estimate_gap_exit(p,t,{**q,"contract_id":"B"}) is None
    assert estimate_gap_exit(p,t,None) is None


def test_estimation_liquidates_gap_and_never_trains(tmp_path):
    replay,result,cfg=run_fixture(missing_exit=True,budget_overrides={"estimate_missing_exits":True,"estimate_haircut":.05,"net_costs":True})
    assert not replay.stopped and not result["unresolved"]
    assert result["status"] == "scenario_complete"
    assert result["estimation"]["estimated_exits"] == 1
    trade=result["trades"][0]
    assert trade["reason"] == "ESTIMATED_DATA_GAP_EXIT"
    assert trade["exit_premium"] == pytest.approx(11*.95)
    assert trade["quality"] == "estimated_scenario"
    report=report_from_run(result,cfg)
    assert report_view(report)["presentation"]["performance_available"]
    trained=LearningService(Store(tmp_path/'excluded.db')).train(report,'scenario-test')
    assert trained["eligible_trades"] == 0


def test_observed_mode_still_stops_and_no_missing_entries_are_invented():
    _,strict,_=run_fixture(missing_exit=True)
    assert strict["status"] == "research_partial"
    _,estimated,_=run_fixture(gap_entry=True,budget_overrides={"estimate_missing_exits":True})
    assert not estimated["trades"]
    assert estimated["estimation"]["estimated_exits"] == 0


def test_haircut_sensitivity_uses_same_observation():
    outcomes=[]
    for haircut in (0,.05,.10):
        _,result,_=run_fixture(missing_exit=True,budget_overrides={"estimate_missing_exits":True,"estimate_haircut":haircut,"net_costs":True})
        outcomes.append(result["metrics"]["total_pnl"])
    assert outcomes[0]>outcomes[1]>outcomes[2]
