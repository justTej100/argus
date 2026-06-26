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
        data={'title': 'Linear Algebra', 'course': 'math'},
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


def test_bulk_delete_removes_documents(authenticated_client):
    for title in ('Book A', 'Book B'):
        upload = authenticated_client.post(
            '/documents',
            files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
            data={'title': title, 'course': 'math'},
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
