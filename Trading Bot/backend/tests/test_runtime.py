"""Isolated runtime tests. No broker requests or production account writes."""
from datetime import datetime,timedelta
from types import SimpleNamespace
import pandas as pd
import pytest
from app.config import Settings,current_credentials
from app.market_data import DhanMarketData,DhanGateway
from app.session import IST,quote_is_fresh,session_state
from app.paper_engine import PaperEngine
from app.expectancy import ExpectancyEngine
from tests.test_paper import plan_account,contract,quote,signal,enter


def test_feed_trade_timestamp_preserves_sdk_wall_clock_and_date():
    from datetime import timezone
    from app.market_data import feed_trade_timestamp,exchange_timestamp
    # Captured feed convention: the epoch's UTC wall clock is exchange IST.
    epoch=int(datetime(2026,10,6,11,4,33,tzinfo=timezone.utc).timestamp())
    assert feed_trade_timestamp(epoch)=="2026-10-06T11:04:33+05:30"
    assert exchange_timestamp(feed_trade_timestamp(epoch))=="2026-10-06T11:04:33+05:30"
    assert exchange_timestamp(epoch)=="2026-10-06T16:34:33+05:30"
    yesterday=int(datetime(2026,10,5,15,29,59,tzinfo=timezone.utc).timestamp())
    assert feed_trade_timestamp(yesterday)=="2026-10-05T15:29:59+05:30"


def test_normalized_feed_time_reaches_underlying_and_option_observations():
    from app.market_data import feed_trade_timestamp
    from datetime import timezone
    stamp=feed_trade_timestamp(int(datetime(2026,10,6,11,4,33,tzinfo=timezone.utc).timestamp()))
    feed=DhanMarketData('test','test','NIFTY')
    feed.security_to_symbol['13']='NIFTY'
    feed._on_message(None,{'security_id':13,'exchange_segment':0,'type':'Ticker Data','LTP':'22674','LTT':stamp})
    assert feed.latest['NIFTY']['exchange_timestamp']==stamp
    c={**contract(),'security_id':'999','exchange':'NSE'}
    feed.subscribe_options([c])
    feed._on_message(None,{'security_id':999,'exchange_segment':2,'type':'Full Data','LTP':'100','LTT':stamp,
        'depth':[{'bid_price':'99','ask_price':'100','bid_quantity':20,'ask_quantity':30}]})
    q=feed.executable_quotes()[c['contract_id']]
    assert q['exchange_timestamp']==stamp
    assert q['quote_update_timestamp']!=stamp


def test_dhan_profile_validator_accepts_current_top_level_shape(monkeypatch):
    import dhanhq
    monkeypatch.setattr(dhanhq.DhanLogin,"user_profile",lambda *_:{
        "dhanClientId":"test-client","tokenValidity":"2026-10-04 09:02:15.0",
        "dataPlan":"Active","dataValidity":"2026-10-04 09:02:15.0"})
    result=__import__('app.broker',fromlist=['DhanBroker']).DhanBroker('test-client','test-token').validate_access()
    assert result=={"valid":True,"reason":None,"data_plan":"Active","data_validity":"2026-10-04 09:02:15.0"}


def test_env_rotation_overrides_inherited_old_value(tmp_path,monkeypatch):
    path=tmp_path/'.env'
    monkeypatch.setenv('DHAN_ACCESS_TOKEN','expired-inherited-test-token')
    path.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=first-test-token\n')
    assert current_credentials(path)==('test','first-test-token')
    path.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=replacement-test-token\n')
    assert current_credentials(path)==('test','replacement-test-token')
    path.write_text('DHAN_CLIENT_ID=test\nDHAN_ACCESS_TOKEN=\n')
    assert current_credentials(path)==('test','')


def test_gateway_discards_response_from_rotated_credentials(tmp_path,monkeypatch):
    import dhanhq
    credentials=['test','old-test-token']
    calls=[]
    class Client:
        def __init__(self,context):
            self.token=context.get_access_token(); self.dhan_http=SimpleNamespace(timeout=None)
        def ticker_data(self,*args):
            calls.append(self.token)
            if self.token=='old-test-token': credentials[1]='new-test-token'
            return {'status':'success','data':{'token_generation':self.token}}
    monkeypatch.setattr(dhanhq,'dhanhq',Client)
    monkeypatch.setattr('app.market_data.time.sleep',lambda _:None)
    from app.store import Store
    g=DhanGateway(Settings(_env_file=None,dhan_client_id='test',dhan_access_token='old-test-token'),Store(tmp_path/'cache.db'),lambda:tuple(credentials))
    assert g.call(g.client.ticker_data,{})['token_generation']=='new-test-token'
    assert calls==['old-test-token','new-test-token']
    assert g.credential_generation==1


def test_rotated_credentials_clear_stale_data_errors(tmp_path):
    broker,store,_=plan_account(tmp_path)
    credentials=['test','new-test-token']
    class Gateway:
        credential_provider=True
        credential_generation=0
        credentials=('test','old-test-token')
        def refresh_credentials(self):
            self.credentials=tuple(credentials)
            self.credential_generation+=1
            return True
    market=SimpleNamespace(refresh_credentials=lambda *_:True)
    engine=PaperEngine(Settings(_env_file=None),store,Gateway(),broker,market)
    engine.status.update(data_error="DH-901 Invalid_Authentication",
                         data_symbols={"NIFTY":{"error":"DH-901 Invalid_Authentication"}})

    engine._refresh_runtime_credentials(datetime.now(IST))

    assert "data_error" not in engine.status
    assert "error" not in engine.status["data_symbols"]["NIFTY"]
    assert engine.status["credentials"]["generation"]==1


def test_option_stream_requires_depth_and_explicit_freshness():
    feed=DhanMarketData('test','test','NIFTY,SENSEX')
    c={**contract(),'security_id':'999','exchange':'NSE'}
    feed.subscribe_options([c])
    packet={'security_id':999,'exchange_segment':2,'type':'Full Data','LTP':'100','LTT':'2026-09-04T10:00:00+05:30',
            'volume':100,'OI':100,'depth':[{'bid_price':'99','ask_price':'100','bid_quantity':20,'ask_quantity':30}]}
    feed._on_message(None,packet)
    q=feed.executable_quotes()[c['contract_id']]
    # Assert against a controlled observation time, not test-runner wall-clock speed.
    assert q['bid']==99 and q['ask_qty']==30 and quote_is_fresh(q,datetime.fromisoformat(q['timestamp'])+timedelta(seconds=1))
    assert not quote_is_fresh(q,datetime.fromisoformat(q['timestamp'])+timedelta(seconds=3))
    feed._on_message(None,{**packet,'type':'Ticker Data','LTP':'105'})
    assert feed.executable_quotes()[c['contract_id']]['ask']==100
    assert not quote_is_fresh({'quote_update_timestamp':None,'exchange_timestamp':q['timestamp'],'source':'dhan_quote'})


def test_execution_snapshot_returns_underlying_and_options_atomically():
    feed=DhanMarketData('test','test','NIFTY,SENSEX')
    feed.latest['NIFTY']={'symbol':'NIFTY','ltp':24000}
    feed.option_quotes={'nifty-contract':{'symbol':'NIFTY','ask':100},'sensex-contract':{'symbol':'SENSEX','ask':200}}
    snapshot=feed.execution_snapshot('NIFTY')
    assert snapshot['underlying']['ltp']==24000
    assert set(snapshot['options'])=={'nifty-contract'}


def test_sparse_depth_preserves_chain_oi_but_explicit_zero_is_not_replaced():
    feed=DhanMarketData('test','test','NIFTY,SENSEX')
    c={**contract(),'security_id':'999','exchange':'NSE','oi':100,'volume':200,
       'delta':.5,'greeks_observed_at':'2026-09-04T10:00:00+05:30'}
    feed.subscribe_options([c])
    packet={'security_id':999,'exchange_segment':2,'type':'Full Data','LTP':'100',
            'depth':[{'bid_price':'99','ask_price':'100','bid_quantity':20,'ask_quantity':30}]}
    feed._on_message(None,packet)
    q=feed.executable_quotes()[c['contract_id']]
    assert q['oi']==100 and q['volume']==200 and q['greeks_observed_at']==c['greeks_observed_at']
    feed._on_message(None,{**packet,'OI':0,'volume':0})
    q=feed.executable_quotes()[c['contract_id']]
    assert q['oi']==0 and q['volume']==0


def test_stream_rotation_drops_old_prices_and_old_callbacks(monkeypatch):
    feed=DhanMarketData('test','old','NIFTY')
    feed.latest={'NIFTY':{'ltp':10}};feed.option_quotes={'old':{'ask':2}}
    old=object();feed.feed=old
    monkeypatch.setattr(feed,'stop',lambda:feed.stopping.set())
    monkeypatch.setattr(feed,'start',lambda:None)
    assert feed.refresh_credentials('test','new')
    assert not feed.latest and not feed.option_quotes
    feed._on_message(old,{'security_id':13,'exchange_segment':0,'LTP':100})
    assert not feed.latest


def test_first_paper_trade_collects_evidence_and_exits_at_1505(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    settings=Settings(_env_file=None,paper_collect_evidence=True,session_exit='15:05')
    engine=PaperEngine(settings,store,None,broker)
    c=contract();q={**quote(c,clock),'oi':10000,'volume':1000,'is_atm':False,
                    'delta':.5,'greeks_observed_at':clock['now'].isoformat()}
    s={**signal(),'symbol':'NIFTY','option_type':'CALL','strategy_version':'orb-retest-v1',
       'retest_timestamp':clock['now'].isoformat(),'invalidation':24000}
    engine.protections[(s['id'],c['contract_id'])]={**c,'low':90}
    engine._enter(s,{c['contract_id']:q},clock['now'])
    assert broker.snapshot()['open_positions']==1,engine.status
    assert broker.snapshot()['positions'][0]['evidence_mode']=='paper_observation'
    ev=[e for e in store.list_records('events') if e['agent']=='EV'][0]
    assert ev['status']=='OBSERVATION' and ev['evaluation']['evidence']['samples']==0
    clock['now']=clock['now'].replace(hour=15,minute=5)
    monkeypatch.setattr('app.paper_engine.now_ist',lambda:clock['now'])
    monkeypatch.setattr(engine,'_session',lambda:session_state(clock['now']))
    engine.quotes={c['contract_id']:quote(c,clock,bid=101)}
    engine.cycle()
    assert broker.snapshot()['open_positions']==0
    assert store.list_records('episodes')[0]['reason']=='SESSION_EXIT'


def test_evidence_mode_does_not_override_negative_supported_edge(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None,paper_collect_evidence=True),store,None,broker)
    c=contract();s={**signal(),'symbol':'NIFTY','option_type':'CALL','strategy_version':'orb-retest-v1','retest_timestamp':clock['now'].isoformat()}
    engine.protections[(s['id'],c['contract_id'])]={**c,'low':90}
    monkeypatch.setattr(ExpectancyEngine,'evaluate_net',lambda *a:{'status':'REJECTED','reason':'Net edge is not supported by session-clustered evidence'})
    engine._enter(s,{c['contract_id']:{**quote(c,clock),'oi':10000,'volume':1000,
                    'delta':.5,'greeks_observed_at':clock['now'].isoformat()}},clock['now'])
    assert broker.snapshot()['open_positions']==0
    assert any(e['agent']=='EV' and e['status']=='REJECTED' for e in store.list_records('events'))


@pytest.mark.parametrize('h,m,s,state',[(9,14,59,'PREOPEN'),(9,15,0,'ENTRY_WINDOW'),(15,4,59,'MANAGE_ONLY'),(15,5,0,'EXIT_ONLY')])
def test_exact_session_boundaries(h,m,s,state):
    assert session_state(datetime(2026,9,4,h,m,s,tzinfo=IST))==state


def test_scan_status_reports_missing_candles_instead_of_old_pause(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    monkeypatch.setattr('app.paper_engine.now_ist',lambda:clock['now'])
    monkeypatch.setattr(engine,'_session',lambda:'ENTRY_WINDOW')
    engine.cycle()
    assert set(engine.status['scans'])=={'NIFTY','SENSEX'}
    assert all('candles' in s['reason'] for s in engine.status['scans'].values())


def test_new_scan_clears_old_agent_decisions():
    from app.telemetry.decision_trace import pipeline_from_events
    rows=pipeline_from_events([
        {'agent':'Scanner','symbol':'NIFTY','status':'PASS'},
        {'agent':'Option Selector','symbol':'NIFTY','status':'REJECTED','summary':'Old quote failure'},
        {'agent':'Scanner','symbol':'NIFTY','status':'WAITING','summary':'No setup'}], 'NIFTY')
    assert rows[0]['label']=='No setup'
    assert next(r for r in rows if r['agent']=='Option Selector')['status']=='WAITING'


def test_expiry_day_is_skipped_for_paper_policy(monkeypatch):
    g=object.__new__(DhanGateway)
    g.client=SimpleNamespace(expiry_list=object(),option_chain=object())
    g.underlyings=lambda:[{'symbol':'NIFTY','security_id':'13'}]
    g.contracts=lambda symbol:[]
    def call(method,*args,**kwargs):
        if method is g.client.expiry_list: return ['2026-09-04','2026-09-10']
        assert args[2]=='2026-09-10'
        return {}
    g.call=call
    monkeypatch.setattr('app.market_data.now_ist',lambda:datetime(2026,9,4,10,tzinfo=IST))
    assert g.chain('NIFTY',exclude_expiry_day=True)==[]


def test_disabled_evidence_collection_cannot_start_with_zero_outcomes(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    engine=PaperEngine(Settings(_env_file=None,paper_collect_evidence=False),store,None,broker)
    c=contract();s={**signal(),'symbol':'NIFTY','option_type':'CALL','strategy_version':'orb-retest-v1','retest_timestamp':clock['now'].isoformat()}
    engine.protections[(s['id'],c['contract_id'])]={**c,'low':90}
    engine._enter(s,{c['contract_id']:{**quote(c,clock),'oi':10000,'volume':1000}},clock['now'])
    assert broker.snapshot()['open_positions']==0


def test_missing_depth_at_1505_keeps_pending_position(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    enter(broker,clock,qty=10)
    clock['now']=clock['now'].replace(hour=15,minute=5)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    monkeypatch.setattr('app.paper_engine.now_ist',lambda:clock['now'])
    monkeypatch.setattr(engine,'_session',lambda:session_state(clock['now']))
    engine.cycle()
    assert broker.snapshot()['open_positions']==1
    assert 'fresh' in engine.status['exit_error']
    assert not store.list_records('trades')
