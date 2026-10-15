"""Explicit user token replacement. Never generates or renews credentials."""
import json
import re
import threading
from pathlib import Path
import requests
from dotenv.main import rewrite
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from .config import PROJECT_ENV, current_credentials

router = APIRouter()
ACCESS_FILE = Path(__file__).resolve().parents[1] / 'token_access.json'
LOCAL_HOSTS = {'127.0.0.1:5174', 'localhost:5174', '127.0.0.1:8080', 'localhost:8080'}
LOCK = threading.Lock()


def trusted_request(request, *, mutation=False, access_path=ACCESS_FILE):
    # Ignore forwarded client addresses: only a loopback proxy may reach this API.
    if not request.client or request.client.host not in {'127.0.0.1', '::1'}:
        return False
    host = request.headers.get('host', '').lower()
    origin = request.headers.get('origin')
    if host in LOCAL_HOSTS:
        allowed = {'http://' + item for item in LOCAL_HOSTS}
    else:
        try:
            access = json.loads(Path(access_path).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return False
        if not isinstance(access, dict):
            return False
        expected = access.get('hostname', '')
        login = access.get('login', '')
        if not isinstance(expected, str) or not expected.endswith('.ts.net') or host != expected or not isinstance(login, str) or not login:
            return False
        if request.headers.get('tailscale-user-login') != login:
            return False
        allowed = {'https://' + expected}
    return origin in allowed if mutation else origin is None or origin in allowed


def save_user_token(token, *, path=PROJECT_ENV):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{20,4096}', token):
        raise HTTPException(400, 'Enter a valid token without spaces or line breaks.')
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Another token update is in progress.')
    try:
        before = Path(path).read_bytes()
        client, _ = current_credentials(path)
        if not client:
            raise HTTPException(400, 'The project client ID is not configured.')
        try:
            response = requests.get('https://api.dhan.co/v2/profile',
                headers={'access-token': token, 'dhanClientId': client}, timeout=(5, 10))
        except requests.RequestException:
            raise HTTPException(502, 'Dhan could not be reached. Nothing was saved.') from None
        if response.status_code != 200:
            raise HTTPException(400, 'Dhan rejected this token. Nothing was saved.')
        # Compare the whole file so a simultaneous manual edit is not overwritten.
        with rewrite(path, encoding='utf-8') as (source, destination):
            if Path(path).read_bytes() != before:
                raise HTTPException(409, 'The file changed. Please submit again.')
            found = False
            for line in source:
                if re.match(r'^\s*(?:export\s+)?DHAN_ACCESS_TOKEN\s*=', line):
                    destination.write("DHAN_ACCESS_TOKEN='" + token + "'\n")
                    found = True
                else:
                    destination.write(line)
            if not found:
                raise HTTPException(400, 'The project token setting is missing. Nothing was saved.')
        return {'saved': True, 'message': 'Token verified and saved. The bot will reload it automatically.'}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, 'Token update failed. Check the service locally.') from None
    finally:
        LOCK.release()


@router.post('/api/credentials/token')
async def update_token(request: Request):
    if not trusted_request(request, mutation=True):
        raise HTTPException(403, 'Private authenticated access and a trusted browser origin are required.')
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise HTTPException(415, 'JSON required.')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise HTTPException(413, 'Request too large.')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Invalid request.') from None
    if not isinstance(payload, dict) or set(payload) != {'token'}:
        raise HTTPException(400, 'Only a token may be updated.')
    # Do not use model validation errors, which can reflect credential input.
    return await run_in_threadpool(save_user_token, payload['token'])


@router.get('/api/credentials/form', response_class=HTMLResponse)
def token_form(request: Request):
    if not trusted_request(request):
        raise HTTPException(403, 'Private authenticated access is required.')
    import secrets
    nonce = secrets.token_urlsafe(24)
    page = Path(__file__).with_name('token_update.html').read_text(encoding='utf-8').replace('{{nonce}}', nonce)
    return HTMLResponse(page, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
        'Content-Security-Policy': f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"})
