from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL is required')

    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    return _pool


async def create_document(
    title: str,
    course: str | None,
    status: str,
    total_pages: int,
    storage_path: str,
    subreddits: list[str] | None,
) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (title, course, status, total_pages, storage_path, subreddits)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id::text
            """,
            title,
            course,
            status,
            total_pages,
            storage_path,
            subreddits,
        )
    return row['id']


async def update_document_status(
    document_id: str,
    status: str,
    total_pages: int | None = None,
    has_scan_warning: bool | None = None,
    error_message: str | None = None,
    storage_path: str | None = None,
) -> None:
    updates: list[str] = ['status = $2']
    params: list[Any] = [document_id, status]
    idx = 3
    if total_pages is not None:
        updates.append(f'total_pages = ${idx}')
        params.append(total_pages)
        idx += 1
    if has_scan_warning is not None:
        updates.append(f'has_scan_warning = ${idx}')
        params.append(has_scan_warning)
        idx += 1
    if error_message is not None:
        updates.append(f'error_message = ${idx}')
        params.append(error_message)
        idx += 1
    if storage_path is not None:
        updates.append(f'storage_path = ${idx}')
        params.append(storage_path)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE documents SET {', '.join(updates)} WHERE id = $1::uuid",
            *params,
        )


async def get_document(document_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, title, course, status, total_pages, storage_path,
                   uploaded_at, subreddits, has_scan_warning, error_message
            FROM documents
            WHERE id = $1::uuid
            """,
            document_id,
        )
    if not row:
        return None
    return dict(row)


async def list_documents(course: str | None = None) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if course:
            rows = await conn.fetch(
                """
                SELECT id::text, title, course, status, total_pages, storage_path,
                       uploaded_at, subreddits, has_scan_warning, error_message
                FROM documents
                WHERE course = $1
                ORDER BY uploaded_at DESC
                """,
                course,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id::text, title, course, status, total_pages, storage_path,
                       uploaded_at, subreddits, has_scan_warning, error_message
                FROM documents
                ORDER BY uploaded_at DESC
                """
            )
    return [dict(r) for r in rows]


async def delete_document(document_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM documents WHERE id = $1::uuid', document_id)


async def replace_document_content(
    document_id: str,
    chunks: list[dict],
    sentences: list[dict],
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM document_chunks WHERE document_id = $1::uuid', document_id)
            await conn.execute('DELETE FROM document_sentences WHERE document_id = $1::uuid', document_id)

            for sentence in sentences:
                await conn.execute(
                    """
                    INSERT INTO document_sentences (document_id, page_number, sentence_idx, text)
                    VALUES ($1::uuid, $2, $3, $4)
                    """,
                    document_id,
                    sentence['page_number'],
                    sentence['sentence_idx'],
                    sentence['text'],
                )

            for chunk in chunks:
                embedding_str = '[' + ','.join(str(x) for x in chunk['embedding']) + ']'
                await conn.execute(
                    """
                    INSERT INTO document_chunks (
                        document_id,
                        page_number,
                        sentence_start_idx,
                        sentence_end_idx,
                        text,
                        embedding,
                        bbox
                    )
                    VALUES ($1::uuid, $2, $3, $4, $5, $6::vector, $7::jsonb)
                    """,
                    document_id,
                    chunk['page_number'],
                    chunk['sentence_start_idx'],
                    chunk['sentence_end_idx'],
                    chunk['text'],
                    embedding_str,
                    json.dumps(chunk.get('bbox')) if chunk.get('bbox') is not None else None,
                )


async def get_scope_document_ids(scope: dict | None) -> list[str]:
    scope = scope or {'type': 'library'}
    scope_type = scope.get('type', 'library')

    pool = await get_pool()
    async with pool.acquire() as conn:
        if scope_type == 'document':
            document_id = scope.get('document_id')
            if not document_id:
                return []
            row = await conn.fetchrow('SELECT id::text FROM documents WHERE id = $1::uuid AND status = $2', document_id, 'ready')
            return [row['id']] if row else []

        if scope_type == 'course':
            course = scope.get('course')
            if not course:
                return []
            rows = await conn.fetch(
                'SELECT id::text FROM documents WHERE course = $1 AND status = $2 ORDER BY uploaded_at DESC',
                course,
                'ready',
            )
            return [r['id'] for r in rows]

        rows = await conn.fetch('SELECT id::text FROM documents WHERE status = $1 ORDER BY uploaded_at DESC', 'ready')
        return [r['id'] for r in rows]


async def retrieve_similar_chunks(query_embedding: list[float], document_ids: list[str], limit: int = 12) -> list[dict]:
    if not document_ids:
        return []
    embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.document_id::text AS document_id,
                d.title AS document_title,
                d.course,
                c.page_number,
                c.sentence_start_idx,
                c.sentence_end_idx,
                c.text,
                c.bbox,
                1 - (c.embedding <=> $1::vector) AS similarity
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = ANY($2::uuid[])
            ORDER BY c.embedding <=> $1::vector
            LIMIT $3
            """,
            embedding_str,
            document_ids,
            limit,
        )
    return [dict(r) for r in rows]


async def get_sentence(document_id: str, page_number: int, sentence_idx: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT text
            FROM document_sentences
            WHERE document_id = $1::uuid AND page_number = $2 AND sentence_idx = $3
            """,
            document_id,
            page_number,
            sentence_idx,
        )
    return row['text'] if row else None


async def get_scope_subreddits(document_ids: list[str]) -> list[str]:
    if not document_ids:
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT unnest(subreddits) AS subreddit
            FROM documents
            WHERE id = ANY($1::uuid[]) AND subreddits IS NOT NULL
            """,
            document_ids,
        )
    result = [r['subreddit'] for r in rows if r['subreddit']]
    return sorted(set(result))
