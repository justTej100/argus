from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from auth import allowed_emails, verify_admin_email


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
