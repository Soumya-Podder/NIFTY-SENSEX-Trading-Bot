import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.token_update import save_user_token, trusted_request, token_form


def request(host='127.0.0.1:5174', origin='http://127.0.0.1:5174', login=None, peer='127.0.0.1'):
    headers=[(b'host',host.encode())]
    if origin: headers.append((b'origin',origin.encode()))
    if login: headers.append((b'tailscale-user-login',login.encode()))
    return Request({'type':'http','method':'GET','path':'/','headers':headers,'client':(peer,1234),'scheme':'http','server':('127.0.0.1',8080),'query_string':b''})


@pytest.mark.parametrize('host,origin,peer,allowed',[
    ('127.0.0.1:5174','http://127.0.0.1:5174','127.0.0.1',True),
    ('evil.example','http://evil.example','127.0.0.1',False),
    ('127.0.0.1:5174','http://evil.example','127.0.0.1',False),
    ('127.0.0.1:5174',None,'127.0.0.1',False),
    ('127.0.0.1:5174','http://127.0.0.1:5174','192.168.1.2',False)])
def test_local_origin_and_peer_required(host,origin,peer,allowed):
    assert trusted_request(request(host,origin,peer=peer),mutation=True)==allowed


def test_remote_requires_configured_identity_https_and_host(tmp_path):
    path=tmp_path/'access.json';path.write_text(json.dumps({'hostname':'bot.example.ts.net','login':'owner@example.com'}))
    good=request('bot.example.ts.net','https://bot.example.ts.net','owner@example.com')
    assert trusted_request(good,mutation=True,access_path=path)
    for bad in [request('bot.example.ts.net','https://bot.example.ts.net'),request('bot.example.ts.net','http://bot.example.ts.net','owner@example.com'),request('other.example.ts.net','https://other.example.ts.net','owner@example.com')]:
        assert not trusted_request(bad,mutation=True,access_path=path)
    assert not trusted_request(good,mutation=True,access_path=tmp_path/'missing')


@pytest.mark.parametrize('kind',['valid','rejected','edited','malformed'])
def test_only_explicit_validated_token_is_saved(tmp_path,monkeypatch,kind):
    path=tmp_path/'.env';original='DHAN_CLIENT_ID=123\nDHAN_ACCESS_TOKEN=old\nPAPER_ONLY=true\n'
    path.write_text(original);new='new.token.'+'x'*25
    def profile(*args,**kwargs):
        assert kwargs['headers']['access-token']==new
        if kind=='edited':path.write_text(original+'# user edit\n')
        return SimpleNamespace(status_code=400 if kind=='rejected' else 200)
    monkeypatch.setattr('app.token_update.requests.get',profile)
    if kind=='valid':
        assert save_user_token(new,path=path)['saved']
        assert 'PAPER_ONLY=true' in path.read_text() and new in path.read_text()
    else:
        with pytest.raises(HTTPException) as exc:save_user_token(new+'\n' if kind=='malformed' else new,path=path)
        assert new not in str(exc.value.detail)
        assert path.read_text()==original+('# user edit\n' if kind=='edited' else '')


def test_form_has_no_cache_and_never_prefills_secret():
    response=token_form(request(origin=None))
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-frame-options']=='DENY'
    assert b'type="password"' in response.body and b'localStorage' not in response.body
