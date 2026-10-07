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


def test_websocket_throttle_backoff_blocks_snapshot_and_idle_retries(monkeypatch):
    from app.market_data import DhanMarketData
    clock={'value':100.}; starts=[]
    monkeypatch.setattr('app.market_data.time.monotonic',lambda:clock['value'])
    monkeypatch.setattr('app.market_data.session_state',lambda:'ENTRY_WINDOW')
    class Thread:
        def __init__(self,**kwargs): pass
        def is_alive(self): return False
        def start(self): starts.append(clock['value'])
    monkeypatch.setattr('app.market_data.threading.Thread',Thread)
    feed=DhanMarketData('test','test-token','NIFTY')
    feed.last_attempt=100.
    error=RuntimeError('secret URL must not appear')
    error.response=SimpleNamespace(status_code=429,headers={'Retry-After':'180'})
    feed._on_error(None,error)
    assert feed.connection_http_status==429 and feed.reconnect_after==280.
    assert '429' in feed.error and 'secret' not in feed.error
    feed._on_error(None,error)  # SDK and adapter can report the same failed attempt.
    assert feed.reconnect_failures==1
    assert feed.snapshot()['reconnect_in_seconds']==180.
    assert not feed.reconnect_if_idle() and not starts
    clock['value']=279.
    feed.start()
    assert not starts
    clock['value']=280.
    assert feed.reconnect_if_idle() and starts==[280.]
    assert feed.reconnect_failures==1  # Forced reconnect must preserve the backoff history.
    error.response.headers={}
    feed._on_error(None,error)
    assert feed.reconnect_failures==2 and feed.reconnect_after==400.
    feed._on_connect(None)
    assert feed.connected and feed.error is None and feed.reconnect_after==0
    assert feed.reconnect_failures==0 and feed.connection_http_status is None


def test_replacement_token_clears_old_feed_error_and_backoff(monkeypatch):
    from app.market_data import DhanMarketData
    feed=DhanMarketData('test','old-token','NIFTY')
    feed.error='Old authentication failure'; feed.connection_http_status=401
    feed.reconnect_after=999999.; feed.reconnect_failures=4
    starts=[]
    monkeypatch.setattr(feed,'start',lambda:starts.append(1))
    assert feed.refresh_credentials('test','replacement-token')
    assert starts==[1] and feed.error is None and feed.connection_http_status is None
    assert feed.reconnect_after==0 and feed.reconnect_failures==0


@pytest.mark.parametrize('stage',['handshake','established'])
def test_failed_feed_stops_sdk_retry_loop_and_closes_socket(monkeypatch,stage):
    import sys
    from app.market_data import DhanMarketData
    closed=[]
    error=RuntimeError('secret token in failed connection URL')
    error.response=SimpleNamespace(status_code=429,headers={})
    class SDKFeed:
        def __init__(self,*args,**callbacks): self.callbacks=callbacks; self._running=False
        def run(self):
            self._running=True
            if stage=='established': self.callbacks['on_connect'](self)
            self.callbacks['on_error'](self,error)
            assert not self._running
            if stage=='handshake': raise error
        def close_connection(self): closed.append(1)
    client=SimpleNamespace(dhan_http=SimpleNamespace())
    monkeypatch.setitem(sys.modules,'dhanhq',SimpleNamespace(DhanContext=lambda *args:None,
        MarketFeed=SDKFeed,dhanhq=lambda context:client))
    monkeypatch.setattr('app.market_data.time.monotonic',lambda:100.)
    feed=DhanMarketData('test','test-token','NIFTY',gateway=SimpleNamespace(master=lambda:object()))
    feed.last_attempt=100.
    monkeypatch.setattr(feed,'_resolve_instruments',lambda *args:[(0,'13',15)])
    monkeypatch.setattr(feed,'_load_initial_snapshot',lambda client:None)
    feed._run()
    assert closed==[1] and not feed.connected
    assert feed.reconnect_failures==1 and feed.reconnect_after==160.
    assert feed.connection_http_status==429 and 'secret' not in feed.error


@pytest.mark.parametrize('status',[401,403,503,None])
def test_feed_error_reports_status_safely_and_retries_without_valid_retry_header(monkeypatch,status):
    from app.market_data import DhanMarketData
    monkeypatch.setattr('app.market_data.time.monotonic',lambda:100.)
    feed=DhanMarketData('test','test-token','NIFTY'); feed.last_attempt=100.
    error=RuntimeError('secret URL')
    error.response=SimpleNamespace(status_code=status,headers={'Retry-After':'invalid'})
    feed._on_error(None,error)
    assert feed.reconnect_after==115. and 'secret' not in feed.error
    assert feed.connection_http_status==status
    if status in {401,403}: assert 'access rejected' in feed.error
    else: assert 'credentials' not in feed.error


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


def test_rejected_token_is_actionable_without_exposing_response_secrets(tmp_path,monkeypatch):
    from app.credential_recovery import renew_project_token
    from app.runtime_health import execution_health
    broker,store,clock=plan_account(tmp_path)
    path=tmp_path/'.env'; original='DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN='+token(clock['now'],5)+'\n'
    path.write_text(original)
    monkeypatch.setattr('app.credential_recovery.requests.get',lambda *a,**k:SimpleNamespace(
        status_code=400,json=lambda:{'errorCode':'DH-906','errorMessage':'Invalid Token: response-secret'}))
    result=renew_project_token(clock['now'],path=path)
    assert result['requires_user_action'] and result['error_code']=='DH-906'
    assert 'project .env' in result['reason'] and 'response-secret' not in str(result)
    assert path.read_text()==original
    engine=SimpleNamespace(status={'last_cycle':clock['now'].isoformat(),'credential_renewal':result},
        threads=[SimpleNamespace(name='paper-engine',is_alive=lambda:True)])
    health=execution_health(engine,broker,clock['now'])
    assert health['operational'] and health['advisory_errors']['credential_renewal']==result


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


def test_automatic_recovery_isolates_failed_repairs_and_verifies_other_components(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    calls=[]
    def failed_recorder(): raise RuntimeError('URL containing secret-token')
    recorder=SimpleNamespace(status=lambda:{'worker_alive':False,'error':None},start=failed_recorder)
    market=SimpleNamespace(recorder=recorder,connected=False,error=None)
    def reconnect():
        calls.append('feed'); market.connected=True
        return True
    market.reconnect_if_idle=reconnect
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,market,clock=lambda:clock['now'])
    engine._recover_once()
    assert calls==['feed']
    components=engine.status['recovery']['components']
    assert components['quote_recorder']['state']=='RETRYING'
    assert components['market_feed']['state']=='RECOVERED'
    assert 'secret-token' not in str(engine.status['recovery'])
    assert engine.status['recovery']['state']=='DEGRADED'


def test_recovery_backoff_journal_and_restart_keep_actual_failures_visible(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    timer={'value':100.}; starts=[]; alive={'value':False}
    monkeypatch.setattr('app.paper_engine.time.monotonic',lambda:timer['value'])
    recorder=SimpleNamespace(status=lambda:{'worker_alive':alive['value'],'error':None},start=lambda:starts.append(1))
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,SimpleNamespace(recorder=recorder),clock=lambda:clock['now'])
    engine._recover_once(); engine._recover_once()
    assert starts==[1]
    assert engine.status['recovery']['components']['quote_recorder']['state']=='RETRYING'
    alive['value']=True; engine._recover_once()
    assert engine.status['recovery']['components']['quote_recorder']['state']=='RECOVERED'
    saved=store.get_record('paper_recovery','status')
    assert saved['history'][-1]['component']=='quote_recorder'
    restarted=PaperEngine(Settings(_env_file=None),store,None,broker,clock=lambda:clock['now'])
    assert restarted.status['recovery']['history']==saved['history']
    assert restarted.status['recovery']['state']=='STARTING'  # Old recovery is history, not current proof.


def test_persistence_repair_rewrites_only_the_durable_account(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    order=__import__('tests.test_paper',fromlist=['enter']).enter(broker,clock,qty=10)
    committed=broker.snapshot()
    original=store.save_bundle
    monkeypatch.setattr(store,'save_bundle',lambda items:(_ for _ in ()).throw(OSError('temporary disk failure')))
    with pytest.raises(OSError): broker.control(enabled=False)
    assert broker.persistence_error and broker.snapshot()['enabled']==committed['enabled']
    with pytest.raises(OSError): broker.recover_persistence()
    monkeypatch.setattr(store,'save_bundle',original)
    assert broker.recover_persistence()
    restored=__import__('app.broker',fromlist=['PaperBroker']).PaperBroker(store,30000,broker.cost,clock=lambda:clock['now'],policy=broker.policy)
    assert restored.snapshot()['positions'][0]['id']==order['id']
    assert restored.snapshot()['loss_ledger']==committed['loss_ledger']
    assert restored.snapshot()['cash']==committed['cash']
    assert not store.list_records('trades')


def test_exit_closed_by_other_worker_clears_stale_technical_errors(tmp_path,monkeypatch):
    from tests.test_paper import enter,contract,quote
    broker,store,clock=plan_account(tmp_path)
    order=enter(broker,clock,qty=10)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,clock=lambda:clock['now'])
    engine.status.update(protection_error='Previous exit failure',exit_error='Previous exit failure')
    clock['now']+=timedelta(seconds=1)
    broker.close(order['id'],quote(contract(),clock,bid=95),'STOP',clock['now'])
    engine.cycle()
    assert not engine.status.get('protection_error') and not engine.status.get('exit_error')
    assert broker.snapshot()['open_positions']==0 and not broker.snapshot()['halted']


@pytest.mark.parametrize('namespace',['paper','paper_recovery'])
def test_account_and_recovery_writes_do_not_wait_behind_a_slow_writer(tmp_path,namespace):
    import sqlite3
    from app.store import Store
    store=Store(tmp_path/'bounded-writes.db')
    locked=threading.Event(); release=threading.Event(); done=threading.Event(); errors=[]
    def hold_lock():
        with store._write_lock:
            locked.set(); release.wait(3)
    def write():
        try:
            store.save_bundle([(namespace,'account' if namespace=='paper' else 'status',{})],
                **({'timeout':.25} if namespace=='paper_recovery' else {}))
        except Exception as exc: errors.append(exc)
        finally: done.set()
    holder=threading.Thread(target=hold_lock); writer=threading.Thread(target=write)
    holder.start()
    try:
        assert locked.wait(1)
        writer.start()
        assert done.wait(1),'Account/recovery write waited behind an unrelated slow write'
        assert len(errors)==1 and isinstance(errors[0],sqlite3.OperationalError)
    finally:
        release.set(); holder.join(3)
        if writer.ident is not None: writer.join(3)


def test_unchanged_failed_repair_does_not_flood_durable_history(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    monkeypatch.setattr('app.paper_engine.time.monotonic',lambda:100.)
    def failed(): raise OSError('secret-token')
    recorder=SimpleNamespace(status=lambda:{'worker_alive':False},start=failed)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,SimpleNamespace(recorder=recorder),clock=lambda:clock['now'])
    engine._recover_once()
    history=engine.status['recovery']['history'].copy()
    writes=[]
    monkeypatch.setattr(store,'save_bundle',lambda *args,**kwargs:writes.append(1))
    engine._recover_once()
    assert engine.status['recovery']['history']==history and not writes


@pytest.mark.parametrize('change,stalled',[
    ({},True),
    ({'runtime':{'heartbeat_age_seconds':5}},False),
    ({'runtime':{'heartbeat_age_seconds':None}},False),
    ({'broker':{'healthy':False,'mode':'paper'}},False),
    ({'broker':{'healthy':True,'mode':'live'}},False),
    ({'readiness':{'exit_status':'WAITING_FOR_DEPTH','positions':[{'pending':True}]}},False),
    ({'readiness':{'exit_status':'NO_POSITION'}},False),
    ({'app':'unavailable'},False),
    ({'app':'degraded'},True),
])
def test_supervisor_restarts_stalled_execution_only_with_verified_flat_paper_account(change,stalled):
    from paper_service import execution_stalled
    health={'app':'healthy','runtime':{'heartbeat_age_seconds':65},
        'broker':{'healthy':True,'mode':'paper'},'readiness':{'exit_status':'NO_POSITION','positions':[]}}
    assert execution_stalled({**health,**change}) is stalled


def test_missing_market_data_does_not_trigger_process_restart():
    from paper_service import execution_stalled
    health={'app':'healthy','runtime':{'heartbeat_age_seconds':2,'healthy':False},
        'broker':{'healthy':True,'mode':'paper'},'market_data':{'connected':False},
        'readiness':{'exit_status':'NO_POSITION','positions':[],
            'entry_blockers':['FEED_DISCONNECTED','NO_INDEX_HAS_ENTRY_DATA']}}
    assert not execution_stalled(health)


def test_alive_worker_does_not_prove_a_stale_execution_loop_recovered(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,clock=lambda:clock['now'])
    engine.threads=[SimpleNamespace(name='paper-engine',is_alive=lambda:True)]
    engine.status['last_cycle']=(clock['now']-timedelta(seconds=65)).isoformat()
    engine._recover_once()
    assert engine.status['recovery']['components']['execution_loop']['state']=='RETRYING'
    assert engine.status['recovery']['state']=='DEGRADED'
    engine.status['last_cycle']=clock['now'].isoformat()
    engine._recover_once()
    assert engine.status['recovery']['components']['execution_loop']['state']=='RECOVERED'


@pytest.mark.parametrize('protection_age,dead,stalled',[(2,[],False),(65,[],True),
    (None,['paper-protection'],True),(None,[],False)])
def test_occupied_account_restart_uses_protection_liveness_not_missing_depth(protection_age,dead,stalled):
    from paper_service import execution_stalled
    health={'app':'degraded','runtime':{'heartbeat_age_seconds':65,
        'protection_heartbeat_age_seconds':protection_age,'dead_workers':dead},
        'broker':{'healthy':True,'mode':'paper'},
        'readiness':{'exit_status':'WAITING_FOR_DEPTH','positions':[{'pending':True}]}}
    assert execution_stalled(health) is stalled


def test_stalled_protection_blocks_entry_even_when_main_worker_is_current(tmp_path):
    from paper_service import execution_stalled
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker,clock=lambda:clock['now'])
    engine.threads=[SimpleNamespace(name=name,is_alive=lambda:True) for name in ('paper-engine','paper-protection')]
    engine.status.update(last_cycle=clock['now'].isoformat(),
        last_protection_cycle=(clock['now']-timedelta(seconds=65)).isoformat())
    runtime=execution_health(engine,broker,clock['now'])
    assert not runtime['operational'] and runtime['protection_heartbeat_age_seconds']==65
    assert execution_stalled({'app':'degraded','runtime':runtime,'broker':broker.health(),
        'readiness':{'positions':[{'pending':True}],'exit_status':'WAITING_FOR_DEPTH'}})


def test_watchdog_grace_and_owned_api_timeout_do_not_confuse_data_failure():
    from paper_service import restart_reason
    assert restart_reason({},61,89) is None
    assert restart_reason({},59,100) is None
    assert restart_reason({},61,100)=='OWNED_API_UNRESPONSIVE'
    assert restart_reason({'app':'degraded','runtime':{'heartbeat_age_seconds':2},
        'broker':{'healthy':True,'mode':'paper'},'readiness':{'positions':[],'exit_status':'NO_POSITION'}},61,100) is None


@pytest.mark.parametrize('hour,minute,held,reconnect',[(15,6,True,True),(15,6,False,False),(15,31,True,False)])
def test_pending_exit_can_reconnect_stale_depth_until_market_close(monkeypatch,hour,minute,held,reconnect):
    from app.market_data import DhanMarketData
    from app.session import IST
    now=__import__('datetime').datetime(2026,9,4,hour,minute,tzinfo=IST)
    monkeypatch.setattr('app.market_data.now_ist',lambda:now)
    monkeypatch.setattr('app.market_data.session_state',lambda:'EXIT_ONLY')
    monkeypatch.setattr('app.market_data.time.monotonic',lambda:100.)
    feed=DhanMarketData('test','test-token','NIFTY')
    feed.option_contracts={(2,'123'):{'symbol':'NIFTY','contract_id':'held','qty':10 if held else 0}}
    calls=[]
    monkeypatch.setattr(feed,'refresh_credentials',lambda *a,**k:calls.append(1) or True)
    assert feed.reconnect_if_idle() is reconnect and bool(calls) is reconnect


def test_supervisor_reads_only_committed_occupied_ledger_and_retains_pending_exit(tmp_path):
    from paper_service import durable_account
    from tests.test_paper import enter
    broker,store,clock=plan_account(tmp_path)
    order=enter(broker,clock,qty=10)
    broker.request_exit(order['id'],'SESSION_CLOSE',clock['now'])
    before=store.get_record('paper','account')
    assert durable_account(store.path)==before
    restored=__import__('app.broker',fromlist=['PaperBroker']).PaperBroker(store,30000,broker.cost,
        clock=lambda:clock['now'],policy=broker.policy)
    assert restored.positions()['positions'][0]['exit_request']==before['positions'][0]['exit_request']
    assert not store.list_records('trades')
    bad=dict(before,positions=[dict(before['positions'][0],qty=0)])
    store.put_record('paper','account',bad)
    assert durable_account(store.path) is None
    assert store.get_record('paper','account')==bad
    absent=tmp_path/'must-not-be-created.db'
    assert durable_account(absent) is None and not absent.exists()


def test_supervisor_history_is_bounded_and_deduplicates_unchanged_state(tmp_path,monkeypatch):
    import paper_service
    path=tmp_path/'supervisor.json'
    monkeypatch.setattr(paper_service,'STATUS',path)
    monkeypatch.setattr(paper_service,'supervisor_status',lambda:__import__('json').loads(path.read_text()) if path.exists() else {})
    paper_service.record_status('RESTART_REQUESTED','OWNED_API_UNRESPONSIVE',[100.])
    paper_service.record_status('RESTART_REQUESTED','OWNED_API_UNRESPONSIVE',[100.])
    assert len(paper_service.supervisor_status()['history'])==1
    for i in range(60): paper_service.record_status('RECOVERED',str(i),[100.])
    assert len(paper_service.supervisor_status()['history'])==50


@pytest.mark.parametrize('occupied,blocked,unowned',[(False,False,False),(True,False,False),
    (True,True,False),(True,False,True)])
def test_supervisor_timeout_restarts_only_owned_api_then_verifies_new_workers(tmp_path,monkeypatch,occupied,blocked,unowned):
    import paper_service,msvcrt
    from tests.test_paper import enter
    broker,store,clock=plan_account(tmp_path)
    if occupied:
        order=enter(broker,clock,qty=10)
        broker.request_exit(order['id'],'SESSION_CLOSE',clock['now'])
    committed=store.get_record('paper','account')
    root=tmp_path/'backend'; root.mkdir()
    monkeypatch.setattr(paper_service,'ROOT',root)
    monkeypatch.setattr(paper_service,'STATUS',root/'status.json')
    read_account=paper_service.durable_account
    monkeypatch.setattr(paper_service,'durable_account',lambda:None if blocked else read_account(store.path))
    monkeypatch.setattr(paper_service,'datetime',SimpleNamespace(now=lambda _:clock['now']))
    read_status=paper_service.supervisor_status
    monkeypatch.setattr(paper_service,'supervisor_status',lambda:read_status(root/'status.json'))
    monkeypatch.setattr(msvcrt,'locking',lambda *a:None)
    requests={'count':0}; started=[]; stopped=[]; ticks={'value':0}; sleeps={'count':0}
    def monotonic():
        ticks['value']+=40
        return ticks['value']
    monkeypatch.setattr(paper_service.time,'monotonic',monotonic)
    def start(*args,**kwargs):
        child=SimpleNamespace(pid=len(started)+1,poll=lambda:None)
        started.append(child); return child
    monkeypatch.setattr(paper_service.subprocess,'Popen',start)
    monkeypatch.setattr(paper_service,'stop_owned_api',lambda child:stopped.append(child))
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
    def request(*args,**kwargs):
        requests['count']+=1
        if requests['count']<=6: raise TimeoutError()
        return Response()
    monkeypatch.setattr(paper_service.urllib.request,'urlopen',request)
    monkeypatch.setattr(paper_service.json,'load',lambda _: {'app':'healthy','runtime':{'healthy':True}})
    import socket
    class Socket:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def connect_ex(self,*args): return 0 if unowned else 1
    monkeypatch.setattr(socket,'socket',lambda *a:Socket())
    class Finished(Exception): pass
    def sleep(*args):
        sleeps['count']+=1
        if sleeps['count']==7: raise Finished()
    monkeypatch.setattr(paper_service.time,'sleep',sleep)
    with pytest.raises(Finished): paper_service.main()
    if unowned:
        assert not started and not stopped
    elif blocked:
        assert len(started)==1 and not stopped
        assert paper_service.supervisor_status()['state']=='BLOCKED'
    else:
        assert len(started)==2 and stopped==[started[0]]
        assert paper_service.supervisor_status()['state']=='RECOVERED'
        assert [e['state'] for e in paper_service.supervisor_status()['history']][-2:]==['RESTART_REQUESTED','RECOVERED']
    assert store.get_record('paper','account')==committed and not store.list_records('trades')
