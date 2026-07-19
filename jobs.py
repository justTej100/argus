from __future__ import annotations

"""Background ingestion scheduling (in-process, no Redis)."""

import asyncio

from agents.IngestionAgent import ingest_document
from db.client import update_document_status


async def _run_ingestion(document_id: str, storage_path: str, *, resume: bool = False) -> None:
    try:
        await ingest_document(document_id, storage_path, resume=resume)
    except Exception as exc:
        await update_document_status(
            document_id,
            status='error',
            error_message=str(exc),
        )


def schedule_ingestion(document_id: str, storage_path: str, *, resume: bool = False) -> str:
    """Start PDF ingestion in the background and return a local task id."""
    asyncio.create_task(_run_ingestion(document_id, storage_path, resume=resume))
    return f'ingest-{document_id}'
