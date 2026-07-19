from __future__ import annotations

"""Guest study rate limits: cooldown between generations + daily cap.

Admins (ADMIN_EMAIL) skip limits. Guests are keyed by lowercased email.
Persists in Postgres `chat_usage` when DATABASE_URL is set; otherwise memory.
"""

import os
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException

_memory_usage: dict[str, dict[str, Any]] = {}


def guest_cooldown_seconds() -> int:
    raw = (
        os.environ.get('GUEST_STUDY_COOLDOWN_SECONDS')
        or os.environ.get('GUEST_CHAT_COOLDOWN_SECONDS', '300')
    ).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 300


def guest_daily_limit() -> int:
    raw = (
        os.environ.get('GUEST_STUDY_DAILY_LIMIT')
        or os.environ.get('GUEST_CHAT_DAILY_LIMIT', '10')
    ).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 10


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def get_study_usage(email: str) -> dict[str, Any]:
    """Return usage row for email (normalized)."""
    key = email.strip().lower()
    today = _today_utc()

    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        row = _memory_usage.get(key)
        if not row:
            return {'email': key, 'last_chat_at': None, 'day_date': today, 'day_count': 0}
        day_date = row.get('day_date') or today
        day_count = int(row.get('day_count') or 0)
        if day_date != today:
            day_date = today
            day_count = 0
        return {
            'email': key,
            'last_chat_at': row.get('last_chat_at'),
            'day_date': day_date,
            'day_count': day_count,
        }

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT email, last_chat_at, day_date, day_count
            FROM chat_usage
            WHERE email = $1
            """,
            key,
        )
    if not row:
        return {'email': key, 'last_chat_at': None, 'day_date': today, 'day_count': 0}
    day_date = row['day_date'] or today
    day_count = int(row['day_count'] or 0)
    if day_date != today:
        day_date = today
        day_count = 0
    return {
        'email': key,
        'last_chat_at': row['last_chat_at'],
        'day_date': day_date,
        'day_count': day_count,
    }


async def _save_usage(email: str, last_chat_at: datetime, day_date: date, day_count: int) -> None:
    key = email.strip().lower()
    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        _memory_usage[key] = {
            'last_chat_at': last_chat_at,
            'day_date': day_date,
            'day_count': day_count,
        }
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_usage (email, last_chat_at, day_date, day_count)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO UPDATE SET
                last_chat_at = EXCLUDED.last_chat_at,
                day_date = EXCLUDED.day_date,
                day_count = EXCLUDED.day_count
            """,
            key,
            last_chat_at,
            day_date,
            day_count,
        )


def usage_status(usage: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    """Public study quota snapshot for GET /me."""
    cooldown = guest_cooldown_seconds()
    daily_limit = guest_daily_limit()
    if is_admin:
        return {
            'cooldown_seconds': cooldown,
            'daily_limit': daily_limit,
            'remaining_today': None,
            'retry_after_seconds': 0,
            'unlimited': True,
        }

    today = _today_utc()
    day_count = int(usage.get('day_count') or 0)
    if usage.get('day_date') != today:
        day_count = 0
    remaining = max(0, daily_limit - day_count)

    retry_after = 0
    last = usage.get('last_chat_at')
    if last is not None and cooldown > 0:
        if getattr(last, 'tzinfo', None) is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (_now_utc() - last).total_seconds()
        if elapsed < cooldown:
            retry_after = int(cooldown - elapsed) + 1

    return {
        'cooldown_seconds': cooldown,
        'daily_limit': daily_limit,
        'remaining_today': remaining,
        'retry_after_seconds': retry_after,
        'unlimited': False,
    }


async def check_and_record_study(email: str, *, is_admin: bool) -> None:
    """Allow admins; enforce guest cooldown + daily cap; record a successful attempt."""
    if is_admin:
        return

    if not email:
        raise HTTPException(status_code=401, detail='Login required.')

    cooldown = guest_cooldown_seconds()
    daily_limit = guest_daily_limit()
    usage = await get_study_usage(email)
    today = _today_utc()
    day_count = int(usage.get('day_count') or 0)
    if usage.get('day_date') != today:
        day_count = 0

    last = usage.get('last_chat_at')
    if last is not None and cooldown > 0:
        if getattr(last, 'tzinfo', None) is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (_now_utc() - last).total_seconds()
        if elapsed < cooldown:
            retry_after = int(cooldown - elapsed) + 1
            remaining = max(0, daily_limit - day_count)
            raise HTTPException(
                status_code=429,
                detail={
                    'message': (
                        f'Guest study limited to one generation every {cooldown // 60 or 1} minute(s). '
                        f'Try again in {retry_after}s.'
                    ),
                    'retry_after_seconds': retry_after,
                    'remaining_today': remaining,
                },
            )

    if day_count >= daily_limit:
        raise HTTPException(
            status_code=429,
            detail={
                'message': (
                    f'Guest daily study limit reached ({daily_limit}/day). '
                    'Come back tomorrow or use an admin account.'
                ),
                'retry_after_seconds': 0,
                'remaining_today': 0,
            },
        )

    now = _now_utc()
    await _save_usage(email, now, today, day_count + 1)


def reset_memory_usage() -> None:
    """Clear in-memory usage (tests)."""
    _memory_usage.clear()
