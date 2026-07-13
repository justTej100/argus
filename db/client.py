from __future__ import annotations

"""Async Postgres helpers for the `documents` table (metadata only).

Vector chunks live in `argus_vectors` (managed by ai.langchain_store).
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
        _memory_documents[document_id] = {
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
        }
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
) -> None:
    """Update document status and optional metadata fields."""
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
        return
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
    """Fetch one document as a plain dictionary."""
    pool = await get_pool()
    if pool is None:
        return _memory_documents.get(document_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, title, description, status, total_pages, storage_path,
                   uploaded_at, has_scan_warning, error_message, flashcards_open
            FROM documents
            WHERE id = $1::uuid
            """,
            document_id,
        )
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
        rows = await conn.fetch(
            """
            SELECT id::text, title, description, status, total_pages, storage_path,
                   uploaded_at, has_scan_warning, error_message, flashcards_open
            FROM documents
            ORDER BY uploaded_at DESC
            """
        )
    return [dict(r) for r in rows]


async def delete_document(document_id: str) -> None:
    """Delete one document and its vectors."""
    from ai.langchain_store import delete_document_vectors
    from db.subscriptions import delete_subscriptions_for_document

    await delete_document_vectors(document_id)
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
            row = await conn.fetchrow('SELECT id::text FROM documents WHERE id = $1::uuid AND status = $2', document_id, 'ready')
            return [row['id']] if row else []

        rows = await conn.fetch('SELECT id::text FROM documents WHERE status = $1 ORDER BY uploaded_at DESC', 'ready')
        return [r['id'] for r in rows]
