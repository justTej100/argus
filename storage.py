from __future__ import annotations

"""PDF storage helpers for Supabase and local development fallback."""

import os
from pathlib import Path

LOCAL_UPLOAD_DIR = Path(__file__).parent / 'uploaded_pdfs'


def upload_pdf(document_id: str, filename: str, data: bytes) -> str:
    """Store a PDF and return the storage path used later for retrieval."""
    bucket = os.environ.get('SUPABASE_BUCKET')
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    safe_name = Path(filename).name or f'{document_id}.pdf'
    storage_path = f'documents/{document_id}/{safe_name}'
    if bucket and url and key:
        from supabase import create_client
        client = create_client(url, key)
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
    bucket = os.environ.get('SUPABASE_BUCKET')
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not (bucket and url and key):
        raise FileNotFoundError(storage_path)
    from supabase import create_client
    client = create_client(url, key)
    return client.storage.from_(bucket).download(storage_path)


def delete_pdf(storage_path: str) -> None:
    """Delete a stored PDF from local disk or Supabase Storage."""
    if not storage_path:
        return
    path = Path(storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
        return

    bucket = os.environ.get('SUPABASE_BUCKET')
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not (bucket and url and key):
        return

    from supabase import create_client

    client = create_client(url, key)
    client.storage.from_(bucket).remove([storage_path])
