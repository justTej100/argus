from __future__ import annotations

"""Feed accounts (personas) and posts."""

import uuid
from datetime import datetime, timezone
from typing import Any

from db.client import get_pool

_memory_accounts: dict[str, dict[str, Any]] = {}
_memory_posts: list[dict[str, Any]] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_account(
    *,
    handle: str,
    display_name: str,
    bio: str = '',
    kind: str = 'textbook',
    document_id: str | None = None,
    topic: str | None = None,
    avatar_key: str = '',
) -> dict[str, Any]:
    handle = handle.strip().lstrip('@').lower()
    pool = await get_pool()
    if pool is None:
        existing = next((a for a in _memory_accounts.values() if a['handle'] == handle), None)
        if existing:
            existing.update(
                {
                    'display_name': display_name,
                    'bio': bio,
                    'kind': kind,
                    'document_id': document_id,
                    'topic': topic,
                    'avatar_key': avatar_key or existing.get('avatar_key') or handle[:2].upper(),
                }
            )
            return dict(existing)
        row = {
            'id': str(uuid.uuid4()),
            'handle': handle,
            'display_name': display_name,
            'bio': bio,
            'kind': kind,
            'document_id': document_id,
            'topic': topic,
            'avatar_key': avatar_key or handle[:2].upper(),
            'created_at': _now(),
        }
        _memory_accounts[row['id']] = row
        return dict(row)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO accounts (handle, display_name, bio, kind, document_id, topic, avatar_key)
            VALUES ($1, $2, $3, $4, $5::uuid, $6, $7)
            ON CONFLICT (handle) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                bio = EXCLUDED.bio,
                kind = EXCLUDED.kind,
                document_id = EXCLUDED.document_id,
                topic = EXCLUDED.topic,
                avatar_key = COALESCE(NULLIF(EXCLUDED.avatar_key, ''), accounts.avatar_key)
            RETURNING id::text, handle, display_name, bio, kind, document_id::text, topic, avatar_key, created_at
            """,
            handle,
            display_name,
            bio,
            kind,
            document_id,
            topic,
            avatar_key or handle[:2].upper(),
        )
    return dict(row)


async def create_post(
    *,
    account_id: str,
    body: str,
    document_id: str | None = None,
    page_number: int | None = None,
    leetcode_url: str | None = None,
) -> dict[str, Any]:
    pool = await get_pool()
    if pool is None:
        row = {
            'id': str(uuid.uuid4()),
            'account_id': account_id,
            'body': body,
            'document_id': document_id,
            'page_number': page_number,
            'leetcode_url': leetcode_url,
            'created_at': _now(),
        }
        _memory_posts.append(row)
        return dict(row)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO posts (account_id, body, document_id, page_number, leetcode_url)
            VALUES ($1::uuid, $2, $3::uuid, $4, $5)
            RETURNING id::text, account_id::text, body, document_id::text, page_number, leetcode_url, created_at
            """,
            account_id,
            body,
            document_id,
            page_number,
            leetcode_url,
        )
    return dict(row)


async def delete_posts_for_document(document_id: str) -> None:
    pool = await get_pool()
    if pool is None:
        global _memory_posts
        _memory_posts = [p for p in _memory_posts if p.get('document_id') != document_id]
        # Remove textbook accounts for this doc with no remaining posts
        remove_ids = [
            aid
            for aid, a in _memory_accounts.items()
            if a.get('document_id') == document_id
            and not any(p.get('account_id') == aid for p in _memory_posts)
        ]
        for aid in remove_ids:
            _memory_accounts.pop(aid, None)
        return
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM posts WHERE document_id = $1::uuid', document_id)
        await conn.execute(
            "DELETE FROM accounts WHERE document_id = $1::uuid AND kind = 'textbook'",
            document_id,
        )


async def list_feed(*, limit: int = 40, cursor: str | None = None) -> list[dict[str, Any]]:
    """Return posts newest-first with nested account."""
    limit = max(1, min(limit, 80))
    pool = await get_pool()
    if pool is None:
        posts = sorted(_memory_posts, key=lambda p: p.get('created_at') or _now(), reverse=True)
        if cursor:
            posts = [p for p in posts if str(p['id']) < cursor]
        out = []
        for p in posts[:limit]:
            acc = _memory_accounts.get(p['account_id'], {})
            out.append({**p, 'account': acc})
        return out

    async with pool.acquire() as conn:
        if cursor:
            rows = await conn.fetch(
                """
                SELECT p.id::text, p.account_id::text, p.body, p.document_id::text, p.page_number,
                       p.leetcode_url, p.created_at,
                       a.handle, a.display_name, a.bio, a.kind, a.avatar_key, a.topic
                FROM posts p
                JOIN accounts a ON a.id = p.account_id
                WHERE p.created_at < (SELECT created_at FROM posts WHERE id = $1::uuid)
                ORDER BY p.created_at DESC
                LIMIT $2
                """,
                cursor,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.id::text, p.account_id::text, p.body, p.document_id::text, p.page_number,
                       p.leetcode_url, p.created_at,
                       a.handle, a.display_name, a.bio, a.kind, a.avatar_key, a.topic
                FROM posts p
                JOIN accounts a ON a.id = p.account_id
                ORDER BY p.created_at DESC
                LIMIT $1
                """,
                limit,
            )
    return [
        {
            'id': r['id'],
            'account_id': r['account_id'],
            'body': r['body'],
            'document_id': r['document_id'],
            'page_number': r['page_number'],
            'leetcode_url': r['leetcode_url'],
            'created_at': r['created_at'],
            'account': {
                'handle': r['handle'],
                'display_name': r['display_name'],
                'bio': r['bio'],
                'kind': r['kind'],
                'avatar_key': r['avatar_key'],
                'topic': r['topic'],
            },
        }
        for r in rows
    ]


async def count_posts() -> int:
    pool = await get_pool()
    if pool is None:
        return len(_memory_posts)
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT COUNT(*)::int AS n FROM posts')
    return int(row['n']) if row else 0
