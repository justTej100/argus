from __future__ import annotations

"""PDF storage helpers for Supabase and local development fallback."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_UPLOAD_DIR = Path(__file__).parent / 'uploaded_pdfs'
DEFAULT_BUCKET = 'argus-pdfs'
_PUBLISHABLE_KEY_WARNING_EMITTED = False


def _bucket_name() -> str:
    return os.environ.get('SUPABASE_BUCKET', DEFAULT_BUCKET)


def _is_publishable_supabase_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith('sb_publishable_') or lowered.startswith('publishable_')


def supabase_write_key() -> str | None:
    """Return a Supabase key suitable for server-side Storage writes."""
    for env_name in ('SUPABASE_SERVICE_KEY', 'SUPABASE_SERVICE_ROLE_KEY'):
        value = os.environ.get(env_name, '').strip()
        if value:
            return value

    key = os.environ.get('SUPABASE_KEY', '').strip()
    if not key or _is_publishable_supabase_key(key):
        return None
    return key


def _use_supabase_storage() -> bool:
    return bool(os.environ.get('SUPABASE_URL', '').strip() and supabase_write_key())


def _warn_if_publishable_key_configured() -> None:
    global _PUBLISHABLE_KEY_WARNING_EMITTED
    if _PUBLISHABLE_KEY_WARNING_EMITTED:
        return
    key = os.environ.get('SUPABASE_KEY', '').strip()
    if os.environ.get('SUPABASE_URL', '').strip() and key and _is_publishable_supabase_key(key):
        _PUBLISHABLE_KEY_WARNING_EMITTED = True
        logger.warning(
            'SUPABASE_KEY is a publishable key and cannot upload to Storage. '
            'Falling back to local uploaded_pdfs/. Set SUPABASE_SERVICE_KEY to your '
            'service_role secret from Supabase → Project Settings → API.'
        )


def _get_supabase_client():
    from supabase import create_client

    key = supabase_write_key()
    if not key:
        raise RuntimeError('Supabase write key is not configured.')
    return create_client(os.environ['SUPABASE_URL'], key)


def _ensure_bucket(client) -> str:
    """Create the storage bucket if it does not exist yet."""
    bucket = _bucket_name()
    try:
        client.storage.get_bucket(bucket)
    except Exception:
        client.storage.create_bucket(bucket)
    return bucket


def _upload_local(document_id: str, data: bytes) -> str:
    LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)
    path = LOCAL_UPLOAD_DIR / f'{document_id}.pdf'
    path.write_bytes(data)
    return str(path)


def _upload_supabase(document_id: str, filename: str, data: bytes) -> str:
    safe_name = Path(filename).name or f'{document_id}.pdf'
    storage_path = f'documents/{document_id}/{safe_name}'
    client = _get_supabase_client()
    bucket = _ensure_bucket(client)
    client.storage.from_(bucket).upload(
        storage_path,
        data,
        {'content-type': 'application/pdf', 'upsert': 'true'},
    )
    return storage_path


def upload_pdf(document_id: str, filename: str, data: bytes) -> str:
    """Store a PDF and return the storage path used later for retrieval."""
    if _use_supabase_storage():
        try:
            return _upload_supabase(document_id, filename, data)
        except Exception as exc:
            logger.warning('Supabase upload failed (%s); using local storage.', exc)

    _warn_if_publishable_key_configured()
    return _upload_local(document_id, data)


def download_pdf(storage_path: str) -> bytes:
    """Load a stored PDF from local disk or Supabase Storage."""
    path = Path(storage_path)
    if path.exists():
        return path.read_bytes()
    if not _use_supabase_storage():
        raise FileNotFoundError(storage_path)
    client = _get_supabase_client()
    bucket = _bucket_name()
    return client.storage.from_(bucket).download(storage_path)


def delete_pdf(storage_path: str) -> None:
    """Delete a stored PDF from local disk or Supabase Storage."""
    if not storage_path:
        return
    path = Path(storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
        return
    if not _use_supabase_storage():
        return
    client = _get_supabase_client()
    bucket = _bucket_name()
    client.storage.from_(bucket).remove([storage_path])
