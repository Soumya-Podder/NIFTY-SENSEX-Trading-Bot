"""Renew an active Dhan Web token before expiry; secrets stay in project .env."""
import base64
import json
import re
from datetime import datetime, timezone
import requests
from dotenv.main import rewrite
from .config import PROJECT_ENV, current_credentials


def token_expiry(token):
    # The unsigned claim schedules renewal only; Dhan authenticates the request.
    try:
        part=token.split('.')[1]
        payload=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
        return datetime.fromtimestamp(float(payload['exp']),timezone.utc)
    except (ValueError,KeyError,IndexError,TypeError,OverflowError): return None


def renew_project_token(now,*,path=PROJECT_ENV):
    credentials=current_credentials(path)
    client,token=credentials
    expires=token_expiry(token)
    result={'status':'NOT_DUE','checked_at':now.isoformat(),
            'expires_at':expires.isoformat() if expires else None}
    if not client or not token or expires is None: return {**result,'status':'EXPIRY_UNAVAILABLE'}
    remaining=(expires-now).total_seconds()
    if remaining<=0: return {**result,'status':'EXPIRED','reason':'Dhan cannot renew an expired token; a new token is required'}
    if remaining>12*3600: return result
    try:
        response=requests.get('https://api.dhan.co/v2/RenewToken',
            headers={'access-token':token,'dhanClientId':client},timeout=(5,15))
        if response.status_code!=200:
            return {**result,'status':'RENEWAL_FAILED','reason':'Dhan renewal HTTP '+str(response.status_code)}
        payload=response.json()
        new_token=payload.get('accessToken','')
        new_expiry=token_expiry(new_token)
        if not new_expiry or new_expiry<=expires or not re.fullmatch(r'[A-Za-z0-9_.-]+',new_token):
            return {**result,'status':'RENEWAL_FAILED','reason':'Invalid renewal response'}
        if payload.get('dhanClientId',client)!=client:
            return {**result,'status':'RENEWAL_FAILED','reason':'Renewal client identity mismatch'}
        # dotenv writes its temporary file beside .env and replaces it atomically.
        # Preserve every other setting and do not overwrite a user replacement.
        with rewrite(path,encoding='utf-8') as (source,destination):
            if current_credentials(path)!=credentials: raise RuntimeError('Credentials changed during renewal')
            found=False
            for line in source:
                if re.match(r'^\s*(?:export\s+)?DHAN_ACCESS_TOKEN\s*=',line):
                    destination.write("DHAN_ACCESS_TOKEN='"+new_token+"'\n"); found=True
                else: destination.write(line)
            if not found: raise RuntimeError('Project token setting missing')
        return {**result,'status':'RENEWED','expires_at':new_expiry.isoformat()}
    except Exception as exc:
        # Response bodies, headers and exception messages may contain credentials.
        return {**result,'status':'RENEWAL_FAILED','reason':type(exc).__name__}
