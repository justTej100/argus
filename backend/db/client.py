"""
Database client — async Postgres via asyncpg + pgvector.

All functions gracefully no-op when DATABASE_URL is not set, so the app
works in full without a database. Postgres is only needed for:
  - Persisting searches and source items across restarts.
  - Semantic search over past results (POST /search/similar — future feature).

To enable:
  1. Create a Supabase project (free tier) at supabase.com.
  2. Run backend/db/schema.sql against it to create the tables.
  3. Add DATABASE_URL to your .env.

Usage:
    from db.client import get_pool, save_search, save_items, save_eval

    pool = await get_pool()   # returns None if DATABASE_URL is not set
    if pool:
        async with pool.acquire() as conn:
            search_id = await save_search(conn, ...)
"""

from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

# Module-level connection pool — created once, reused across all requests.
# asyncpg pools handle connection reuse and concurrent access automatically.
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool | None:
    """
    Return the shared connection pool, creating it on first call.

    Returns None (instead of raising) when DATABASE_URL is not set,
    so callers can use `if pool:` to skip DB operations gracefully.
    """
    global _pool
    if _pool is not None:
        return _pool

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # No database configured — the app runs fine without it.
        return None

    try:
        # min_size=2: keep 2 connections warm so the first request isn't slow.
        # max_size=10: cap at 10 to avoid overwhelming Supabase's free tier.
        _pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
        return _pool
    except Exception as exc:
        print(f"[db] Could not connect to Postgres: {exc}")
        return None


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------
# Each function takes a live asyncpg Connection (not the pool) so callers
# can wrap multiple saves in a single transaction if needed.

async def save_search(
    conn: asyncpg.Connection,
    query: str,
    query_type: str,
    provider: str,
    brief: str,
    grounding_score: float,
    sources_hit: list[str],
    items_retrieved: int,
    duration_ms: int,
) -> str:
    """
    Insert one search record and return its UUID.

    The UUID is used as a foreign key when saving source_items and eval_results,
    so call this first and pass the returned id to the other save functions.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO searches
            (query, query_type, provider, brief, grounding_score,
             sources_hit, items_retrieved, duration_ms)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id::text
        """,
        query, query_type, provider, brief, grounding_score,
        sources_hit, items_retrieved, duration_ms,
    )
    return row["id"]


async def save_items(
    conn: asyncpg.Connection,
    search_id: str,
    items: list[Any],
) -> None:
    """
    Bulk insert SourceItems with their embedding vectors.

    ON CONFLICT DO NOTHING deduplicates on item_id — the same Reddit post
    scraped in two different searches is only stored once.
    """
    for item in items:
        # pgvector expects the embedding as a string: "[0.1, 0.2, -0.3, ...]"
        embedding_str = None
        if item.embedding:
            embedding_str = "[" + ",".join(str(x) for x in item.embedding) + "]"

        await conn.execute(
            """
            INSERT INTO source_items
                (search_id, item_id, source, title, body, url,
                 author, container, published_at, engagement, metadata, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::vector)
            ON CONFLICT (item_id) DO NOTHING
            """,
            search_id,
            item.item_id,
            item.source,
            item.title,
            item.body,
            item.url,
            item.author,
            item.container,
            item.published_at,
            json.dumps(item.engagement),
            json.dumps(item.metadata),
            embedding_str,
        )


async def save_eval(
    conn: asyncpg.Connection,
    search_id: str,
    passed: bool,
    score: float,
    claims_checked: int,
    claims_grounded: int,
    ungrounded_claims: list[str],
    explanation: str,
) -> None:
    """Insert the EvalAgent grounding check results for a search."""
    await conn.execute(
        """
        INSERT INTO eval_results
            (search_id, passed, score, claims_checked,
             claims_grounded, ungrounded_claims, explanation)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        search_id, passed, score, claims_checked,
        claims_grounded, ungrounded_claims, explanation,
    )


async def semantic_search(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    limit: int = 10,
) -> list[asyncpg.Record]:
    """
    Find stored items whose embeddings are most similar to the query embedding.

    Uses pgvector's <=> operator (cosine distance) with the ivfflat index
    for fast approximate nearest-neighbor search.

    The similarity score returned is 1 - cosine_distance, so:
      1.0 = identical
      0.0 = completely unrelated
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    return await conn.fetch(
        """
        SELECT
            source, title, url, body, engagement,
            1 - (embedding <=> $1::vector) AS similarity
        FROM source_items
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        embedding_str, limit,
    )
