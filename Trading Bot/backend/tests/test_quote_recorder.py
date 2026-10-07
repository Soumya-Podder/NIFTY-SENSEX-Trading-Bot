import json
import sqlite3
import time
import threading
from app.quote_recorder import QuoteRecorder


def test_stop_waits_for_writer_completion():
    recorder=QuoteRecorder('unused.db')
    release=threading.Event()
    recorder.thread=threading.Thread(target=release.wait)
    recorder.thread.start()
    stopped=threading.Event()
    stopper=threading.Thread(target=lambda:(recorder.stop(),stopped.set()))
    stopper.start()
    try:
        assert recorder.stop_event.wait(1)
        assert not stopped.wait(.05)
    finally:
        release.set(); stopper.join(2); recorder.thread.join(2)
    assert stopped.is_set()


def test_archive_reads_preserve_legacy_and_previous_capture_ids(tmp_path):
    archive=tmp_path/'archive'; archive.mkdir()
    old_paths=[tmp_path/'legacy.db',archive/'previous.db']
    identifiers=[]
    for path in old_paths:
        old=QuoteRecorder(path,min_free_bytes=0)
        old.start(); identifiers.append(old.record('underlying',{'symbol':'NIFTY','ltp':22000}))
        old.stop()
    current=QuoteRecorder(archive/'current.db',archive_dir=archive,legacy_paths=(old_paths[0],),min_free_bytes=0)
    current.start(); current.stop()
    for identifier in identifiers:
        assert current.read(identifier)['quote']['ltp']==22000


def test_quote_round_trip_is_durable_and_does_not_record_credentials(tmp_path):
    path=tmp_path/'quotes.db'
    recorder=QuoteRecorder(path,min_free_bytes=0)
    recorder.start()
    identifier=recorder.record('option_depth',{'contract_id':'test','bid':99,'ask':100,'bid_qty':10,
                                             'timestamp':'2026-09-15T10:00:00+05:30',
                                             'access_token':'secret-test-value','raw':{'api_key':'secret-test-value'}},2)
    recorder.stop()
    assert recorder.persisted==1
    with sqlite3.connect(path) as db:
        row=db.execute('SELECT id,generation,payload FROM observations').fetchone()
        run=db.execute('SELECT clean_shutdown,persisted,dropped FROM recorder_runs').fetchone()
    assert row[0]==identifier and row[1]==2
    assert json.loads(row[2])['bid']==99
    assert 'secret-test-value' not in row[2]
    assert run==(1,1,0)
    assert recorder.read(identifier)['quote']['ask']==100
    assert recorder.read('missing') is None
    restored=QuoteRecorder(path,min_free_bytes=0)
    restored.start(); restored.stop()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM observations').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM recorder_runs').fetchone()[0]==2
    restored.start(); restored.stop()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM recorder_runs').fetchone()[0]==3


def test_full_depth_and_sequence_are_durable_but_unknown_packet_fields_are_not(tmp_path):
    path=tmp_path/'depth.db'
    recorder=QuoteRecorder(path,min_free_bytes=0)
    recorder.start()
    identifier=recorder.record('option_depth',{
        'contract_id':'fixed-contract','packet_type':'Full Data','sequence':42,
        'ordering_rejected':True,'ordering_status':'NONINCREASING_SEQUENCE','exchange_book_freshness_verified':False,
        'exchange_segment':2,'raw_exchange_timestamp':1780000000,
        'depth':[{'bid_price':99.5,'bid_quantity':50,'bid_orders':3,
                  'ask_price':100.0,'ask_quantity':25,'ask_orders':2,
                  'unknown_depth_value':'discard-me'} for _ in range(7)],
        'access_token':'must-not-be-recorded','unknown_packet_field':'discard-me',
    })
    recorder.stop()
    saved=recorder.read(identifier)['quote']
    assert saved['sequence']==42 and saved['packet_type']=='Full Data'
    assert saved['ordering_rejected'] and not saved['exchange_book_freshness_verified']
    assert saved['ordering_status']=='NONINCREASING_SEQUENCE'
    assert len(saved['depth'])==5 and saved['depth'][0]['bid_orders']==3
    assert 'unknown_depth_value' not in saved['depth'][0]
    assert 'access_token' not in saved and 'unknown_packet_field' not in saved


def test_queue_overflow_and_storage_limit_are_not_silent(tmp_path):
    recorder=QuoteRecorder(tmp_path/'bounded.db',capacity=1,max_bytes=1,min_free_bytes=0)
    recorder.accepting=True
    assert recorder.record('underlying',{'symbol':'NIFTY','ltp':100})
    assert recorder.record('underlying',{'symbol':'NIFTY','ltp':101}) is None
    recorder.start(); recorder.stop()
    assert recorder.status()['dropped_this_run']==2
    assert recorder.status()['error']=='STORAGE_LIMIT'
    assert recorder.persisted==0
    assert not recorder.status()['complete_exchange_history_verified']


def test_failed_writer_stops_accepting_observations(tmp_path,monkeypatch):
    def fail(*a,**kw): raise sqlite3.OperationalError('disk failure')
    monkeypatch.setattr('app.quote_recorder.sqlite3.connect',fail)
    recorder=QuoteRecorder(tmp_path/'failure.db',min_free_bytes=0)
    recorder.start(); recorder.stop()
    assert recorder.status()['error']=='OperationalError'
    assert recorder.record('underlying',{'ltp':100}) is None
    assert not recorder.status()['worker_alive']


def test_live_sized_burst_drains_without_queue_drops(tmp_path):
    recorder=QuoteRecorder(tmp_path/'burst.db',capacity=25000,batch_size=2000,min_free_bytes=0)
    recorder.start()
    for value in range(20000):
        assert recorder.record('option_depth',{'contract_id':f'test-{value % 48}','bid':100,'ask':101})
    deadline=time.time()+10
    while recorder.status()['queued'] and time.time()<deadline:
        time.sleep(.02)
    recorder.stop()
    assert recorder.status()['queued']==0
    assert recorder.status()['dropped_this_run']==0
    assert recorder.status()['error'] is None
    assert recorder.persisted==20000
