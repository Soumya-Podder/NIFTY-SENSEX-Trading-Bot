"""Local paper lifecycle checks using isolated storage and simulated feed packets."""
from datetime import datetime, timedelta
import pytest
from app.broker import PaperBroker
from app.config import Settings, current_credentials
from app.market_data import DhanMarketData
from app.paper_engine import PaperEngine
from app.risk import size_plan_order
from app.runtime_health import trading_readiness
from app.session import IST, session_state
from app.store import Store
from tests.test_paper import plan_account, enter, quote, contract, TestFees


def test_flat_unchanged_mark_does_not_write_account_again(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    broker.mark({},clock['now'])
    writes=[]
    original=store.save_bundle
    monkeypatch.setattr(store,'save_bundle',lambda items:(writes.append(items),original(items))[1])
    broker.mark({},clock['now'])
    assert writes==[]
    broker.persistence_error='OperationalError'
    broker.mark({},clock['now'])
    assert len(writes)==1 and broker.persistence_error is None


def test_recent_record_reads_use_ordered_index(tmp_path):
    store=Store(tmp_path/'indexed.db')
    with store._conn() as connection:
        plan=connection.execute('EXPLAIN QUERY PLAN SELECT payload FROM records WHERE namespace=? ORDER BY updated_at DESC,key DESC LIMIT ?',('events',80)).fetchall()
    assert any('records_recent' in row[-1] for row in plan)
    assert not any('TEMP B-TREE' in row[-1] for row in plan)


def test_keepalive_preserves_committed_records_and_closes(tmp_path):
    from app.store import Store
    path=tmp_path/'keepalive.db'
    store=Store(path,keep_open=True)
    store.put_record('events','one',{'status':'WAITING'})
    assert store.get_record('events','one')['status']=='WAITING'
    assert store._keepalive is not None
    store.close()
    assert store._keepalive is None
    assert Store(path).get_record('events','one')['status']=='WAITING'


def test_sizing_enforces_combined_cash_risk_and_two_sided_depth(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    q=quote(contract(),clock)
    sized=size_plan_order(broker.policy,broker.snapshot(),q,90,TestFees())
    assert sized['quantity']==80  # 880 price/spread risk + 20 charges; nine lots exceed the daily 1000.
    assert size_plan_order(broker.policy,broker.snapshot(),{**q,'bid_qty':20},90,TestFees())['quantity']==20
    assert size_plan_order(broker.policy,broker.snapshot(),{**q,'bid_qty':9},90,TestFees()) is None
    small={**broker.snapshot(),'cash':7000}
    assert size_plan_order(broker.policy,small,q,90,TestFees()) is None  # cash reserve plus entry charges
    with pytest.raises(ValueError,match='risk'): enter(broker,clock,qty=100)


def test_paper_premium_budget_uses_account_capital_not_fixed_30000(tmp_path):
    from dataclasses import replace
    from app.risk import PlanRiskPolicy
    policy=replace(PlanRiskPolicy(),premium_limit=40000)
    broker=PaperBroker(Store(tmp_path/'larger.db'),50000,TestFees(),
        clock=lambda:datetime(2026,9,4,10,0,tzinfo=IST),policy=policy)
    q={**contract(),'ask':1000.,'bid':999.9,'ask_qty':1000,'bid_qty':1000}
    sized=size_plan_order(policy,broker.snapshot(),q,999.,TestFees())
    assert sized['quantity']==30
    now=datetime(2026,9,4,10,0,tzinfo=IST)
    broker.place_order(contract=q,quote={**quote(q,{'now':now},bid=999.9,ask=1000.),
        'quote_update_timestamp':now.isoformat()},quantity=30,
        signal={'id':'larger-capital','stop_price':999.,'target_price':1002.,
                'setup':'TEST_ONLY','regime':'TREND_UP','agent_contexts':{}},now=now)
    assert broker.snapshot()['open_positions']==1


def test_partial_exit_retains_fee_reserve_and_original_exit_reason(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    order=enter(broker,clock,qty=20)
    broker.close(order['id'],quote(contract(),clock,bid=95,qty=10),'STOP',clock['now'])
    p=broker.snapshot()['positions'][0]
    assert p['risk_rupees']==130  # 110 remaining price/spread risk plus full 20 fee reserve
    assert p['exit_request']['status']=='PARTIAL'
    clock['now']+=timedelta(seconds=1)
    trade=broker.close(order['id'],quote(contract(),clock,bid=105,qty=10),'TARGET',clock['now'])
    assert trade['reason']=='STOP'
    assert store.get_record('exit_requests',order['id'])['status']=='COMPLETED'
    assert broker.snapshot()['cash']==29940


def test_completed_retry_clears_only_exit_pending_halt(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    order=enter(broker,clock,qty=10)
    with pytest.raises(ValueError,match='fresh'):
        broker.close(order['id'],quote(contract(),clock,bid=95,qty=10), 'STOP',
                     clock['now']+timedelta(seconds=10))
    assert broker.snapshot()['halted']
    clock['now']+=timedelta(seconds=10)
    broker.close(order['id'],quote(contract(),clock,bid=95,qty=10),'STOP',clock['now'])
    assert store.get_record('exit_requests',order['id'])['status']=='COMPLETED'
    assert store.get_record('exit_requests',order['id'])['failure_history'][0]['type']=='ValueError'
    assert not broker.snapshot()['positions']
    assert not broker.snapshot()['halted']
    assert broker.snapshot()['halt_reason'] is None

    broker,_,clock=plan_account(tmp_path/'manual')
    order=enter(broker,clock,qty=10,identifier='manual-review-signal')
    broker.control(halted=True,reason='Manual review')
    clock['now']+=timedelta(seconds=1)
    broker.close(order['id'],quote(contract(),clock,bid=95,qty=10),'STOP',clock['now'])
    assert broker.snapshot()['halted']
    assert broker.snapshot()['halt_reason']=='Manual review'


def test_protection_worker_exits_without_waiting_for_charge_http_or_entry_cycle(tmp_path,monkeypatch):
    from app.expectancy import CostModel
    broker,store,clock=plan_account(tmp_path)
    order=enter(broker,clock,qty=20)
    broker.cost.fast_exit_estimate=CostModel().fast_exit_estimate
    def blocked_http(*args):
        raise AssertionError('Protective exit must not call the charge endpoint')
    broker.cost.quote=blocked_http
    clock['now']+=timedelta(seconds=1)
    class Feed:
        def execution_snapshot(self,symbol):
            return {'underlying':{},'options':{contract()['contract_id']:quote(contract(),clock,bid=90)}}
    monkeypatch.setattr('app.paper_engine.now_ist',lambda:clock['now'])
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,Feed())
    engine._protect_once()
    assert not broker.snapshot()['positions']
    trade=store.list_records('trades')[0]
    assert trade['reason']=='STOP'
    assert trade['costs_estimated'] and not trade['learning_eligible']
    assert trade['exit_charges']['kind']=='entry_broker_prequote_exit_estimate'
    assert store.get_record('exit_requests',order['id'])['attempts']==1


def test_exit_survives_rotation_restart_reconnect_and_partial_liquidation(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    c={**contract(),'security_id':'999','exchange':'NSE'}
    order=enter(broker,clock,c=c,qty=20)
    clock['now']=clock['now'].replace(hour=15,minute=5)
    monkeypatch.setattr('app.paper_engine.now_ist',lambda:clock['now'])
    monkeypatch.setattr('app.market_data.now_ist',lambda:clock['now'])
    class PacketClock(datetime):
        @classmethod
        def now(cls,tz=None): return clock['now'].astimezone(tz) if tz else clock['now'].replace(tzinfo=None)
    monkeypatch.setattr('app.market_data.datetime',PacketClock)
    feed=DhanMarketData('test','old-test-token','NIFTY,SENSEX')
    monkeypatch.setattr(feed,'start',lambda:None)  # no network in this integration test
    feed.subscribe_options([c])
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,feed)
    monkeypatch.setattr(engine,'_session',lambda:session_state(clock['now']))
    engine.cycle()
    request=store.get_record('exit_requests',order['id'])
    assert request['status']=='PENDING' and not store.list_records('trades')
    env=tmp_path/'.env'; env.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=replacement-test-token\n')
    feed.refresh_credentials(*current_credentials(env))
    assert not feed.executable_quotes() and feed.credential_generation==1
    restored=PaperBroker(store,30000,TestFees(),clock=lambda:clock['now'],policy=broker.policy)
    engine=PaperEngine(Settings(_env_file=None),store,None,restored,feed)
    monkeypatch.setattr(engine,'_session',lambda:session_state(clock['now']))
    engine.cycle()
    assert not store.list_records('trades')
    feed._on_connect(None)
    packet={'security_id':999,'exchange_segment':2,'type':'Full Data','LTP':'95','LTT':clock['now'].isoformat(),
        'volume':100,'OI':100,'depth':[{'bid_price':'95','ask_price':'96','bid_quantity':10,'ask_quantity':20}]}
    feed._on_message(None,packet)
    engine.cycle()
    assert restored.snapshot()['positions'][0]['qty']==10
    engine.cycle()  # replaying the same depth cannot fill twice
    assert len(store.list_records('trades'))==1
    clock['now']+=timedelta(seconds=1)
    feed._on_message(None,{**packet,'LTT':clock['now'].isoformat()})
    engine.cycle()
    assert not restored.snapshot()['positions']
    assert len(store.list_records('trades'))==2 and len(store.list_records('episodes'))==1
    completed=store.get_record('exit_requests',order['id'])
    assert completed['status']=='COMPLETED' and completed['reason']==request['reason']
    assert completed['first_requested_at']==request['first_requested_at']
    assert restored.snapshot()['cash']==29840


def test_readiness_distinguishes_closed_session_stale_feed_and_exit_capability(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    settings=Settings(_env_file=None)
    runtime={'healthy':True}; recorder={'worker_alive':True,'error':None}
    market={'connected':True,'symbols':{'NIFTY':quote(contract(),clock)},'options_by_symbol':{'NIFTY':{'fresh_depth':1}}}
    ready=lambda account,now=clock['now']:trading_readiness(runtime,account,market,{},recorder,settings,now)
    assert ready(broker.snapshot())['entry_ready']
    assert 'COMPLETED_CANDLES_UNAVAILABLE' in trading_readiness(runtime,broker.snapshot(),market,{},recorder,settings,clock['now'],candles_ready={})['symbols']['NIFTY']['blockers']
    assert not ready(broker.snapshot(),clock['now']+timedelta(seconds=10))['entry_ready']
    assert 'CALENDAR_UNSUPPORTED' in ready(broker.snapshot(),clock['now'].replace(year=2027))['entry_blockers']
    recorder['error']='disk full'
    assert 'QUOTE_RECORDER_UNAVAILABLE' in ready(broker.snapshot())['entry_blockers']
    enter(broker,clock,qty=10)
    assert ready(broker.snapshot())['exit_status']=='WAITING_FOR_DEPTH'
    p=broker.snapshot()['positions'][0]
    result=trading_readiness(runtime,broker.snapshot(),market,{p['contract_id']:quote(contract(),clock,qty=10)},recorder,settings,clock['now'])
    assert result['exit_status']=='EXECUTABLE' and not result['entry_ready']


def test_readiness_veto_replaces_stale_selector_status(tmp_path,monkeypatch):
    from tests.test_strategy_portfolio import portfolio_account
    engine,broker,_,_=portfolio_account(tmp_path,monkeypatch)
    engine.entry_readiness=lambda:{'entry_ready':False,'entry_blockers':['QUOTE_RECORDER_UNAVAILABLE']}
    engine.portfolio_cycle()
    assert engine.status['portfolio']['reason']=='QUOTE_RECORDER_UNAVAILABLE'
    assert len(engine.status['portfolio']['evaluations'])==6
    assert all(row['status']=='WAITING' for row in engine.status['portfolio']['evaluations'])
    assert broker.snapshot()['open_positions']==0
