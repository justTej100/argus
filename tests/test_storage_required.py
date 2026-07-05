from __future__ import annotations

"""Tests for storage backend enforcement."""

import os

import pytest


def test_storage_backend_defaults_local_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('STORAGE_BACKEND', raising=False)
    monkeypatch.setenv('ENVIRONMENT', 'development')
    import storage

    assert storage.storage_backend() == 'local'


def test_storage_backend_supabase_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('STORAGE_BACKEND', raising=False)
    monkeypatch.setenv('ENVIRONMENT', 'production')
    import storage

    assert storage.storage_backend() == 'supabase'


def test_upload_requires_service_key_when_supabase_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STORAGE_BACKEND', 'supabase')
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.delenv('SUPABASE_SERVICE_KEY', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    monkeypatch.delenv('SUPABASE_KEY', raising=False)

    import storage

    with pytest.raises(storage.StorageError, match='SUPABASE_SERVICE_KEY'):
        storage.upload_pdf('doc-1', 'book.pdf', b'%PDF-1.4')
