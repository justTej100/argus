from __future__ import annotations

import pytest

from rate_limit import check_and_record_study, reset_memory_usage


@pytest.fixture(autouse=True)
def _limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('GUEST_STUDY_COOLDOWN_SECONDS', '300')
    monkeypatch.setenv('GUEST_STUDY_DAILY_LIMIT', '10')
    reset_memory_usage()
    import db.client as db_client

    db_client._pool = None
    db_client._pool_failed = False


@pytest.mark.asyncio
async def test_admin_skips_rate_limit() -> None:
    await check_and_record_study('admin@test.com', is_admin=True)
    await check_and_record_study('admin@test.com', is_admin=True)


@pytest.mark.asyncio
async def test_guest_second_study_within_cooldown_raises_429() -> None:
    from fastapi import HTTPException

    await check_and_record_study('guest@test.com', is_admin=False)
    with pytest.raises(HTTPException) as exc:
        await check_and_record_study('guest@test.com', is_admin=False)
    assert exc.value.status_code == 429
    assert exc.value.detail['retry_after_seconds'] > 0


@pytest.mark.asyncio
async def test_guest_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    monkeypatch.setenv('GUEST_STUDY_COOLDOWN_SECONDS', '0')
    monkeypatch.setenv('GUEST_STUDY_DAILY_LIMIT', '2')
    reset_memory_usage()

    await check_and_record_study('guest2@test.com', is_admin=False)
    await check_and_record_study('guest2@test.com', is_admin=False)
    with pytest.raises(HTTPException) as exc:
        await check_and_record_study('guest2@test.com', is_admin=False)
    assert exc.value.status_code == 429
    assert exc.value.detail['remaining_today'] == 0
