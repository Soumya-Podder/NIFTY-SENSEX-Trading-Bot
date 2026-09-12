"""Failure injection against isolated E-drive databases; no runtime imports."""
import copy
import sqlite3
from datetime import timedelta
import pandas as pd
import pytest
from app.ai import LearningService
from app.autonomous_agent import AutonomousTradingAgent
from app.backtest.data import read_contract_csv
from app.learning_validation import replay_evidence
from tests.test_adaptive_learning import trades
from tests.test_paper import plan_account, enter, quote, contract
from app.provenance import reviewed_report
from app.runtime_health import execution_health
from app.pipeline import plan_protection


def test_raw_index_prices_cannot_become_verified_options(tmp_path):
    path=tmp_path/'index.csv'
    pd.DataFrame([dict(timestamp='2026-09-04 09:15',symbol='NIFTY',open=100,high=101,low=99,close=100)]).to_csv(path,index=False)
    with pytest.raises(ValueError,match='not historical option prices'):
        read_contract_csv(path)


def test_legacy_synthetic_verified_report_cannot_train_or_promote(tmp_path):
    _,store,_=plan_account(tmp_path)
    rows=trades()
    rows[0]['price_source']='raw_index_black_scholes'
    report={'quality':'verified','trades':rows}
    result=LearningService(store).train(report,'synthetic-rejected')
    assert result['status']=='REJECTED_SYNTHETIC_DATA'
    assert result['eligible_trades']==0
    assert not store.list_records('ml_models')
    guard=replay_evidence(report,report,'2025-01-01','2025-12-31')
    assert not guard['passed']
    assert any('Synthetic' in reason for reason in guard['reasons'])


@pytest.mark.parametrize('action',['entry','exit'])
def test_failed_persistence_restores_account_and_prevents_ghost_fill(tmp_path,monkeypatch,action):
    broker,store,clock=plan_account(tmp_path)
    if action=='exit':
        order=enter(broker,clock,qty=10)
        clock['now']+=timedelta(seconds=1)
    before=copy.deepcopy(broker.state)
    def fail(*args,**kwargs): raise sqlite3.OperationalError('disk I/O error')
    monkeypatch.setattr(store,'save_bundle',fail)
    with pytest.raises(sqlite3.OperationalError):
        if action=='entry': enter(broker,clock,qty=10)
        else: broker.close(order['id'],quote(contract(),clock,bid=90),'STOP',clock['now'])
    assert broker.state==before==store.get_record('paper','account')
    assert not broker.health()['healthy']
    assert not store.list_records('trades')
    with pytest.raises(ValueError,match='persistence recovery'):
        enter(broker,clock,qty=10,identifier='new')


def test_coordinator_has_no_independent_order_authority():
    agent=object.__new__(AutonomousTradingAgent)
    class Engine:
        ml_frozen={'scope':'model'}
        status={'state':'RUNNING','last_cycle':'actual-heartbeat','portfolio':{'selected':'orb'}}
    agent.engine=Engine()
    agent._evaluate_and_decide()
    assert agent.execution_observation['order_authority'] is False
    assert agent.execution_observation['portfolio']==Engine.status['portfolio']
    with pytest.raises(RuntimeError,match='shared paper engine'): agent._execute_entry(None,None)
    with pytest.raises(RuntimeError,match='shared paper engine'): agent._execute_exit(None,None)


def test_legacy_report_is_invalidated_without_erasing_audit_record():
    original={'quality':'verified','status':'complete','metrics':{'total_pnl':1000},
              'trades':[{'contract_id':'dynamic:NIFTY:test','quality':'verified'}]}
    checked=reviewed_report(original)
    assert checked['status']=='invalidated'
    assert checked['metrics']['total_pnl'] is None
    assert original['quality']=='verified' and original['metrics']['total_pnl']==1000


def test_health_detects_stuck_execution_worker(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    class Thread:
        name='paper-engine'
        def is_alive(self): return True
    class Engine:
        threads=[Thread()]
        status={'last_cycle':clock['now'].isoformat()}
    assert execution_health(Engine(),broker,clock['now'])['healthy']
    assert not execution_health(Engine(),broker,clock['now']+timedelta(seconds=16))['healthy']


def test_structural_stop_is_not_tightened_to_force_risk_budget():
    c=contract()
    c['lot_size']=100
    signal={'retest_timestamp':'2026-09-04T09:59:00+05:30'}
    protected=plan_protection(signal,c,{**c,'low':80},100,min_stop=8)
    assert protected['stop_price'] < 80
    assert (100-protected['stop_price'])*100 > 600
    # Risk admission must reject the oversized position, not move its stop.
