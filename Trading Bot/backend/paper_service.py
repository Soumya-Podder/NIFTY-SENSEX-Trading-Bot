"""Local paper API supervisor, started before the session by Windows Task Scheduler.

Uses a single-instance file lock; never terminates a running API or a pending exit.
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

def main():
    import msvcrt
    lock=(ROOT/'.paper_service.lock').open('a+b')
    lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: return
    child=None
    while True:
        now=datetime.now(ZoneInfo('Asia/Kolkata'))
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3) as response:
                healthy=json.load(response).get('app')=='healthy'
        except Exception: healthy=False
        # Start early enough to load metadata/feed; the engine enforces 09:15.
        # Keep supervising after close to recover/manage pending observed exits.
        if not healthy and (now.weekday()<5 and now.strftime('%H:%M')>='09:10'):
            import socket
            with socket.socket() as probe:
                occupied=probe.connect_ex(('127.0.0.1',8080))==0
            if not occupied and (child is None or child.poll() is not None):
                child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8080','--no-access-log'],
                    cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        time.sleep(2)

if __name__=='__main__': main()
