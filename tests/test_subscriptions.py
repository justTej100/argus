from __future__ import annotations

import pytest

from db.subscriptions import (
    list_flashcard_offers,
    list_subscriber_emails,
    reset_memory_subscriptions,
    set_flashcards_open,
    subscribe,
    unsubscribe,
)


@pytest.fixture(autouse=True)
def _memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('DATABASE_URL', raising=False)
    reset_memory_subscriptions()
    import db.client as client

    client._memory_documents.clear()
    client._pool = None
    client._pool_failed = False


@pytest.mark.asyncio
async def test_subscribe_requires_open_ready_doc() -> None:
    import db.client as client

    doc_id = await client.create_document('Alg', None, 'ready', 10, 'x.pdf')
    with pytest.raises(ValueError, match='not open'):
        await subscribe('guest@example.com', doc_id)

    await set_flashcards_open(doc_id, True)
    await subscribe('guest@example.com', doc_id)
    assert await list_subscriber_emails(doc_id) == ['guest@example.com']

    await unsubscribe('guest@example.com', doc_id)
    assert await list_subscriber_emails(doc_id) == []


@pytest.mark.asyncio
async def test_offers_include_subscription_state() -> None:
    import db.client as client

    doc_id = await client.create_document('Calc', 'limits', 'ready', 5, 'y.pdf')
    await set_flashcards_open(doc_id, True)
    await subscribe('guest@example.com', doc_id)

    offers = await list_flashcard_offers('guest@example.com')
    assert len(offers) == 1
    assert offers[0]['subscribed'] is True
    assert offers[0]['subscriber_count'] == 1

    other = await list_flashcard_offers('other@example.com')
    assert other[0]['subscribed'] is False
