from app.risk import RiskEngine
from app.risk import available_risk
def test_daily_halt(): assert not RiskEngine().approve(100,.1,75,-3000,0).approved
def test_position_limit(): assert not RiskEngine().approve(100,.1,75,0,2).approved

def test_fees_cash_and_correlated_risk_are_shared():
    risk=RiskEngine()
    assert not risk.approve(100,.1,50,0,0,cash=5000,estimated_cost=300).approved
    assert not risk.approve(100,.1,50,0,1,cash=20000,correlated_risk=200,correlated_limit=600).approved
    assert not risk.approve(100,.1,50,-800,1,cash=20000,open_risk=200).approved

def test_invalid_risk_inputs_fail_closed():
    for value in (float("nan"),-1):
        assert not RiskEngine().approve(100,.1,10,0,0,cash=value).approved


def test_shared_budget_uses_selected_limits_and_does_not_recycle_daily_profits():
    assert available_risk(5000,10000,0,0,5000,0)==5000
    assert available_risk(5000,10000,-8000,500,5000,0)==1500
    assert available_risk(5000,10000,50000,9000,5000,0)==1000
