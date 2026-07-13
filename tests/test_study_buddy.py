from __future__ import annotations

"""Smoke tests for the highest-value request paths."""


def test_logout_clears_session(authenticated_client):
    response = authenticated_client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert response.status_code == 200

    logout = authenticated_client.get('/logout', follow_redirects=False)
    assert logout.status_code == 302
    set_cookie = logout.headers.get('set-cookie', '')
    assert 'Max-Age=0' in set_cookie
    # TestClient keeps deleted cookies in its jar unless removed explicitly.
    authenticated_client.cookies.delete('argus_session', path='/')

    blocked = authenticated_client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert blocked.status_code == 401


def test_chat_requires_session(client):
    response = client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert response.status_code == 401


def test_upload_enqueues_and_status_polling(authenticated_client):
    upload = authenticated_client.post(
        '/documents',
        files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
        data={'title': 'Linear Algebra', 'description': 'Intro linear algebra'},
    )
    assert upload.status_code == 200
    payload = upload.json()
    assert payload['status'] == 'processing'
    assert payload['job_id'].startswith('ingest-')

    document_id = payload['id']

    first = authenticated_client.get(f'/documents/{document_id}/status')
    assert first.status_code == 200
    assert first.json()['status'] == 'processing'

    store = authenticated_client.state_store  # type: ignore[attr-defined]
    store[document_id]['status'] = 'ready'

    second = authenticated_client.get(f'/documents/{document_id}/status')
    assert second.status_code == 200
    assert second.json()['status'] == 'ready'


def test_bulk_delete_requires_session(client):
    response = client.post('/documents/bulk-delete', json={'document_ids': ['doc-1']})
    assert response.status_code == 401


def test_guest_upload_forbidden(guest_client):
    upload = guest_client.post(
        '/documents',
        files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
        data={'title': 'Nope'},
    )
    assert upload.status_code == 403


def test_guest_chat_rate_limited(guest_client):
    first = guest_client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert first.status_code == 200

    second = guest_client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'again'}],
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert second.status_code == 429
    detail = second.json()['detail']
    assert detail['retry_after_seconds'] > 0


def test_me_returns_role(client):
    from auth import COOKIE_NAME, issue_session_token

    client.cookies.set(COOKIE_NAME, issue_session_token('admin@test.com'), path='/')
    admin_me = client.get('/me')
    assert admin_me.status_code == 200
    assert admin_me.json()['is_admin'] is True

    client.cookies.set(COOKIE_NAME, issue_session_token('guest@example.com'), path='/')
    guest_me = client.get('/me')
    assert guest_me.status_code == 200
    body = guest_me.json()
    assert body['is_admin'] is False
    assert body['chat']['unlimited'] is False


def test_guest_flashcard_subscribe_flow(client):
    from auth import COOKIE_NAME, issue_session_token

    client.cookies.set(COOKIE_NAME, issue_session_token('admin@test.com'), path='/')
    upload = client.post(
        '/documents',
        files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
        data={'title': 'Linear Algebra'},
    )
    assert upload.status_code == 200
    doc_id = upload.json()['id']
    store = client.state_store  # type: ignore[attr-defined]
    store[doc_id]['status'] = 'ready'
    store[doc_id]['flashcards_open'] = False

    client.cookies.set(COOKIE_NAME, issue_session_token('guest@example.com'), path='/')
    closed = client.post('/flashcards/subscribe', json={'document_id': doc_id})
    assert closed.status_code == 400

    client.cookies.set(COOKIE_NAME, issue_session_token('admin@test.com'), path='/')
    opened = client.patch(
        f'/documents/{doc_id}/flashcards-open',
        json={'enabled': True},
    )
    assert opened.status_code == 200
    assert opened.json()['flashcards_open'] is True

    client.cookies.set(COOKIE_NAME, issue_session_token('guest@example.com'), path='/')
    sub = client.post('/flashcards/subscribe', json={'document_id': doc_id})
    assert sub.status_code == 200

    offers = client.get('/flashcards/offers')
    assert offers.status_code == 200
    assert offers.json()[0]['subscribed'] is True

    unsub = client.post('/flashcards/unsubscribe', json={'document_id': doc_id})
    assert unsub.status_code == 200
    offers2 = client.get('/flashcards/offers')
    assert offers2.json()[0]['subscribed'] is False


def test_guest_cannot_open_flashcard_signup(guest_client):
    response = guest_client.patch(
        '/documents/doc-1/flashcards-open',
        json={'enabled': True},
    )
    assert response.status_code == 403


def test_bulk_delete_removes_documents(authenticated_client):
    for title in ('Book A', 'Book B'):
        upload = authenticated_client.post(
            '/documents',
            files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
            data={'title': title, 'description': 'math'},
        )
        assert upload.status_code == 200

    store = authenticated_client.state_store  # type: ignore[attr-defined]
    doc_ids = list(store.keys())
    assert len(doc_ids) == 2

    bulk = authenticated_client.post('/documents/bulk-delete', json={'document_ids': [doc_ids[0]]})
    assert bulk.status_code == 200
    assert bulk.json()['deleted'] == 1

    remaining = authenticated_client.get('/documents')
    assert remaining.status_code == 200
    docs = remaining.json()
    assert len(docs) == 1
    assert docs[0]['id'] == doc_ids[1]
