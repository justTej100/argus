from __future__ import annotations

"""Integration checks for Postgres when DATABASE_URL is configured."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

pytestmark = pytest.mark.asyncio


def _database_url() -> str | None:
    url = os.environ.get('DATABASE_URL', '').strip()
    return url or None


async def test_database_url_connects() -> None:
    database_url = _database_url()
    if database_url is None:
        pytest.skip('DATABASE_URL is not set')

    import asyncpg

    conn = await asyncpg.connect(database_url, timeout=15)
    try:
        assert await conn.fetchval('SELECT 1') == 1
    finally:
        await conn.close()


async def test_init_schema_applies() -> None:
    database_url = _database_url()
    if database_url is None:
        pytest.skip('DATABASE_URL is not set')

    from db.client import init_schema

    await init_schema()
