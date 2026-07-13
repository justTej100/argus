from __future__ import annotations

"""Flashcard signup: guests subscribe to admin-opened textbooks."""

import time
from typing import Any

from db.client import get_document, get_pool, list_documents

_memory_subscriptions: set[tuple[str, str]] = set()


def reset_memory_subscriptions() -> None:
    """Clear in-memory subscriptions (tests)."""
    _memory_subscriptions.clear()


async def set_flashcards_open(document_id: str, enabled: bool) -> dict | None:
    """Toggle whether guests may subscribe to flashcards for this document."""
    pool = await get_pool()
    if pool is None:
        doc = await get_document(document_id)
        if not doc:
            return None
        doc['flashcards_open'] = bool(enabled)
        return dict(doc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE documents
            SET flashcards_open = $2
            WHERE id = $1::uuid
            RETURNING id::text, title, description, status, total_pages, storage_path,
                      uploaded_at, has_scan_warning, error_message, flashcards_open
            """,
            document_id,
            enabled,
        )
    return dict(row) if row else None


async def subscribe(email: str, document_id: str) -> None:
    """Subscribe an email to flashcards for an open, ready document."""
    key = email.strip().lower()
    doc = await get_document(document_id)
    if not doc:
        raise ValueError('Document not found.')
    if doc.get('status') != 'ready':
        raise ValueError('Textbook is not ready yet.')
    if not doc.get('flashcards_open'):
        raise ValueError('Flashcard signup is not open for this textbook.')

    pool = await get_pool()
    if pool is None:
        _memory_subscriptions.add((key, document_id))
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO flashcard_subscriptions (email, document_id)
            VALUES ($1, $2::uuid)
            ON CONFLICT (email, document_id) DO NOTHING
            """,
            key,
            document_id,
        )


async def unsubscribe(email: str, document_id: str) -> None:
    """Remove a flashcard subscription."""
    key = email.strip().lower()
    pool = await get_pool()
    if pool is None:
        _memory_subscriptions.discard((key, document_id))
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM flashcard_subscriptions
            WHERE email = $1 AND document_id = $2::uuid
            """,
            key,
            document_id,
        )


async def list_subscriber_emails(document_id: str) -> list[str]:
    """Emails subscribed to a document."""
    pool = await get_pool()
    if pool is None:
        return sorted(email for email, doc_id in _memory_subscriptions if doc_id == document_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT email FROM flashcard_subscriptions
            WHERE document_id = $1::uuid
            ORDER BY email
            """,
            document_id,
        )
    return [r['email'] for r in rows]


async def is_subscribed(email: str, document_id: str) -> bool:
    key = email.strip().lower()
    pool = await get_pool()
    if pool is None:
        return (key, document_id) in _memory_subscriptions
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM flashcard_subscriptions
            WHERE email = $1 AND document_id = $2::uuid
            """,
            key,
            document_id,
        )
    return row is not None


async def list_flashcard_offers(email: str | None) -> list[dict[str, Any]]:
    """Ready textbooks open for signup, with subscription state for the viewer."""
    docs = await list_documents()
    offers: list[dict[str, Any]] = []
    for doc in docs:
        if doc.get('status') != 'ready' or not doc.get('flashcards_open'):
            continue
        subscribers = await list_subscriber_emails(doc['id'])
        subscribed = bool(email and email.strip().lower() in {s.lower() for s in subscribers})
        offers.append(
            {
                'document_id': doc['id'],
                'title': doc['title'],
                'description': doc.get('description'),
                'subscribed': subscribed,
                'subscriber_count': len(subscribers),
            }
        )
    return offers


async def delete_subscriptions_for_document(document_id: str) -> None:
    """Clean memory subscriptions when a document is deleted."""
    global _memory_subscriptions
    _memory_subscriptions = {(e, d) for e, d in _memory_subscriptions if d != document_id}
