"""Local paper API supervisor, started before the session by Windows Task Scheduler.

Uses a single-instance lock. A stalled owned API may restart only while durably flat.
Credentials are read only by the application, never passed on the command line.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent

def execution_stalled(health):
    """Missing quotes are not a stalled engine; a pending position forbids restart."""
    runtime=health.get('runtime',{})
    age=runtime.get('heartbeat_age_seconds')
    readiness=health.get('readiness',{})
    broker=health.get('broker',{})
    return (health.get('app')=='healthy' and isinstance(age,(float,int)) and age>60
        and broker.get('healthy') is True and broker.get('mode')=='paper'
        and readiness.get('exit_status')=='NO_POSITION' and readiness.get('positions')==[])


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
    child=None; stalled_checks=0; restarts=[]
    while True:
        now=datetime.now(ZoneInfo('Asia/Kolkata'))
        health={}
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3) as response:
                health=json.load(response)
        except Exception: pass
        healthy=health.get('app')=='healthy'
        owned=child is not None and child.poll() is None
        stalled_checks=stalled_checks+1 if owned and execution_stalled(health) else 0
        tick=time.monotonic()
        restarts=[stamp for stamp in restarts if tick-stamp<3600]
        if stalled_checks>=3 and len(restarts)<3 and (not restarts or tick-restarts[-1]>=300):
            # Each of three fresh health responses confirmed flat, healthy storage.
            # Unresponsive/unowned APIs and positions are left to protective workers.
            try:
                stop_owned_api(child)
                child=None; healthy=False; stalled_checks=0; restarts.append(tick)
            except (OSError,subprocess.SubprocessError): pass
        # Start early enough to load metadata/feed; the engine enforces 09:15.
        # Keep supervising after close to recover/manage pending observed exits.
        if not healthy and (now.weekday()<5 and now.strftime('%H:%M')>='09:10'):
            import socket
            with socket.socket() as probe:
                occupied=probe.connect_ex(('127.0.0.1',8080))==0
            if not occupied and (child is None or child.poll() is not None):
                child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8080','--no-access-log'],
                    cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        time.sleep(2)

if __name__=='__main__': main()
