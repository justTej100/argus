from __future__ import annotations

"""Pytest fixtures for smoke-testing the study buddy app.

The client fixture imports the FastAPI app, then
monkeypatches storage and database helpers so the tests can focus on request
handling and route behavior without external services.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    os.environ['SECRET_KEY'] = 'test-secret-key'
    os.environ['ADMIN_EMAIL'] = 'admin@test.com'
    os.environ.pop('DATABASE_URL', None)
    os.environ['GUEST_STUDY_COOLDOWN_SECONDS'] = '300'
    os.environ['GUEST_STUDY_DAILY_LIMIT'] = '10'

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from rate_limit import reset_memory_usage

    reset_memory_usage()

    import main  # type: ignore

    # main.load_dotenv() may rehydrate DATABASE_URL from .env — keep tests in-memory.
    os.environ.pop('DATABASE_URL', None)
    import db.client as db_client

    db_client._pool = None
    db_client._pool_failed = False

    state: dict[str, dict] = {}

    async def create_document(title: str, description: str | None, status: str, total_pages: int, storage_path: str) -> str:
        doc_id = f'doc-{len(state) + 1}'
        state[doc_id] = {
            'id': doc_id,
            'title': title,
            'description': description,
            'status': status,
            'total_pages': total_pages,
            'storage_path': storage_path,
            'has_scan_warning': False,
            'error_message': None,
            'flashcards_open': False,
        }
        return doc_id

    async def update_document_status(
        document_id: str,
        status: str,
        total_pages: int | None = None,
        has_scan_warning: bool | None = None,
        error_message: str | None = None,
        storage_path: str | None = None,
    ) -> None:
        doc = state[document_id]
        doc['status'] = status
        if total_pages is not None:
            doc['total_pages'] = total_pages
        if has_scan_warning is not None:
            doc['has_scan_warning'] = has_scan_warning
        if error_message is not None:
            doc['error_message'] = error_message
        if storage_path is not None:
            doc['storage_path'] = storage_path

    async def get_document(document_id: str):
        return state.get(document_id)

    async def list_documents():
        return list(state.values())

    async def delete_document(document_id: str) -> None:
        state.pop(document_id, None)

    def upload_pdf(document_id: str, filename: str, data: bytes) -> str:
        return f'documents/{document_id}/{filename}'

    def schedule_ingestion(document_id: str, storage_path: str) -> str:
        return f'ingest-{document_id}'

    async def set_flashcards_open(document_id: str, enabled: bool):
        doc = state.get(document_id)
        if not doc:
            return None
        doc['flashcards_open'] = bool(enabled)
        return dict(doc)

    monkeypatch.setattr(main, 'create_document', create_document)
    monkeypatch.setattr(main, 'update_document_status', update_document_status)
    monkeypatch.setattr(main, 'get_document', get_document)
    monkeypatch.setattr(main, 'list_documents', list_documents)
    monkeypatch.setattr(main, 'delete_document', delete_document)
    monkeypatch.setattr(main, 'upload_pdf', upload_pdf)
    monkeypatch.setattr(main, 'schedule_ingestion', schedule_ingestion)
    monkeypatch.setattr(main, 'set_flashcards_open', set_flashcards_open)
    monkeypatch.setattr('db.subscriptions.get_document', get_document)
    monkeypatch.setattr('db.subscriptions.list_documents', list_documents)

    monkeypatch.setattr(main, 'download_pdf', lambda _path: b'%PDF-1.4\n%test')
    monkeypatch.setattr(main, 'delete_pdf', lambda _path: None)

    from types import SimpleNamespace

    def make_dummy_result() -> SimpleNamespace:
        return SimpleNamespace(
            query='q',
            query_type='study',
            brief='Answer on page 1 [p1]',
            eval=SimpleNamespace(
                passed=True,
                score=1.0,
                claims_checked=1,
                claims_grounded=1,
                ungrounded_claims=[],
                explanation='ok',
                citation_errors=[],
            ),
            sources=[{'document_id': 'doc-1', 'page_number': 1, 'sentence_start_idx': 0, 'sentence_end_idx': 1, 'text': 'abc', 'document_title': 'Book', 'source_type': 'textbook'}],
            meta={'mode': 'quiz', 'provider': 'gemini'},
            structured={'items': [{'question': 'Q?', 'answer': 'A', 'citations': ['[p1]']}]},
        )

    async def fake_run(**_kwargs):
        return make_dummy_result()

    async def noop_init_schema() -> None:
        return None

    async def noop_ensure_vector_table() -> None:
        return None

    async def noop_seed() -> None:
        return None

    async def noop_resume() -> int:
        return 0

    monkeypatch.setattr(main.pipeline, 'run', fake_run)
    monkeypatch.setattr(main, 'init_schema', noop_init_schema)

    import ai.vector_store as vector_store

    monkeypatch.setattr(vector_store, 'ensure_vector_table', noop_ensure_vector_table)
    monkeypatch.setattr('agents.FeedAgent.seed_leetcode_accounts', noop_seed)
    monkeypatch.setattr('agents.IngestionAgent.resume_paused_embeddings', noop_resume)

    app_client = TestClient(main.app)
    app_client.state_store = state  # type: ignore[attr-defined]
    return app_client


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    from auth import COOKIE_NAME, issue_session_token

    client.cookies.set(COOKIE_NAME, issue_session_token('admin@test.com'), path='/')
    return client


@pytest.fixture
def guest_client(client: TestClient) -> TestClient:
    from auth import COOKIE_NAME, issue_session_token

    client.cookies.set(COOKIE_NAME, issue_session_token('guest@example.com'), path='/')
    return client
