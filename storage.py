from __future__ import annotations

"""PDF storage: Supabase Storage (production) or local uploaded_pdfs/ (dev).

Set STORAGE_BACKEND=supabase for cloud storage (requires SUPABASE_URL +
SUPABASE_SERVICE_KEY). Production defaults to supabase when ENVIRONMENT=production.

See README "Supabase Storage" for how to obtain the service_role key.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_UPLOAD_DIR = Path(__file__).parent / 'uploaded_pdfs'
DEFAULT_BUCKET = 'argus-pdfs'
_PUBLISHABLE_KEY_WARNING_EMITTED = False


class StorageError(RuntimeError):
    """Raised when storage operations fail or are misconfigured."""


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


def storage_backend() -> str:
    """Return configured storage backend: supabase or local."""
    explicit = os.environ.get('STORAGE_BACKEND', '').strip().lower()
    if explicit in {'supabase', 'local'}:
        return explicit
    env = os.environ.get('ENVIRONMENT', '').strip().lower()
    if env in {'prod', 'production'}:
        return 'supabase'
    return 'local'


def _use_supabase_storage() -> bool:
    return storage_backend() == 'supabase'


def _require_supabase_config() -> None:
    if not os.environ.get('SUPABASE_URL', '').strip():
        raise StorageError(
            'STORAGE_BACKEND=supabase requires SUPABASE_URL. '
            'See .env.example for Supabase setup.'
        )
    if not supabase_write_key():
        raise StorageError(
            'STORAGE_BACKEND=supabase requires SUPABASE_SERVICE_KEY (service_role). '
            'Publishable keys cannot upload files.'
        )


def _warn_if_publishable_key_configured() -> None:
    global _PUBLISHABLE_KEY_WARNING_EMITTED
    if _PUBLISHABLE_KEY_WARNING_EMITTED:
        return
    key = os.environ.get('SUPABASE_KEY', '').strip()
    if os.environ.get('SUPABASE_URL', '').strip() and key and _is_publishable_supabase_key(key):
        _PUBLISHABLE_KEY_WARNING_EMITTED = True
        logger.warning(
            'SUPABASE_KEY is a publishable key and cannot upload to Storage. '
            'Set SUPABASE_SERVICE_KEY to your service_role secret.'
        )


def _get_supabase_client():
    from supabase import create_client

    _require_supabase_config()
    return create_client(os.environ['SUPABASE_URL'], supabase_write_key())


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
        return _upload_supabase(document_id, filename, data)

    _warn_if_publishable_key_configured()
    if os.environ.get('SUPABASE_URL', '').strip() and supabase_write_key():
        try:
            return _upload_supabase(document_id, filename, data)
        except Exception as exc:
            logger.warning('Supabase upload failed (%s); using local storage.', exc)

    return _upload_local(document_id, data)


def download_pdf(storage_path: str) -> bytes:
    """Load a stored PDF from local disk or Supabase Storage."""
    path = Path(storage_path)
    if path.exists():
        return path.read_bytes()

    if storage_backend() == 'local' and not supabase_write_key():
        raise FileNotFoundError(storage_path)

    _require_supabase_config()
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

    if not storage_path.startswith('documents/'):
        return

    if not _use_supabase_storage() and not supabase_write_key():
        return

    try:
        _require_supabase_config()
        client = _get_supabase_client()
        bucket = _bucket_name()
        client.storage.from_(bucket).remove([storage_path])
    except StorageError:
        if _use_supabase_storage():
            raise
    except Exception as exc:
        if _use_supabase_storage():
            raise StorageError(f'Failed to delete from Supabase Storage: {exc}') from exc
        logger.warning('Supabase delete failed (%s)', exc)


def supabase_project_ref() -> str | None:
    """Extract project ref from SUPABASE_URL for dashboard links."""
    url = os.environ.get('SUPABASE_URL', '').strip()
    if not url:
        return os.environ.get('SUPABASE_PROJECT_REF', '').strip() or None
    explicit = os.environ.get('SUPABASE_PROJECT_REF', '').strip()
    if explicit:
        return explicit
    # https://abcdefgh.supabase.co
    host = url.replace('https://', '').replace('http://', '').split('/')[0]
    ref = host.split('.')[0] if host else ''
    return ref or None


def supabase_dashboard_urls() -> dict[str, str | None]:
    """Build Supabase dashboard URLs for tables and storage."""
    ref = supabase_project_ref()
    if not ref:
        return {'tableEditorUrl': None, 'storageUrl': None}
    bucket = _bucket_name()
    return {
        'tableEditorUrl': f'https://supabase.com/dashboard/project/{ref}/editor',
        'storageUrl': f'https://supabase.com/dashboard/project/{ref}/storage/buckets/{bucket}',
    }
