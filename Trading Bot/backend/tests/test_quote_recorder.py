import json
import sqlite3
import time
from app.quote_recorder import QuoteRecorder


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
