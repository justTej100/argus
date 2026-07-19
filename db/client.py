from __future__ import annotations

"""Async Postgres helpers for the `documents` table (metadata only).

Vector chunks live in `argus_vectors` (managed by ai.vector_store).
When DATABASE_URL is unset or unreachable, uses an in-memory dict.
"""

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_failed = False
_memory_documents: dict[str, dict[str, Any]] = {}


async def get_pool() -> asyncpg.Pool | None:
    """Create or return the shared asyncpg pool, or None when DB is absent/unreachable."""
    global _pool, _pool_failed
    if _pool is not None:
        return _pool
    if _pool_failed:
        return None

    database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not database_url:
        return None

    try:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
        return _pool
    except Exception as exc:
        _pool_failed = True
        logger.error(
            'Postgres unavailable (%s). Falling back to in-memory store. '
            'Check DATABASE_URL, wake a paused Supabase project, or copy a fresh URI from '
            'Dashboard → Project Settings → Database.',
            exc,
        )
        return None


async def init_schema() -> None:
    """Apply db/schema.sql on startup when DATABASE_URL is configured."""
    pool = await get_pool()
    if pool is None:
        return
    schema_path = Path(__file__).with_name('schema.sql')
    sql = schema_path.read_text(encoding='utf-8')
    try:
        async with pool.acquire() as conn:
            await conn.execute(sql)
    except Exception as exc:
        logger.error('init_schema failed: %s', exc)


def _blank_doc(
    document_id: str,
    title: str,
    description: str | None,
    status: str,
    total_pages: int,
    storage_path: str,
) -> dict[str, Any]:
    return {
        'id': document_id,
        'title': title,
        'description': description,
        'status': status,
        'total_pages': total_pages,
        'storage_path': storage_path,
        'uploaded_at': time.time(),
        'has_scan_warning': False,
        'error_message': None,
        'flashcards_open': False,
        'embed_total': 0,
        'embed_done': 0,
        'embed_resume_at': None,
        'chunks_skipped': 0,
    }


async def create_document(
    title: str,
    description: str | None,
    status: str,
    total_pages: int,
    storage_path: str,
) -> str:
    """Insert one document row and return its UUID as text."""
    pool = await get_pool()
    if pool is None:
        document_id = str(uuid.uuid4())
        _memory_documents[document_id] = _blank_doc(
            document_id, title, description, status, total_pages, storage_path
        )
        return document_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (title, description, status, total_pages, storage_path, subreddits, flashcards_open)
            VALUES ($1, $2, $3, $4, $5, NULL, FALSE)
            RETURNING id::text
            """,
            title,
            description,
            status,
            total_pages,
            storage_path,
        )
    return row['id']


async def update_document_status(
    document_id: str,
    status: str,
    total_pages: int | None = None,
    has_scan_warning: bool | None = None,
    error_message: str | None = None,
    storage_path: str | None = None,
    embed_done: int | None = None,
    embed_total: int | None = None,
    embed_resume_at: Any = None,
    chunks_skipped: int | None = None,
) -> None:
    """Update document status and optional metadata fields."""
    clear_resume = status in {'ready', 'processing', 'embedding', 'error'} and embed_resume_at is None

    pool = await get_pool()
    if pool is None:
        document = _memory_documents.get(document_id)
        if not document:
            return
        document['status'] = status
        if total_pages is not None:
            document['total_pages'] = total_pages
        if has_scan_warning is not None:
            document['has_scan_warning'] = has_scan_warning
        if error_message is not None:
            document['error_message'] = error_message
        if storage_path is not None:
            document['storage_path'] = storage_path
        if embed_done is not None:
            document['embed_done'] = embed_done
        if embed_total is not None:
            document['embed_total'] = embed_total
        if chunks_skipped is not None:
            document['chunks_skipped'] = chunks_skipped
        if clear_resume:
            document['embed_resume_at'] = None
        elif embed_resume_at is not None:
            document['embed_resume_at'] = embed_resume_at
        return

    updates: list[str] = ['status = $2']
    params: list[Any] = [document_id, status]
    idx = 3
    for col, val in (
        ('total_pages', total_pages),
        ('has_scan_warning', has_scan_warning),
        ('error_message', error_message),
        ('storage_path', storage_path),
        ('embed_done', embed_done),
        ('embed_total', embed_total),
        ('chunks_skipped', chunks_skipped),
    ):
        if val is not None:
            updates.append(f'{col} = ${idx}')
            params.append(val)
            idx += 1

    if clear_resume:
        updates.append(f'embed_resume_at = ${idx}')
        params.append(None)
        idx += 1
    elif embed_resume_at is not None:
        updates.append(f'embed_resume_at = ${idx}')
        params.append(embed_resume_at)
        idx += 1

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE documents SET {', '.join(updates)} WHERE id = $1::uuid",
            *params,
        )


_DOC_SELECT = """
    SELECT id::text, title, description, status, total_pages, storage_path,
           uploaded_at, has_scan_warning, error_message, flashcards_open,
           embed_total, embed_done, embed_resume_at, chunks_skipped
    FROM documents
"""


async def get_document(document_id: str) -> dict | None:
    """Fetch one document as a plain dictionary."""
    pool = await get_pool()
    if pool is None:
        return _memory_documents.get(document_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_DOC_SELECT + ' WHERE id = $1::uuid', document_id)
    if not row:
        return None
    return dict(row)


async def list_documents() -> list[dict]:
    """Return documents newest-first."""
    pool = await get_pool()
    if pool is None:
        documents = list(_memory_documents.values())
        return sorted(documents, key=lambda document: document.get('uploaded_at', 0), reverse=True)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_DOC_SELECT + ' ORDER BY uploaded_at DESC')
    return [dict(r) for r in rows]


async def delete_document(document_id: str) -> None:
    """Delete one document and its vectors / sections / feed posts."""
    from ai.vector_store import delete_document_vectors
    from db.feed import delete_posts_for_document
    from db.sections import delete_sections_for_document
    from db.subscriptions import delete_subscriptions_for_document

    await delete_document_vectors(document_id)
    await delete_posts_for_document(document_id)
    await delete_sections_for_document(document_id)
    await delete_subscriptions_for_document(document_id)
    pool = await get_pool()
    if pool is None:
        _memory_documents.pop(document_id, None)
        return
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM documents WHERE id = $1::uuid', document_id)


async def get_scope_document_ids(scope: dict | None) -> list[str]:
    """Resolve a scope object into the document IDs it covers."""
    scope = scope or {'type': 'library'}
    scope_type = scope.get('type', 'library')

    pool = await get_pool()
    if pool is None:
        documents = [document for document in _memory_documents.values() if document.get('status') == 'ready']
        if scope_type == 'document':
            document_id = scope.get('document_id')
            if document_id and document_id in _memory_documents and _memory_documents[document_id].get('status') == 'ready':
                return [document_id]
            return []
        return [document['id'] for document in documents]
    async with pool.acquire() as conn:
        if scope_type == 'document':
            document_id = scope.get('document_id')
            if not document_id:
                return []
            row = await conn.fetchrow(
                'SELECT id::text FROM documents WHERE id = $1::uuid AND status = $2',
                document_id,
                'ready',
            )
            return [row['id']] if row else []

        rows = await conn.fetch(
            'SELECT id::text FROM documents WHERE status = $1 ORDER BY uploaded_at DESC',
            'ready',
        )
        return [r['id'] for r in rows]
