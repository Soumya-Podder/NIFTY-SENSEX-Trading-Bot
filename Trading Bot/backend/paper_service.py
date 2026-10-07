"""Local paper API supervisor, started before the session by Windows Task Scheduler.

Uses a single-instance lock. An owned stalled API can restore an occupied ledger.
Credentials are read only by the application, never passed on the command line.
"""
from pathlib import Path
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
STATUS=ROOT/'.paper_service.status.json'


def durable_account(path=ROOT/'trading_bot.db'):
    """Read committed paper state without creating, repairing or changing the ledger."""
    try:
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.25) as connection:
            row=connection.execute("SELECT payload FROM records WHERE namespace='paper' AND key='account'").fetchone()
        account=json.loads(row[0]) if row else None
        if not isinstance(account,dict) or not isinstance(account.get('positions'),list): return None
        if not all(isinstance(account.get(k),bool) for k in ('enabled','halted')): return None
        if not all(math.isfinite(float(account[k])) for k in ('cash','initial_capital')): return None
        for p in account['positions']:
            if not isinstance(p,dict) or not p.get('id') or not p.get('contract_id'): return None
            if int(p['lot_size'])<=0 or int(p['qty'])<=0 or int(p['qty'])%int(p['lot_size']): return None
            if not all(math.isfinite(float(p[k])) for k in ('entry','stop','target','entry_charges_remaining')): return None
        return account
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError): return None


def supervisor_status(path=STATUS):
    try:
        value=json.loads(Path(path).read_text())
        return value if isinstance(value,dict) else {'state':'UNAVAILABLE'}
    except (OSError,ValueError): return {'state':'UNAVAILABLE'}


def record_status(state,reason,restarts):
    previous=supervisor_status()
    if previous.get('state')==state and previous.get('reason')==reason: return
    stamp=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
    history=previous.get('history',[])[-49:]+[{'state':state,'reason':reason,'at':stamp}]
    value={'state':state,'reason':reason,'checked_at':stamp,'restart_times':restarts,
        'history':history,'authority':'OWNED_PAPER_PROCESS_ONLY'}
    temporary=STATUS.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(value)); temporary.replace(STATUS)
    except OSError: pass  # Diagnostic failure cannot hold up held-contract recovery.

def execution_stalled(health):
    """Missing quotes are not a stall. Observe protection separately when occupied."""
    runtime=health.get('runtime',{})
    age=runtime.get('heartbeat_age_seconds')
    readiness=health.get('readiness',{})
    broker=health.get('broker',{})
    if health.get('app') not in {'healthy','degraded'} or broker.get('healthy') is not True or broker.get('mode')!='paper': return False
    positions=readiness.get('positions')
    if not isinstance(positions,list): return False
    if not positions:
        return readiness.get('exit_status')=='NO_POSITION' and isinstance(age,(float,int)) and age>60
    protection_age=runtime.get('protection_heartbeat_age_seconds')
    return ('paper-protection' in runtime.get('dead_workers',[]) or
        isinstance(protection_age,(float,int)) and protection_age>60)


def restart_reason(health,unresponsive_seconds,process_age):
    if process_age<90: return None  # Give metadata and workers a bounded startup grace.
    if execution_stalled(health): return 'STALLED_EXECUTION_OR_PROTECTION'
    if not health and unresponsive_seconds>=60: return 'OWNED_API_UNRESPONSIVE'
    return None


def stop_owned_api(child):
    # The Windows venv launcher has a child interpreter. Stop only our owned tree.
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else: child.terminate()
    child.wait(timeout=10)


def main():
    import msvcrt
    temporary=ROOT.parents[1]/'.tmp'
    temporary.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(temporary),TMP=str(temporary),PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode=True
    lock=(ROOT/'.paper_service.lock').open('a+b')
    lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: return
    child=None; stalled_checks=0; started=0; last_response=0; recovering=False
    restarts=[stamp for stamp in supervisor_status().get('restart_times',[])
        if isinstance(stamp,(float,int)) and 0<=time.time()-stamp<3600]
    while True:
        now=datetime.now(ZoneInfo('Asia/Kolkata'))
        health={}
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3) as response:
                health=json.load(response)
        except Exception: pass
        available=health.get('app') in {'healthy','degraded'}
        owned=child is not None and child.poll() is None
        tick=time.monotonic()
        if available: last_response=tick
        reason=restart_reason(health,tick-last_response,tick-started) if owned else None
        stalled_checks=stalled_checks+1 if reason else 0
        restarts=[stamp for stamp in restarts if time.time()-stamp<3600]
        if stalled_checks>=3:
            if len(restarts)>=3 or restarts and time.time()-restarts[-1]<300:
                record_status('BACKOFF','Restart budget/cooldown active; no parallel engine started',restarts)
            elif durable_account() is None:
                record_status('BLOCKED','Committed paper ledger unavailable; no restart or fabricated recovery',restarts)
            else:
                restarts.append(time.time())
                record_status('RESTART_REQUESTED',reason,restarts)
                try:
                    stop_owned_api(child)
                    child=None; available=False; stalled_checks=0; recovering=True; health={}; owned=False
                except (OSError,subprocess.SubprocessError):
                    record_status('BLOCKED','Owned process termination failed',restarts)
        if recovering and health.get('runtime',{}).get('healthy') is True and owned:
            record_status('RECOVERED','New paper workers verified; positions/exits retain fresh-depth gates',restarts)
            recovering=False
        elif owned and health.get('runtime',{}).get('healthy') is True and supervisor_status().get('state')=='STARTING':
            record_status('RUNNING','Owned paper workers verified',restarts)
        # Start early enough to load metadata/feed; the engine enforces 09:15.
        # Keep supervising after close to recover/manage pending observed exits.
        account=durable_account() if not available else None
        if not available and (recovering or child is not None or bool(account and account['positions']) or
            now.weekday()<5 and now.strftime('%H:%M')>='09:10'):
            import socket
            with socket.socket() as probe:
                occupied=probe.connect_ex(('127.0.0.1',8080))==0
            if not occupied and (child is None or child.poll() is not None):
                child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8080','--no-access-log'],
                    cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                started=time.monotonic(); last_response=started
                if not recovering: record_status('STARTING','Waiting for owned paper workers to become healthy',restarts)
        time.sleep(2)

if __name__=='__main__': main()
