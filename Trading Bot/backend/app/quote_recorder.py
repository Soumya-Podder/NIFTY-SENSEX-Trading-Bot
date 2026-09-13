"""Bounded, asynchronous recording of normalized observations, never credentials."""
import json
import math
import queue
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path
from .session import now_ist

FIELDS={"symbol","security_id","contract_id","exchange","expiry","strike","option_type","lot_size","tick_size",
        "identity_verified","metadata_source","source","timestamp","quote_update_timestamp","exchange_timestamp",
        "last_trade_timestamp","bid","ask","bid_qty","ask_qty","ltp","open","high","low","close","volume","oi"}


class QuoteRecorder:
    def __init__(self,path,*,capacity=10000,max_bytes=1024**3,min_free_bytes=1024**3):
        self.path=Path(path); self.queue=queue.Queue(maxsize=capacity)
        self.max_bytes=max_bytes; self.min_free_bytes=min_free_bytes
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
            if isinstance(value,str): safe[key]=value[:512]
            elif isinstance(value,(bool,int,float)) and (not isinstance(value,float) or math.isfinite(value)):
                safe[key]=value
        identifier=str(uuid.uuid4())
        item=(identifier,self.run_id,now_ist().isoformat(),kind,int(generation),json.dumps(safe,allow_nan=False))
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
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,run_id TEXT,received_at TEXT,kind TEXT,generation INTEGER,payload TEXT)')
            connection.execute('CREATE INDEX IF NOT EXISTS observations_time ON observations(received_at,id)')
            connection.execute('CREATE TABLE IF NOT EXISTS recorder_runs(id TEXT PRIMARY KEY,started_at TEXT,ended_at TEXT,clean_shutdown INTEGER,persisted INTEGER,dropped INTEGER,last_drop TEXT,error TEXT)')
            connection.execute('INSERT INTO recorder_runs VALUES(?,?,NULL,0,0,0,NULL,NULL)',(self.run_id,now_ist().isoformat()))
            connection.commit()
            while not self.stop_event.is_set() or not self.queue.empty():
                batch=[]
                try: batch.append(self.queue.get(timeout=.25))
                except queue.Empty: pass
                while len(batch)<250:
                    try: batch.append(self.queue.get_nowait())
                    except queue.Empty: break
                if not batch and self.dropped==saved_dropped: continue
                if batch:
                    estimate=sum(len(item[-1].encode())+512 for item in batch)
                    if self._size()+estimate>self.max_bytes or shutil.disk_usage(self.path.parent).free<self.min_free_bytes+estimate:
                        with self.lock:
                            self.dropped+=len(batch); self.last_drop=batch[-1][2]; self.error='STORAGE_LIMIT'
                        batch=[]
                    else:
                        pending_count=len(batch)
                        with connection:
                            connection.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',batch)
                        self.persisted+=len(batch); self.last_write=now_ist().isoformat()
                        pending_count=0
                with connection:
                    connection.execute('UPDATE recorder_runs SET persisted=?,dropped=?,last_drop=?,error=? WHERE id=?',
                                       (self.persisted,self.dropped,self.last_drop,self.error,self.run_id))
                saved_dropped=self.dropped
                connection.execute('PRAGMA wal_checkpoint(PASSIVE)')
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
        if self.thread: self.thread.join(timeout=3)

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
        if not self.path.exists(): return None
        connection=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
        try:
            row=connection.execute('SELECT rowid,id,run_id,received_at,kind,generation,payload FROM observations WHERE id=?',(identifier,)).fetchone()
            if row is None: return None
            return dict(capture_sequence=row[0],id=row[1],run_id=row[2],received_at=row[3],kind=row[4],
                        credential_generation=row[5],quote=json.loads(row[6]))
        finally: connection.close()
