from __future__ import annotations

"""Async Postgres helpers for documents, chunks, and sentence lookups.

This module owns the connection pool plus the small set of queries used by the
app. Keeping the SQL here avoids scattering schema assumptions across the code
base.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None
_memory_documents: dict[str, dict[str, Any]] = {}
_memory_sentences: dict[str, list[dict[str, Any]]] = {}
_memory_chunks: dict[str, list[dict[str, Any]]] = {}


async def get_pool() -> asyncpg.Pool | None:
    """Create or return the shared asyncpg pool, or None when DB is absent."""
    global _pool
    if _pool is not None:
        return _pool

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        return None

    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    return _pool


async def init_schema() -> None:
    """Apply db/schema.sql on startup when DATABASE_URL is configured."""
    pool = await get_pool()
    if pool is None:
        return
    schema_path = Path(__file__).with_name('schema.sql')
    sql = schema_path.read_text(encoding='utf-8')
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def create_document(
    title: str,
    course: str | None,
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
            'course': course,
            'status': status,
            'total_pages': total_pages,
            'storage_path': storage_path,
            'uploaded_at': time.time(),
            'has_scan_warning': False,
            'error_message': None,
        }
        _memory_sentences[document_id] = []
        _memory_chunks[document_id] = []
        return document_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (title, course, status, total_pages, storage_path, subreddits)
            VALUES ($1, $2, $3, $4, $5, NULL)
            RETURNING id::text
            """,
            title,
            course,
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
            SELECT id::text, title, course, status, total_pages, storage_path,
                   uploaded_at, has_scan_warning, error_message
            FROM documents
            WHERE id = $1::uuid
            """,
            document_id,
        )
    if not row:
        return None
    return dict(row)


async def list_documents(course: str | None = None) -> list[dict]:
    """Return documents newest-first, optionally filtered by course."""
    pool = await get_pool()
    if pool is None:
        documents = list(_memory_documents.values())
        if course:
            documents = [document for document in documents if document.get('course') == course]
        return sorted(documents, key=lambda document: document.get('uploaded_at', 0), reverse=True)
    async with pool.acquire() as conn:
        if course:
            rows = await conn.fetch(
                """
                SELECT id::text, title, course, status, total_pages, storage_path,
                       uploaded_at, has_scan_warning, error_message
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
                       uploaded_at, has_scan_warning, error_message
                FROM documents
                ORDER BY uploaded_at DESC
                """
            )
    return [dict(r) for r in rows]


async def delete_document(document_id: str) -> None:
    """Delete one document and its dependent rows."""
    pool = await get_pool()
    if pool is None:
        _memory_documents.pop(document_id, None)
        _memory_sentences.pop(document_id, None)
        _memory_chunks.pop(document_id, None)
        return
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM documents WHERE id = $1::uuid', document_id)


async def replace_document_content(
    document_id: str,
    chunks: list[dict],
    sentences: list[dict],
) -> None:
    """Replace all stored sentences and chunks for a document."""
    pool = await get_pool()
    if pool is None:
        _memory_sentences[document_id] = list(sentences)
        _memory_chunks[document_id] = [{**chunk, 'document_id': document_id} for chunk in chunks]
        return
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
        if scope_type == 'course':
            course = scope.get('course')
            return [document['id'] for document in documents if document.get('course') == course]
        return [document['id'] for document in documents]
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
    """Return the most similar chunk rows for the given document scope."""
    if not document_ids:
        return []
    pool = await get_pool()
    if pool is None:
        chunks = [chunk for document_id in document_ids for chunk in _memory_chunks.get(document_id, [])]
        for chunk in chunks:
            chunk['document_title'] = _memory_documents.get(chunk['document_id'], {}).get('title', '')
            chunk['course'] = _memory_documents.get(chunk['document_id'], {}).get('course')
            chunk['similarity'] = 0.0
        return chunks[:limit]
    embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
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
                1 - (c.embedding::halfvec(3072) <=> $1::halfvec(3072)) AS similarity
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = ANY($2::uuid[])
            ORDER BY c.embedding::halfvec(3072) <=> $1::halfvec(3072)
            LIMIT $3
            """,
            embedding_str,
            document_ids,
            limit,
        )
    return [dict(r) for r in rows]


async def get_sentence(document_id: str, page_number: int, sentence_idx: int) -> str | None:
    """Look up the exact stored sentence at a page/sentence address."""
    pool = await get_pool()
    if pool is None:
        for sentence in _memory_sentences.get(document_id, []):
            if sentence.get('page_number') == page_number and sentence.get('sentence_idx') == sentence_idx:
                return sentence.get('text')
        return None
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
