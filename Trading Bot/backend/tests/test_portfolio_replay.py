"""Synthetic mechanics fixtures, never performance evidence or runtime inputs."""
from dataclasses import replace
import pandas as pd
import pytest
from app.backtest.strategy_signals import historical_signals
from app.backtest.engine import BacktestEngine, BacktestConfig
from app.strategy_portfolio import evaluate_strategies
from app.risk import PlanRiskPolicy
from tests.test_backtest import historical_fixture
from tests.test_strategy_portfolio import frame_fixture


def orb_frame():
    f=historical_fixture(('NIFTY','SENSEX'))
    for symbol in ('NIFTY','SENSEX'):
        ix=f.index[f.symbol==symbol]
        f.loc[ix[17],['open','high','low','close']]=[24000,24006,24000,24005]
        f.loc[ix[18],['open','high','low','close']]=[24005,24005,24002,24004]
        f.loc[ix[19],['open','high','low','close']]=[24004,24008,24004,24007]
        f.loc[ix[20:],['open','high','low','close']]=[24007,24008,24006,24007]
    for quotes in f.option_quotes:
        for q in quotes: q['charge_schedule']['brokerage']=0
    return f


def test_historical_signals_match_live_prefixes_and_ignore_future():
    f=orb_frame()
    stamp=pd.Timestamp('2026-09-04 09:34',tz='Asia/Kolkata')
    replay=historical_signals(f,'portfolio')
    for symbol in ('NIFTY','SENSEX'):
        live,_=evaluate_strategies(f[f.symbol==symbol],stamp+pd.Timedelta(minutes=1),symbol)
        assert live==replay[(stamp.isoformat(),symbol)]
        assert live
    truncated=historical_signals(f[f.timestamp<=stamp],'portfolio')
    assert truncated[(stamp.isoformat(),'NIFTY')]==replay[(stamp.isoformat(),'NIFTY')]
    broken=f.drop(f[(f.symbol=='NIFTY') & (f.timestamp.dt.strftime('%H:%M')=='09:20')].index)
    assert (stamp.isoformat(),'NIFTY') not in historical_signals(broken,'portfolio')


@pytest.mark.parametrize('mode',['orb_retest','portfolio'])
def test_shared_replay_has_one_owner_and_preserves_strategy_attribution(mode):
    cfg=BacktestConfig(plan_policy=PlanRiskPolicy(),strategy_mode=mode,exit_at='15:05')
    result=BacktestEngine(cfg).run(orb_frame())
    assert result['quality']=='verified',result['issues']
    assert len(result['trades'])==1
    trade=result['trades'][0]
    assert trade['strategy_id']=='orb_retest'
    assert trade['horizon_minutes']==10
    assert trade['entry_ts'].strftime('%H:%M')=='09:35'
    assert result['selection_mode']=='frozen_observation_economics'
    assert result['parity_limitations']
    reversed_run=BacktestEngine(cfg).run(orb_frame().iloc[::-1])
    assert reversed_run['trades'][0]['symbol']==trade['symbol']


@pytest.mark.parametrize('mode,version',[('trend_pullback','trend-pullback-v1'),('range_rejection','range-rejection-v1')])
def test_no_trade_report_preserves_requested_strategy(mode,version):
    result=BacktestEngine(BacktestConfig(plan_policy=PlanRiskPolicy(),strategy_mode=mode)).run(historical_fixture())
    assert not result['trades']
    assert result['strategy_version']==version


@pytest.mark.parametrize('mode,horizon',[('trend_pullback',10),('range_rejection',5)])
def test_each_strategy_reaches_an_attributed_entry_and_its_own_time_exit(monkeypatch,mode,horizon):
    # Controlled indicator values exercise rule/execution integration. The
    # separate prefix test above uses the actual feature calculator.
    scenario=frame_fixture()
    if mode=='trend_pullback':
        scenario.loc[:,['open','high','low','close']]=[102,103,101,102]
        scenario['adx']=30.; scenario['atr']=1.; scenario['ema21']=101.5; scenario['ema9']=102.5
        scenario.loc[48,['open','high','low','close','ema21']]=[102,103,101.75,102.7,101.7]
        scenario.loc[49,['open','high','low','close','ema21']]=[103,103.4,102.7,103.2,102]
    else:
        scenario.loc[48,['open','high','low','close']]=[100.5,101.2,100.1,100.8]
        scenario.loc[49,['open','high','low','close']]=[100.9,101.6,100.7,101.4]
    f=historical_fixture()
    for column in ('open','high','low','close','ema9','ema21','adx','atr'):
        f[column]=float(scenario.iloc[-1][column])
        f.loc[:49,column]=scenario[column].to_numpy()
    for quotes in f.option_quotes:
        quotes[0]['charge_schedule']['brokerage']=0
    monkeypatch.setattr('app.backtest.strategy_signals.add_features',lambda frame:frame)
    result=BacktestEngine(BacktestConfig(plan_policy=PlanRiskPolicy(),strategy_mode=mode,exit_at='15:05')).run(f)
    assert result['quality']=='verified',result['issues']
    assert len(result['trades'])==1
    trade=result['trades'][0]
    assert trade['strategy_id']==mode
    assert trade['horizon_minutes']==horizon
    assert trade['holding_minutes']==horizon
    assert trade['reason']=='TIME_EXIT'
