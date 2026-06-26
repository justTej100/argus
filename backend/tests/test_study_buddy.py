from __future__ import annotations


def test_login_success_and_failure(client):
    bad = client.post('/auth/login', json={'password': 'wrong'})
    assert bad.status_code == 401

    good = client.post('/auth/login', json={'password': 'test-password'})
    assert good.status_code == 200
    assert good.json()['ok'] is True
    assert 'argus_session' in good.cookies


def test_chat_requires_session(client):
    response = client.post(
        '/chat',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'provider': 'deepseek',
            'mode': 'chat',
            'scope': {'type': 'library'},
        },
    )
    assert response.status_code == 401


def test_upload_enqueues_and_status_polling(client):
    login = client.post('/auth/login', json={'password': 'test-password'})
    assert login.status_code == 200

    upload = client.post(
        '/documents',
        files={'file': ('book.pdf', b'%PDF-1.4 test', 'application/pdf')},
        data={'title': 'Linear Algebra', 'course': 'math', 'subreddits': 'math,learnmath'},
    )
    assert upload.status_code == 200
    payload = upload.json()
    assert payload['status'] == 'processing'
    assert payload['job_id'].startswith('job-')

    document_id = payload['id']

    first = client.get(f'/documents/{document_id}/status')
    assert first.status_code == 200
    assert first.json()['status'] == 'processing'

    store = client.state_store  # type: ignore[attr-defined]
    store[document_id]['status'] = 'ready'

    second = client.get(f'/documents/{document_id}/status')
    assert second.status_code == 200
    assert second.json()['status'] == 'ready'
