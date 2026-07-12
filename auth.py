from __future__ import annotations

"""Session-cookie authentication helpers.

Google OAuth accepts any signed-in Google account. ADMIN_EMAIL (comma-separated)
marks admin users who get unlimited chat and mutation/admin routes.
"""

import os
from time import time

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

COOKIE_NAME = 'argus_session'
MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _signer() -> TimestampSigner:
    """Return the signer used for the session cookie."""
    secret = os.environ.get('SECRET_KEY') or 'dev-argus-secret'
    return TimestampSigner(secret)


def _secure_cookie() -> bool:
    """Return True when cookies should be marked secure in production."""
    return os.environ.get('ENVIRONMENT', '').lower() in {'prod', 'production'}


def _session_payload(email: str) -> str:
    return f'argus:{email}:{int(time())}'


def issue_session_token(email: str) -> str:
    """Return a signed session token for the given email (tests only)."""
    return _signer().sign(_session_payload(email).encode()).decode()


def set_session_cookie(response: Response, email: str) -> None:
    """Set the signed session cookie for an authenticated user."""
    token = issue_session_token(email)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=_secure_cookie(),
        samesite='lax',
        max_age=MAX_AGE_SECONDS,
        path='/',
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie."""
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=_secure_cookie(),
        samesite='lax',
        path='/',
    )


def allowed_emails() -> set[str]:
    """Return admin emails from comma-separated ADMIN_EMAIL."""
    raw = os.environ.get('ADMIN_EMAIL', '')
    emails = {part.strip().lower() for part in raw.split(',') if part.strip()}
    if not emails:
        raise HTTPException(status_code=500, detail='ADMIN_EMAIL is not configured.')
    return emails


def is_admin_email(email: str | None) -> bool:
    """Return True when email is in the ADMIN_EMAIL allowlist."""
    if not email:
        return False
    try:
        return email.strip().lower() in allowed_emails()
    except HTTPException:
        return False


def normalize_login_email(email: str | None) -> str:
    """Accept any non-empty Google email for session creation."""
    if not email or not str(email).strip():
        raise HTTPException(status_code=400, detail='Google account did not provide an email.')
    return str(email).strip()


def verify_admin_email(email: str | None) -> str:
    """Return the email when it is an admin; otherwise raise 403.

    Kept for tests and explicit admin checks; login no longer uses this gate.
    """
    if not email or email.strip().lower() not in allowed_emails():
        raise HTTPException(status_code=403, detail='Email is not authorized.')
    return email.strip()


def session_is_valid(request: Request) -> bool:
    """Check whether the request carries a valid login cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        value = _signer().unsign(token, max_age=MAX_AGE_SECONDS).decode()
    except (BadSignature, SignatureExpired):
        return False
    parts = value.split(':', 2)
    return len(parts) == 3 and parts[0] == 'argus' and bool(parts[1])


def get_session_email(request: Request) -> str | None:
    """Return the authenticated email from the session cookie, if any."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        value = _signer().unsign(token, max_age=MAX_AGE_SECONDS).decode()
    except (BadSignature, SignatureExpired):
        return None
    parts = value.split(':', 2)
    if len(parts) != 3 or parts[0] != 'argus' or not parts[1]:
        return None
    return parts[1]


def require_session(request: Request) -> None:
    """Raise HTTP 401 when the request is not authenticated."""
    if not session_is_valid(request):
        raise HTTPException(status_code=401, detail='Login required.')


def require_admin(request: Request) -> None:
    """Raise 401 if logged out, 403 if logged in but not an admin."""
    require_session(request)
    email = get_session_email(request)
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail='Admin access required.')
