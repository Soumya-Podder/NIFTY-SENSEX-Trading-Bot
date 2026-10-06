"""Failure injection uses isolated paper accounts; no production or broker orders."""
from datetime import timedelta
from types import SimpleNamespace
import threading
import pytest

from app.paper_engine import PaperEngine
from app.config import Settings
from app.runtime_health import execution_health, trading_readiness
from tests.test_paper import plan_account
from tests.test_autonomous_paper import setup_engine


def test_recovered_execution_loop_clears_only_its_technical_halt(tmp_path,monkeypatch):
    engine,broker,_,clock,_,_=setup_engine(tmp_path,monkeypatch)
    attempts=[]
    def cycle():
        attempts.append(1)
        if len(attempts)<=2: raise RuntimeError('isolated temporary failure')
        engine.status['last_cycle']=clock['now'].isoformat()
    monkeypatch.setattr(engine,'cycle',cycle)
    def wait(_):
        if len(attempts)==2: assert broker.snapshot()['halted']
        if len(attempts)==4: engine.stop_event.set()
    monkeypatch.setattr(engine.stop_event,'wait',wait)
    engine._loop()
    assert not broker.snapshot()['halted'] and engine.status['error'] is None
    engine.stop_event.clear()
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==1


@pytest.mark.parametrize('reason',['Manual paper halt; exits remain active','DRAWDOWN_PAUSE','Exit pending: retry'])
def test_recovery_never_overwrites_other_halts(tmp_path,reason):
    broker,_,_=plan_account(tmp_path)
    broker.control(halted=True,reason=reason)
    broker.engine_error_halt()
    assert not broker.engine_error_halt(recover=True)
    assert broker.snapshot()['halt_reason']==reason


def test_recovery_preserves_risk_lock_and_pending_position(tmp_path):
    from tests.test_paper import enter
    broker,_,clock=plan_account(tmp_path)
    enter(broker,clock,qty=10)
    broker.engine_error_halt()
    assert not broker.engine_error_halt(recover=True)
    broker.state['positions']=[]
    broker.state['loss_ledger']['lock_reason']='DAILY_FLATTEN'
    assert not broker.engine_error_halt(recover=True)


def test_dead_worker_restarts_once_and_shutdown_never_restarts(tmp_path,monkeypatch):
    broker,store,_=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    created=[]
    class Worker:
        def __init__(self,*,name,target,daemon): self.name=name; self.alive=False; created.append(self)
        def start(self): self.alive=True
        def is_alive(self): return self.alive
    monkeypatch.setattr('app.paper_engine.threading.Thread',Worker)
    engine._start_worker('isolated-worker',lambda:None)
    engine.threads[0].alive=False
    engine._restart_dead_workers()
    engine._restart_dead_workers()
    assert len(created)==2 and len(engine.threads)==1 and engine.threads[0].is_alive()
    assert engine.status['worker_recovery']['isolated-worker']['restarts']==1
    engine.stop_event.set(); engine.threads[0].alive=False
    engine._restart_dead_workers()
    assert len(created)==2


def test_one_index_data_failure_does_not_block_healthy_index_entry(tmp_path,monkeypatch):
    engine,broker,_,clock,q,under=setup_engine(tmp_path,monkeypatch)
    engine.threads=[SimpleNamespace(name='paper-engine',is_alive=lambda:True)]
    engine.status.update(last_cycle=clock['now'].isoformat(),data_error='SENSEX temporary failure',
        data_symbols={'SENSEX':{'error':'SENSEX temporary failure','candle_status':'ERROR'}})
    runtime=execution_health(engine,broker,clock['now'])
    assert runtime['operational'] and not runtime['healthy']
    market={'connected':True,'symbols':{'NIFTY':under},'options_by_symbol':{'NIFTY':{'fresh_depth':1}}}
    engine.entry_readiness=lambda:trading_readiness(runtime,broker.snapshot(),market,{q['contract_id']:q},
        {'worker_alive':True,'error':None},engine.settings,clock['now'],candles_ready={'NIFTY':True,'SENSEX':False})
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==1


def test_unknown_data_error_and_persistence_failure_still_block(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    engine.threads=[SimpleNamespace(name='paper-engine',is_alive=lambda:True)]
    engine.status.update(last_cycle=clock['now'].isoformat(),data_error='unknown failure')
    assert not execution_health(engine,broker,clock['now'])['operational']
    engine.status['data_symbols']={'SENSEX':{'error':'unknown failure'}}
    engine.status['persistence_error']='disk failure'
    assert not execution_health(engine,broker,clock['now'])['operational']


def test_slow_chain_work_is_not_on_candle_worker(tmp_path,monkeypatch):
    from tests.test_strategy_portfolio import portfolio_account,frame_fixture
    engine,_,_,_=portfolio_account(tmp_path,monkeypatch)
    engine.gateway.refresh_credentials=lambda:False
    engine.gateway.candles=lambda *a,**k:frame_fixture()
    engine.gateway.chain=lambda *a,**k:pytest.fail('Candle worker waited for option chain')
    monkeypatch.setattr(engine.stop_event,'wait',lambda _:engine.stop_event.set())
    engine._data_loop('NIFTY')
    assert engine.status['data_symbols']['NIFTY']['candle_status']=='READY'


def test_cached_decision_expires_inside_same_minute(tmp_path,monkeypatch):
    engine,_,_,clock,_,_=setup_engine(tmp_path,monkeypatch)
    frame=engine.frames['NIFTY'].iloc[:-1].copy()
    _,before=engine.evaluate_market(frame,clock['now'],'NIFTY',{})
    assert before[0]['reason']!='Completed candle is stale'
    _,after=engine.evaluate_market(frame,clock['now']+timedelta(seconds=6),'NIFTY',{})
    assert all(row['reason']=='Completed candle is stale' for row in after)


@pytest.mark.parametrize('missing',['index','depth'])
def test_partial_feed_outage_reconnects_while_other_packets_arrive(tmp_path,monkeypatch,missing):
    from app.market_data import DhanMarketData
    _,_,clock=plan_account(tmp_path)
    monkeypatch.setattr('app.market_data.now_ist',lambda:clock['now'])
    monkeypatch.setattr('app.market_data.session_state',lambda:'ENTRY_WINDOW')
    monkeypatch.setattr('app.market_data.time.monotonic',lambda:100.)
    feed=DhanMarketData('test','test-token','NIFTY,SENSEX')
    feed.last_attempt=0.; feed.last_packet_at=clock['now'].isoformat()
    stamp=clock['now'].isoformat()
    feed.latest={symbol:{'quote_update_timestamp':stamp,'source':'dhan_market_feed'} for symbol in feed.symbol_names}
    feed.option_contracts={(2,'1'):{'symbol':'NIFTY'},(8,'2'):{'symbol':'SENSEX'}}
    feed.option_quotes={symbol:{'symbol':symbol,'quote_update_timestamp':stamp,'source':'dhan_market_feed_depth'} for symbol in feed.symbol_names}
    if missing=='index': feed.latest['SENSEX']['quote_update_timestamp']=(clock['now']-timedelta(seconds=31)).isoformat()
    else: feed.option_quotes.pop('SENSEX')
    renewed=[]
    monkeypatch.setattr(feed,'refresh_credentials',lambda *args,**kwargs:renewed.append(kwargs) or True)
    assert feed.reconnect_if_idle() and renewed==[{'force':True}]
    feed.last_attempt=99
    assert not feed.reconnect_if_idle()


def test_recorder_worker_recovers_without_removing_a_readiness_gate(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    starts=[]
    recorder=SimpleNamespace(status=lambda:{'worker_alive':False},start=lambda:starts.append(1))
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,SimpleNamespace(recorder=recorder))
    monkeypatch.setattr(engine.stop_event,'wait',lambda _:engine.stop_event.set())
    engine._feed_watch()
    assert starts==[1] and engine.status['recorder_recovery']['status']=='RESTART_REQUESTED'


def test_failed_subscription_is_retried_instead_of_marked_subscribed(tmp_path):
    from app.market_data import DhanMarketData
    from tests.test_paper import contract
    feed=DhanMarketData('test','test-token','NIFTY')
    calls=[]
    def subscribe(instruments):
        calls.append(instruments)
        if len(calls)==1: raise RuntimeError('Temporary subscription failure')
    feed.feed=SimpleNamespace(subscribe_symbols=subscribe)
    c={**contract(),'security_id':'999','exchange':'NSE'}
    with pytest.raises(RuntimeError): feed.subscribe_options([c])
    assert not feed.option_contracts
    feed.subscribe_options([c])
    assert len(calls)==2 and len(feed.option_contracts)==1


def test_candle_readiness_expires_without_relabelling_old_data_as_fresh(tmp_path,monkeypatch):
    from app.runtime_health import completed_candles_ready
    engine,_,_,clock,_,_=setup_engine(tmp_path,monkeypatch)
    assert completed_candles_ready(engine.frames,{},clock['now'])['NIFTY']
    assert not completed_candles_ready(engine.frames,{},clock['now']+timedelta(seconds=66))['NIFTY']
    assert not completed_candles_ready(engine.frames,{},clock['now']+timedelta(days=1))['NIFTY']
    assert not completed_candles_ready(engine.frames,{'NIFTY':{'candle_status':'ERROR'}},clock['now'])['NIFTY']


def test_missing_protection_candle_retry_bypasses_cached_empty_response(tmp_path,monkeypatch):
    import pandas as pd
    from tests.test_strategy_portfolio import portfolio_account,candidate,executable
    engine,_,_,clock=portfolio_account(tmp_path,monkeypatch)
    signal=candidate(clock); c,_=executable(clock); key=(signal['id'],c['contract_id'])
    calls=[]
    def candles(*args,**kwargs):
        calls.append(kwargs.get('cache_seconds',30))
        if len(calls)==1: return pd.DataFrame({'timestamp':pd.to_datetime([])})
        return pd.DataFrame([{'timestamp':pd.Timestamp(signal['retest_timestamp']),'open':95.,'high':99.,'low':90.,'close':96.}])
    engine.gateway.contract_candles=candles
    request={'signal':signal,'contract':c,'generation':0}
    engine.prepare_protection(key,request)
    assert engine.protection_results[key]['candle'] is None
    engine.prepare_protection(key,request)
    assert calls==[30,0] and engine.protection_results[key]['candle']['contract_id']==c['contract_id']


def token(now,hours):
    import json,base64
    payload={'exp':(now+timedelta(hours=hours)).timestamp()}
    return 'test.'+base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')+'.test'


def test_renewal_saves_only_token_and_runtime_reloads_rest_and_feed(tmp_path,monkeypatch):
    from app.credential_recovery import renew_project_token
    from app.config import current_credentials
    from app.market_data import DhanGateway
    broker,store,clock=plan_account(tmp_path)
    old=token(clock['now'],5); new=token(clock['now'],24)
    path=tmp_path/'.env'
    path.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN='+old+'\nPLANNED_DAILY_LOSS_RUPEES=1000\n')
    calls=[]
    def renew(url,**kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200,json=lambda:{'accessToken':new,'dhanClientId':'test'})
    monkeypatch.setattr('app.credential_recovery.requests.get',renew)
    gateway=DhanGateway(Settings(_env_file=None,dhan_client_id='test',dhan_access_token=old),store,lambda:current_credentials(path))
    feed=SimpleNamespace(refresh_credentials=lambda *values:calls.append(values))
    engine=PaperEngine(Settings(_env_file=None),store,gateway,broker,feed)
    assert renew_project_token(clock['now'],path=path)['status']=='RENEWED'
    engine._refresh_runtime_credentials(clock['now'])
    assert gateway.credentials==('test',new) and calls[-1]==('test',new)
    assert 'PLANNED_DAILY_LOSS_RUPEES=1000' in path.read_text()
    assert renew_project_token(clock['now'],path=path)['status']=='NOT_DUE'
    assert len(calls)==2


@pytest.mark.parametrize('kind',['expired','malformed','failure','replacement'])
def test_renewal_never_fabricates_or_overwrites_user_credentials(tmp_path,monkeypatch,kind):
    from app.credential_recovery import renew_project_token
    _,_,clock=plan_account(tmp_path)
    old=token(clock['now'],-1 if kind=='expired' else 5)
    if kind=='malformed': old='invalid-token'
    path=tmp_path/'.env'; original='DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN='+old+'\n'
    path.write_text(original)
    calls=[]
    def renew(*args,**kwargs):
        calls.append(1)
        if kind=='replacement': path.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=user-replacement\n')
        return SimpleNamespace(status_code=401 if kind=='failure' else 200,json=lambda:{'accessToken':token(clock['now'],24)})
    monkeypatch.setattr('app.credential_recovery.requests.get',renew)
    result=renew_project_token(clock['now'],path=path)
    assert result['status'] in {'EXPIRED','EXPIRY_UNAVAILABLE','RENEWAL_FAILED'}
    assert path.read_text()==('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=user-replacement\n' if kind=='replacement' else original)
    assert bool(calls)==(kind in {'failure','replacement'})


@pytest.mark.parametrize('session,held,renew',[('ENTRY_WINDOW',False,False),('MANAGE_ONLY',False,False),('PREOPEN',True,False),('PREOPEN',False,True)])
def test_token_renewal_never_interrupts_entries_or_held_position(tmp_path,monkeypatch,session,held,renew):
    broker,store,_=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,SimpleNamespace(credential_provider=True),broker)
    calls=[]
    monkeypatch.setattr(engine,'_session',lambda:session)
    monkeypatch.setattr(broker,'positions',lambda:{'positions':[{}] if held else []})
    monkeypatch.setattr('app.credential_recovery.renew_project_token',lambda now:calls.append(now) or {'status':'NOT_DUE'})
    monkeypatch.setattr(engine.stop_event,'wait',lambda _:engine.stop_event.set())
    engine._feed_watch()
    assert bool(calls)==renew


def test_slow_history_http_does_not_hold_up_other_candle_requests(tmp_path):
    from app.market_data import DhanGateway
    from app.store import Store
    gateway=DhanGateway(Settings(_env_file=None),Store(tmp_path/'cache.db'))
    entered=threading.Event(); release=threading.Event(); completed=threading.Event()
    failures=[]
    def slow():
        entered.set(); release.wait(5)
        return {'status':'success','data':{'source':'slow'}}
    def fast(): return {'status':'success','data':{'source':'fast'}}
    def request(method):
        try:
            assert gateway.call(method)['source']==method.__name__
            if method is fast: completed.set()
        except Exception as exc: failures.append(exc)
    first=threading.Thread(target=request,args=(slow,)); second=threading.Thread(target=request,args=(fast,))
    first.start()
    try:
        assert entered.wait(2)
        second.start()
        assert completed.wait(2),'Slow provider call held the global data lock'
    finally:
        release.set(); first.join(3)
        if second.ident is not None: second.join(3)
    assert failures==[]
