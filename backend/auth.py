from __future__ import annotations

import os
from time import time

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

COOKIE_NAME = 'argus_session'
MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _signer() -> TimestampSigner:
    secret = os.environ.get('APP_PASSWORD') or os.environ.get('SECRET_KEY') or 'dev-argus-secret'
    return TimestampSigner(secret)


def _secure_cookie() -> bool:
    return os.environ.get('ENVIRONMENT', '').lower() in {'prod', 'production'}


def login_response(password: str, response: Response) -> dict:
    expected = os.environ.get('APP_PASSWORD')
    if not expected:
        raise HTTPException(status_code=500, detail='APP_PASSWORD is not configured.')
    if password != expected:
        raise HTTPException(status_code=401, detail='Invalid password.')
    token = _signer().sign(f'argus:{int(time())}'.encode()).decode()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=_secure_cookie(),
        samesite='lax',
        max_age=MAX_AGE_SECONDS,
    )
    return {'ok': True}


def session_is_valid(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        value = _signer().unsign(token, max_age=MAX_AGE_SECONDS).decode()
    except (BadSignature, SignatureExpired):
        return False
    return value.startswith('argus:')


def require_session(request: Request) -> None:
    if not session_is_valid(request):
        raise HTTPException(status_code=401, detail='Login required.')
