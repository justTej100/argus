from __future__ import annotations

"""Tests for PDF storage helpers."""

import os
from pathlib import Path

import pytest


def test_publishable_key_is_not_used_for_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'sb_publishable_test_key')
    monkeypatch.delenv('SUPABASE_SERVICE_KEY', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)

    import storage

    assert storage.supabase_write_key() is None
    assert storage._use_supabase_storage() is False


def test_service_key_alias_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'sb_publishable_test_key')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'sb_secret_service_key')

    import storage

    assert storage.supabase_write_key() == 'sb_secret_service_key'
    assert storage._use_supabase_storage() is True


def test_upload_pdf_falls_back_to_local_with_publishable_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY', 'sb_publishable_test_key')
    monkeypatch.delenv('SUPABASE_SERVICE_KEY', raising=False)

    import storage

    monkeypatch.setattr(storage, 'LOCAL_UPLOAD_DIR', tmp_path)

    path = storage.upload_pdf('doc-123', 'book.pdf', b'%PDF-1.4 test')
    assert path == str(tmp_path / 'doc-123.pdf')
    assert Path(path).read_bytes() == b'%PDF-1.4 test'
