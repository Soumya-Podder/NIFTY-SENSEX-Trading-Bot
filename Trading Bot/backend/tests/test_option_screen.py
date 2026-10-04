"""Isolated mechanics checks; fixtures are not market-performance evidence."""
from datetime import timedelta
import json
import sqlite3
import pytest
from app.option_screen import VERSION, assess, midpoint_spread, net_economics
from app.pipeline import DecisionPipeline
from app.ai import scope
from app.backtest.engine import BacktestConfig, BacktestEngine
from app.quote_recorder import QuoteRecorder
from tests.test_paper import plan_account, contract, quote
from tests.test_portfolio_replay import orb_frame
from tests.test_strategy_portfolio import portfolio_account, candidate, executable


def observed(clock, **changes):
    return {**quote(contract(),clock,bid=99),"delta":.5,"oi":1000,"volume":2000,
            "greeks_observed_at":clock["now"].isoformat(),"is_atm":True,**changes}


def test_atm_admitted_and_missing_delta_never_passes(tmp_path):
    _,_,clock=plan_account(tmp_path)
    signal={"symbol":"NIFTY","option_type":"CALL","regime":"TREND_UP"}
    pipeline=DecisionPipeline()
    options=[observed(clock),observed(clock,contract_id="missing",delta=None)]
    rows=pipeline.option_candidates(signal,options,30000,clock["now"],.02,buyer_screen=True)
    assert len(rows)==1 and rows[0]["is_atm"]
    assert rows[0]["option_screen_version"]==VERSION
    assert pipeline.last_option_screens[1]["status"]=="WAITING_DATA"


@pytest.mark.parametrize("delta,side,regime,status",[
    (.45,"CALL","RANGE","PASS"),(-.60,"PUT","RANGE","PASS"),
    (.30,"CALL","TREND_UP","PASS"),(-.4,"PUT","TREND_DOWN","PASS"),
    (.4,"CALL","RANGE","REJECTED"),(.19,"CALL","TREND_UP","REJECTED"),
    (.7,"CALL","TREND_UP","REJECTED"),(-.5,"CALL","TREND_UP","REJECTED")])
def test_direction_signed_delta_and_trend_only_band(tmp_path,delta,side,regime,status):
    _,_,clock=plan_account(tmp_path)
    result=assess(observed(clock,delta=delta,option_type=side),{"option_type":side,"regime":regime},clock["now"])
    assert result["status"]==status


@pytest.mark.parametrize("seconds",[-1,121])
def test_future_or_stale_greeks_cannot_enter(tmp_path,seconds):
    _,_,clock=plan_account(tmp_path)
    c=observed(clock,greeks_observed_at=(clock["now"]-timedelta(seconds=seconds)).isoformat())
    assert assess(c,{"option_type":"CALL"},clock["now"])["status"]=="WAITING_DATA"


def test_midpoint_spread_does_not_trust_stale_precomputed_ratio(tmp_path):
    _,_,clock=plan_account(tmp_path)
    c=observed(clock,bid=98,ask=100,spread_pct=.001)
    assert midpoint_spread(c)[1] > .02  # ask denominator would have passed at exactly 2%
    assert assess(c,{"option_type":"CALL"},clock["now"])["status"]=="REJECTED"
    assert midpoint_spread({"ask":100,"bid":101})==(None,None)


def test_units_are_required_and_theta_is_not_a_daily_return_forecast(tmp_path):
    _,_,clock=plan_account(tmp_path)
    c=observed(clock,bid=100,ask=100,theta=-5,vega=2)
    before=assess(c,{"option_type":"CALL"},clock["now"])["sensitivity"]
    assert before["theta_daily_pct"] is None and before["iv_percentile"] is None
    c["greek_units"]={"theta":"premium_per_day","vega":"premium_per_iv_percentage_point"}
    after=assess(c,{"option_type":"CALL"},clock["now"])["sensitivity"]
    assert after["theta_daily_pct"]==5 and after["vega_one_point_iv_drop_per_unit"]==-2
    assert after["authority"]=="CONTEXT_ONLY"


def test_costs_and_spread_count_once_and_target_is_not_stretched():
    economics=net_economics(100,99,90,120,10,20,25)
    assert economics["risk"]==130 and economics["net_reward"]==175
    assert not economics["strict_2r_pass"] and not economics["target_extended"]
    with pytest.raises(ValueError): net_economics(100,101,90,120,10,20,25)


def test_delta_can_change_without_price_change_and_final_entry_must_reject(tmp_path,monkeypatch):
    engine,broker,_,clock=portfolio_account(tmp_path,monkeypatch)
    signal=candidate(clock); c,candle=executable(clock)
    engine.protection_results[(signal["id"],c["contract_id"])]=dict(candle=candle,generation=0)
    offer,reason=engine._prepare_offer(signal,c,broker.snapshot(),[],clock["now"])
    assert reason is None
    engine.quotes[c["contract_id"]]={**c,"delta":.19}
    assert not engine._execute_offer(offer)
    assert broker.snapshot()["open_positions"]==0


def test_atomic_broker_rejects_bypass_and_keeps_account_unchanged(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    broker.option_screen_limits=(.02,1.)
    c=observed(clock,delta=None)
    signal={"id":"direct","option_type":"CALL","stop_price":90,"target_price":120,
            "risk_rupees":130,"setup":"test","regime":"TREND_UP","agent_contexts":{}}
    before=broker.snapshot()["cash"]
    with pytest.raises(ValueError,match="Observed Delta required"):
        broker.place_order(contract=c,quote=c,quantity=c["lot_size"],signal=signal,now=clock["now"])
    assert broker.snapshot()["cash"]==before and broker.snapshot()["open_positions"]==0
    c["delta"]=.5
    broker.place_order(contract=c,quote=c,quantity=c["lot_size"],signal=signal,now=clock["now"])
    position=broker.snapshot()["positions"][0]
    assert position["option_screen_version"]==VERSION
    assert position["entry_economics"]["target_extended"] is False


def test_old_learning_scope_cannot_gate_new_screen():
    signal={"symbol":"NIFTY","strategy_version":"orb-retest-v1","exit_policy":"test"}
    assert scope(signal)!=scope({**signal,"option_screen_version":VERSION})


def test_changed_valid_delta_is_saved_in_actual_entry_features(tmp_path,monkeypatch):
    engine,broker,_,clock=portfolio_account(tmp_path,monkeypatch)
    signal=candidate(clock); c,candle=executable(clock)
    engine.protection_results[(signal["id"],c["contract_id"])]=dict(candle=candle,generation=0)
    offer,_=engine._prepare_offer(signal,c,broker.snapshot(),[],clock["now"])
    engine.quotes[c["contract_id"]]={**c,"delta":.55}
    assert engine._execute_offer(offer)
    assert broker.snapshot()["positions"][0]["entry_features"]["values"]["option_delta"]==.55


def test_expiry_day_remains_blocked(tmp_path):
    _,_,clock=plan_account(tmp_path)
    c=observed(clock,expiry=str(clock["now"].date()))
    assert assess(c,{"option_type":"CALL"},clock["now"])["status"]=="REJECTED"


def test_minute_replay_does_not_claim_current_greek_or_depth_validation():
    from app.risk import PlanRiskPolicy
    cfg=BacktestConfig(plan_policy=PlanRiskPolicy(),strategy_mode="portfolio",option_screen=VERSION)
    result=BacktestEngine(cfg).run(orb_frame())
    assert not result["trades"] and not result["learning_eligible"]
    assert result["status"]=="research_partial"
    assert result["metrics"]["total_pnl"] is None
    assert result["option_screen_validation"]["counts"]["WAITING_DATA"]>0
    assert not result["option_screen_validation"]["runtime_screen_validated"]


def test_recorded_greeks_retain_observation_times_units_and_no_secrets(tmp_path):
    recorder=QuoteRecorder(tmp_path/"observations.db",min_free_bytes=0)
    recorder.start()
    recorder.record("option_depth",{"delta":.5,"theta":-5,"greeks_observed_at":"2026-09-04T10:00:00+05:30",
        "greek_units":{"vega":"premium_per_iv_percentage_point","token":"sensitive"},"access_token":"secret"})
    recorder.stop()
    with sqlite3.connect(recorder.path) as connection:
        row=json.loads(connection.execute("select payload from observations").fetchone()[0])
    assert row["delta"]==.5 and row["greeks_observed_at"].endswith("+05:30")
    assert row["greek_units"]=={"vega":"premium_per_iv_percentage_point"}
    assert "secret" not in json.dumps(row)
