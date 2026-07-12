from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth import allowed_emails, is_admin_email, normalize_login_email, verify_admin_email


@pytest.fixture(autouse=True)
def admin_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_EMAIL', 'alice@example.com,bob@example.com')


def test_allowed_emails_parses_comma_separated_list() -> None:
    assert allowed_emails() == {'alice@example.com', 'bob@example.com'}


def test_verify_admin_email_accepts_any_allowed_address() -> None:
    assert verify_admin_email('alice@example.com') == 'alice@example.com'
    assert verify_admin_email('Bob@Example.com') == 'Bob@Example.com'


def test_verify_admin_email_rejects_unknown_address() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_admin_email('stranger@example.com')
    assert exc.value.status_code == 403


def test_is_admin_email() -> None:
    assert is_admin_email('alice@example.com') is True
    assert is_admin_email('stranger@example.com') is False


def test_normalize_login_email_accepts_any_address() -> None:
    assert normalize_login_email('guest@gmail.com') == 'guest@gmail.com'


def test_normalize_login_email_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        normalize_login_email(None)
    assert exc.value.status_code == 400
