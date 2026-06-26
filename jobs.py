from __future__ import annotations

"""RQ queue helpers for background document ingestion."""

import os

from redis import Redis
from rq import Queue

QUEUE_NAME = 'argus-ingestion'


def get_queue() -> Queue:
    """Return the shared ingestion queue bound to REDIS_URL."""
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    return Queue(QUEUE_NAME, connection=Redis.from_url(redis_url))


def enqueue_ingestion(document_id: str, storage_path: str) -> str:
    """Enqueue one ingestion job and return its RQ job id."""
    from agents.IngestionAgent import ingest_document_job
    job = get_queue().enqueue(ingest_document_job, document_id, storage_path)
    return job.id
