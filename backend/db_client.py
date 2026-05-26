"""
Database client — async Postgres via asyncpg + pgvector.

Usage:
    from db.client import get_db, save_search, save_items

    async with get_db() as conn:
        await save_search(conn, ...)
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL not set — add it to your .env")
        _pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    return _pool


@asynccontextmanager
async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

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
    """Insert a search record, return the search UUID."""
    row = await conn.fetchrow(
        """
        INSERT INTO searches
            (query, query_type, provider, brief, grounding_score,
             sources_hit, items_retrieved, duration_ms)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING id::text
        """,
        query, query_type, provider, brief, grounding_score,
        sources_hit, items_retrieved, duration_ms,
    )
    return row["id"]


async def save_items(
    conn: asyncpg.Connection,
    search_id: str,
    items: list,
) -> None:
    """Bulk insert SourceItems with their embeddings."""
    for item in items:
        embedding_str = None
        if item.embedding:
            # pgvector expects a string like "[0.1, 0.2, ...]"
            embedding_str = "[" + ",".join(str(x) for x in item.embedding) + "]"

        await conn.execute(
            """
            INSERT INTO source_items
                (search_id, item_id, source, title, body, url,
                 author, container, published_at, engagement, metadata, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::vector)
            ON CONFLICT DO NOTHING
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
    await conn.execute(
        """
        INSERT INTO eval_results
            (search_id, passed, score, claims_checked,
             claims_grounded, ungrounded_claims, explanation)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
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
    Find the most semantically similar stored items to a query embedding.
    This is pgvector doing the heavy lifting — cosine distance search.
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    return await conn.fetch(
        """
        SELECT source, title, url, body, engagement,
               1 - (embedding <=> $1::vector) AS similarity
        FROM source_items
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        embedding_str, limit,
    )