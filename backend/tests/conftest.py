from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    os.environ['ARGUS_ENABLE_NICEGUI'] = '0'
    os.environ['APP_PASSWORD'] = 'test-password'

    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    import main  # type: ignore

    state: dict[str, dict] = {}

    async def create_document(title: str, course: str | None, status: str, total_pages: int, storage_path: str, subreddits: list[str] | None) -> str:
        doc_id = f'doc-{len(state) + 1}'
        state[doc_id] = {
            'id': doc_id,
            'title': title,
            'course': course,
            'status': status,
            'total_pages': total_pages,
            'storage_path': storage_path,
            'subreddits': subreddits,
            'has_scan_warning': False,
            'error_message': None,
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

    async def list_documents(course: str | None = None):
        docs = list(state.values())
        if course:
            docs = [d for d in docs if d.get('course') == course]
        return docs

    async def delete_document(document_id: str) -> None:
        state.pop(document_id, None)

    def upload_pdf(document_id: str, filename: str, data: bytes) -> str:
        return f'documents/{document_id}/{filename}'

    def enqueue_ingestion(document_id: str, storage_path: str) -> str:
        return f'job-{document_id}'

    monkeypatch.setattr(main, 'create_document', create_document)
    monkeypatch.setattr(main, 'update_document_status', update_document_status)
    monkeypatch.setattr(main, 'get_document', get_document)
    monkeypatch.setattr(main, 'list_documents', list_documents)
    monkeypatch.setattr(main, 'delete_document', delete_document)
    monkeypatch.setattr(main, 'upload_pdf', upload_pdf)
    monkeypatch.setattr(main, 'enqueue_ingestion', enqueue_ingestion)

    monkeypatch.setattr(main, 'download_pdf', lambda _path: b'%PDF-1.4\n%test')
    monkeypatch.setattr(main, 'delete_pdf', lambda _path: None)

    class DummyEval:
        passed = True
        score = 1.0
        claims_checked = 1
        claims_grounded = 1
        ungrounded_claims = []
        explanation = 'ok'
        citation_errors = []

    class DummyResult:
        query = 'q'
        query_type = 'study'
        brief = 'Answer [p1:s0]'
        eval = DummyEval()
        sources = [{'document_id': 'doc-1', 'page_number': 1, 'sentence_start_idx': 0, 'sentence_end_idx': 1, 'text': 'abc', 'document_title': 'Book', 'source_type': 'textbook'}]
        community_context = []
        meta = {'mode': 'chat'}
        structured = None

    async def fake_run(**_kwargs):
        return DummyResult()

    monkeypatch.setattr(main.pipeline, 'run', fake_run)

    app_client = TestClient(main.app)
    app_client.state_store = state  # type: ignore[attr-defined]
    return app_client
