from __future__ import annotations

"""PDF storage helpers for Supabase and local development fallback."""

import os
from pathlib import Path

LOCAL_UPLOAD_DIR = Path(__file__).parent / 'uploaded_pdfs'
DEFAULT_BUCKET = 'argus-pdfs'


def _use_supabase() -> bool:
    return bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_KEY'))


def _bucket_name() -> str:
    return os.environ.get('SUPABASE_BUCKET', DEFAULT_BUCKET)


def _get_supabase_client():
    from supabase import create_client

    return create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])


def _ensure_bucket(client) -> str:
    """Create the storage bucket if it does not exist yet."""
    bucket = _bucket_name()
    try:
        client.storage.get_bucket(bucket)
    except Exception:
        client.storage.create_bucket(bucket)
    return bucket


def upload_pdf(document_id: str, filename: str, data: bytes) -> str:
    """Store a PDF and return the storage path used later for retrieval."""
    safe_name = Path(filename).name or f'{document_id}.pdf'
    storage_path = f'documents/{document_id}/{safe_name}'
    if _use_supabase():
        client = _get_supabase_client()
        bucket = _ensure_bucket(client)
        client.storage.from_(bucket).upload(
            storage_path,
            data,
            {'content-type': 'application/pdf', 'upsert': 'true'},
        )
        return storage_path
    LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)
    path = LOCAL_UPLOAD_DIR / f'{document_id}.pdf'
    path.write_bytes(data)
    return str(path)


def download_pdf(storage_path: str) -> bytes:
    """Load a stored PDF from local disk or Supabase Storage."""
    path = Path(storage_path)
    if path.exists():
        return path.read_bytes()
    if not _use_supabase():
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
    if not _use_supabase():
        return
    client = _get_supabase_client()
    bucket = _bucket_name()
    client.storage.from_(bucket).remove([storage_path])
