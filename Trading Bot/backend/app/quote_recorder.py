"""Bounded, asynchronous recording of normalized observations, never credentials."""
import json
import math
import queue
import shutil
import sqlite3
import threading
import time
import uuid
import zlib
from pathlib import Path
from .session import now_ist

FIELDS={"symbol","security_id","contract_id","exchange","expiry","strike","option_type","lot_size","tick_size",
        "identity_verified","metadata_source","source","timestamp","quote_update_timestamp","exchange_timestamp",
        "last_trade_timestamp","bid","ask","bid_qty","ask_qty","ltp","open","high","low","close","volume","oi",
        "packet_type","sequence","exchange_segment","raw_exchange_timestamp","depth",
        "delta","gamma","theta","vega","iv","greeks_source","greeks_observed_at","greek_units",
        "chain_observed_at","previous_oi","spot","is_atm"}
DEPTH_FIELDS={"bid_price","bid_quantity","bid_orders","ask_price","ask_quantity","ask_orders"}


class QuoteRecorder:
    def __init__(self,path,*,capacity=100000,batch_size=2000,max_bytes=1024**3,min_free_bytes=1024**3,archive_dir=None,legacy_paths=()):
        self.path=Path(path); self.queue=queue.Queue(maxsize=capacity)
        self.archive_dir=Path(archive_dir) if archive_dir else None
        self.legacy_paths=tuple(Path(path) for path in legacy_paths)
        self.batch_size=batch_size; self.max_bytes=max_bytes; self.min_free_bytes=min_free_bytes
        self.stop_event=threading.Event(); self.thread=None; self.lock=threading.Lock()
        self.run_id=str(uuid.uuid4()); self.persisted=0; self.dropped=0; self.error=None
        self.last_write=None; self.last_drop=None; self.accepting=False

    def start(self):
        if self.thread and self.thread.is_alive(): return
        if self.thread is not None:
            self.run_id=str(uuid.uuid4()); self.persisted=0; self.dropped=0
            self.error=None; self.last_write=None; self.last_drop=None
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stop_event.clear(); self.accepting=True
        self.thread=threading.Thread(target=self._loop,name='quote-recorder',daemon=True)
        self.thread.start()

    def record(self,kind,values,generation=0):
        safe={}
        for key in FIELDS:
            value=values.get(key)
            if key=="greek_units" and isinstance(value,dict):
                safe[key]={name:unit for name,unit in value.items() if name in {"delta","gamma","theta","vega"} and isinstance(unit,str) and len(unit)<80}
            if isinstance(value,str): safe[key]=value[:512]
            elif isinstance(value,(bool,int,float)) and (not isinstance(value,float) or math.isfinite(value)):
                safe[key]=value
            elif key=="depth" and isinstance(value,list):
                safe[key]=[{name:item[name] for name in DEPTH_FIELDS if name in item and
                            isinstance(item[name],(bool,int,float)) and
                            (not isinstance(item[name],float) or math.isfinite(item[name]))}
                           for item in value[:5] if isinstance(item,dict)]
        return self._enqueue(kind,json.dumps(safe,allow_nan=False),generation)

    def _enqueue(self,kind,payload,generation=0,received_at=None):
        identifier=str(uuid.uuid4())
        item=(identifier,self.run_id,received_at or now_ist().isoformat(),kind,int(generation),payload)
        with self.lock:
            if not self.accepting:
                self.dropped+=1; self.last_drop=item[2]; return None
            try: self.queue.put_nowait(item)
            except queue.Full:
                self.dropped+=1; self.last_drop=item[2]; return None
        return identifier

    def _size(self):
        return sum(p.stat().st_size for p in (self.path,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')) if p.exists())

    def _loop(self):
        connection=None
        pending_count=0; saved_dropped=0
        try:
            connection=sqlite3.connect(self.path,timeout=1)
            # Keep index pages in memory instead of rereading them from the
            # growing observation database for every insertion batch.
            connection.execute('PRAGMA cache_size=-131072')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=NORMAL')
            connection.execute('PRAGMA wal_autocheckpoint=4000')
            connection.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,run_id TEXT,received_at TEXT,kind TEXT,generation INTEGER,payload TEXT)')
            connection.execute('CREATE INDEX IF NOT EXISTS observations_time ON observations(received_at,id)')
            connection.execute('CREATE TABLE IF NOT EXISTS recorder_runs(id TEXT PRIMARY KEY,started_at TEXT,ended_at TEXT,clean_shutdown INTEGER,persisted INTEGER,dropped INTEGER,last_drop TEXT,error TEXT)')
            connection.execute('INSERT INTO recorder_runs VALUES(?,?,NULL,0,0,0,NULL,NULL)',(self.run_id,now_ist().isoformat()))
            connection.commit()
            last_checkpoint=time.monotonic()
            while not self.stop_event.is_set() or not self.queue.empty():
                batch=[]
                try: batch.append(self.queue.get(timeout=.25))
                except queue.Empty: pass
                while len(batch)<self.batch_size:
                    try: batch.append(self.queue.get_nowait())
                    except queue.Empty: break
                if not batch and self.dropped==saved_dropped: continue
                if batch:
                    estimate=sum(len(item[-1] if isinstance(item[-1],bytes) else item[-1].encode())+512 for item in batch)
                    if self._size()+estimate>self.max_bytes or shutil.disk_usage(self.path.parent).free<self.min_free_bytes+estimate:
                        with self.lock:
                            self.dropped+=len(batch); self.last_drop=batch[-1][2]; self.error='STORAGE_LIMIT'
                        batch=[]
                    else:
                        pending_count=len(batch)
                        with connection:
                            connection.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',batch)
                            self.persisted+=len(batch); self.last_write=now_ist().isoformat()
                            connection.execute('UPDATE recorder_runs SET persisted=?,dropped=?,last_drop=?,error=? WHERE id=?',
                                               (self.persisted,self.dropped,self.last_drop,self.error,self.run_id))
                        pending_count=0
                elif self.dropped!=saved_dropped:
                    with connection:
                        connection.execute('UPDATE recorder_runs SET persisted=?,dropped=?,last_drop=?,error=? WHERE id=?',
                                           (self.persisted,self.dropped,self.last_drop,self.error,self.run_id))
                saved_dropped=self.dropped
                if time.monotonic()-last_checkpoint>=5:
                    connection.execute('PRAGMA wal_checkpoint(PASSIVE)')
                    last_checkpoint=time.monotonic()
            with connection:
                connection.execute('UPDATE recorder_runs SET ended_at=?,clean_shutdown=1 WHERE id=?',(now_ist().isoformat(),self.run_id))
        except Exception as exc:
            self.error=type(exc).__name__
            with self.lock:
                self.accepting=False
                self.dropped+=pending_count
                while not self.queue.empty():
                    try: self.queue.get_nowait(); self.dropped+=1
                    except queue.Empty: break
            # The run remains unclean after an I/O failure. Never claim its
            # sequence is a complete market history after recovery.
        finally:
            if connection is not None: connection.close()

    def stop(self):
        with self.lock: self.accepting=False
        self.stop_event.set()
        # The writer drains its queue before exiting. A timed join allowed the
        # process to exit with daemon-thread observations still only in memory.
        if self.thread: self.thread.join()

    def status(self):
        return {"mode":"durable_normalized_quotes","run_id":self.run_id,
                "worker_alive":bool(self.thread and self.thread.is_alive()),"queued":self.queue.qsize(),
                "persisted_this_run":self.persisted,"dropped_this_run":self.dropped,"last_drop":self.last_drop,
                "last_write":self.last_write,"error":self.error,"storage_limit_bytes":self.max_bytes,
                "storage":str(self.path),"complete_exchange_history_verified":False,
                "limitations":["Records normalized top-of-book observations, not raw packets or full exchange depth.",
                               "Receive timestamps are not exchange book timestamps; missing exchange sequences cannot be inferred.",
                               "Queue drops, storage errors and unclean runs invalidate claims of complete coverage."]}

    def read(self,identifier):
        paths=[self.path,*self.legacy_paths]
        if self.archive_dir: paths.extend(sorted(self.archive_dir.glob('*.db'),reverse=True))
        for path in dict.fromkeys(paths):
            result=self._read_path(path,identifier)
            if result is not None: return result
        return None

    def _read_path(self,path,identifier):
        if not path.exists(): return None
        connection=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
        try:
            row=connection.execute('SELECT rowid,id,run_id,received_at,kind,generation,payload FROM observations WHERE id=?',(identifier,)).fetchone()
            if row is None: return None
            return dict(capture_sequence=row[0],id=row[1],run_id=row[2],received_at=row[3],kind=row[4],
                        credential_generation=row[5],quote=json.loads(zlib.decompress(row[6]) if isinstance(row[6],bytes) else row[6]))
        finally: connection.close()
