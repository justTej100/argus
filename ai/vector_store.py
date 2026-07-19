from __future__ import annotations

"""PGVectorStore — vector storage in Postgres table `argus_vectors`.

Each row stores content, embedding, and metadata columns including chapter.
Without DATABASE_URL, falls back to an in-memory list (tests only).
Supports batched embedding with progress callbacks for 429 resume.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from langchain_core.documents import Document
from langchain_postgres import Column, PGEngine, PGVectorStore

from ai.clients import GeminiAPIError
from ai.embeddings import VECTOR_SIZE, get_embeddings

logger = logging.getLogger(__name__)

VECTOR_TABLE = 'argus_vectors'
EMBED_BATCH_SIZE = 8
EMBED_RESUME_HOURS = 24

_engine: PGEngine | None = None
_store: PGVectorStore | None = None
_memory_docs: list[dict[str, Any]] = []

_metadata_columns = [
    Column(name='document_id', data_type='TEXT', nullable=False),
    Column(name='page', data_type='INTEGER', nullable=False),
    Column(name='title', data_type='TEXT', nullable=True),
    Column(name='course', data_type='TEXT', nullable=True),
    Column(name='chapter', data_type='TEXT', nullable=True),
]


def _database_url_psycopg() -> str:
    url = (os.environ.get('DATABASE_URL') or '').strip()
    if not url:
        return ''
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://') :]
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg://' + url[len('postgresql://') :]
    return url


def _use_memory_store() -> bool:
    return not _database_url_psycopg()


def get_engine() -> PGEngine | None:
    global _engine
    url = _database_url_psycopg()
    if not url:
        return None
    if _engine is None:
        _engine = PGEngine.from_connection_string(url)
    return _engine


async def ensure_vector_table() -> None:
    """Create argus_vectors table if missing; add chapter column when needed."""
    engine = get_engine()
    if engine is None:
        return
    try:
        await engine.ainit_vectorstore_table(
            table_name=VECTOR_TABLE,
            vector_size=VECTOR_SIZE,
            metadata_columns=_metadata_columns,
            overwrite_existing=False,
        )
    except Exception as exc:
        if 'already exists' not in str(exc).lower() and 'duplicate' not in str(exc).lower():
            logger.warning('Vector table init: %s', exc)

    # Best-effort chapter column for older tables
    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                f'ALTER TABLE {VECTOR_TABLE} ADD COLUMN IF NOT EXISTS chapter TEXT'
            )
    except Exception as exc:
        logger.debug('chapter column ensure: %s', exc)


async def get_vector_store() -> PGVectorStore | None:
    """Return shared PGVectorStore (or None when DATABASE_URL unset)."""
    global _store
    if _use_memory_store():
        return None
    engine = get_engine()
    if engine is None:
        return None
    if _store is None:
        await ensure_vector_table()
        _store = await PGVectorStore.create(
            engine=engine,
            table_name=VECTOR_TABLE,
            embedding_service=get_embeddings(),
            metadata_columns=['document_id', 'page', 'title', 'course', 'chapter'],
        )
    return _store


def chunks_to_documents(chunks: list[dict]) -> list[Document]:
    """Convert split chunk dicts to LangChain Documents."""
    docs: list[Document] = []
    for chunk in chunks:
        meta = dict(chunk.get('metadata') or {})
        doc_id = str(meta.get('document_id') or chunk.get('document_id') or '')
        page = int(meta.get('page') or meta.get('page_number') or chunk.get('page_number') or 1)
        description = str(
            meta.get('description') or chunk.get('description') or meta.get('course') or chunk.get('course') or ''
        )
        docs.append(
            Document(
                page_content=chunk['text'],
                metadata={
                    'document_id': doc_id,
                    'page': page,
                    'title': str(meta.get('title') or chunk.get('title') or ''),
                    'course': description,
                    'description': description,
                    'chapter': str(meta.get('chapter') or chunk.get('chapter') or ''),
                    'section_id': str(meta.get('section_id') or ''),
                },
            )
        )
    return docs


class EmbedPaused(Exception):
    """Raised when embedding hits a sustained rate limit and should resume later."""

    def __init__(self, done: int, total: int, resume_at: datetime):
        self.done = done
        self.total = total
        self.resume_at = resume_at
        super().__init__(f'Embedding paused at {done}/{total}; resume after {resume_at.isoformat()}')


def resume_at_default() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=EMBED_RESUME_HOURS)


async def add_document_chunks(
    document_id: str,
    chunks: list[dict],
    *,
    start_index: int = 0,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    clear_existing: bool = True,
) -> int:
    """Embed and store chunks in batches. Raises EmbedPaused on sustained 429."""
    global _memory_docs
    documents = chunks_to_documents(chunks)
    if not documents:
        return 0

    total = len(documents)
    store = await get_vector_store()
    if store is None:
        if clear_existing and start_index == 0:
            _memory_docs = [d for d in _memory_docs if d.get('metadata', {}).get('document_id') != document_id]
        for doc in documents[start_index:]:
            _memory_docs.append(
                {
                    'page_content': doc.page_content,
                    'metadata': dict(doc.metadata),
                    'id': str(uuid.uuid4()),
                }
            )
        if on_progress:
            await on_progress(total, total)
        return total

    if clear_existing and start_index == 0:
        await store.adelete(filter={'document_id': document_id})

    done = start_index
    i = start_index
    while i < total:
        batch = documents[i : i + EMBED_BATCH_SIZE]
        ids = [str(uuid.uuid4()) for _ in batch]
        try:
            await store.aadd_documents(batch, ids=ids)
        except Exception as exc:
            msg = str(exc).lower()
            status = getattr(exc, 'status_code', None)
            if status == 429 or '429' in msg or 'rate limit' in msg or 'resource_exhausted' in msg:
                if on_progress:
                    await on_progress(done, total)
                raise EmbedPaused(done, total, resume_at_default()) from exc
            if isinstance(exc, GeminiAPIError) and exc.status_code == 429:
                if on_progress:
                    await on_progress(done, total)
                raise EmbedPaused(done, total, resume_at_default()) from exc
            raise
        done = i + len(batch)
        i = done
        if on_progress:
            await on_progress(done, total)
    return total


async def delete_document_vectors(document_id: str) -> None:
    """Remove all vectors for a document."""
    global _memory_docs
    store = await get_vector_store()
    if store is None:
        _memory_docs = [d for d in _memory_docs if d.get('metadata', {}).get('document_id') != document_id]
        return
    await store.adelete(filter={'document_id': document_id})


def _memory_search(
    query: str,
    document_ids: list[str],
    limit: int,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> list[tuple[Document, float]]:
    del query
    results: list[tuple[Document, float]] = []
    for row in _memory_docs:
        meta = row.get('metadata') or {}
        if meta.get('document_id') not in document_ids:
            continue
        page = int(meta.get('page') or 1)
        if start_page is not None and page < start_page:
            continue
        if end_page is not None and page > end_page:
            continue
        results.append((Document(page_content=row['page_content'], metadata=meta), 0.0))
    return results[:limit]


async def similarity_search(
    query: str,
    document_ids: list[str],
    *,
    limit: int = 12,
    start_page: int | None = None,
    end_page: int | None = None,
) -> list[tuple[Document, float]]:
    """Retrieve similar chunks scoped to document IDs and optional page range."""
    if not document_ids:
        return []

    store = await get_vector_store()
    if store is None:
        return _memory_search(query, document_ids, limit, start_page=start_page, end_page=end_page)

    filt: dict[str, Any]
    if len(document_ids) == 1:
        filt = {'document_id': document_ids[0]}
    else:
        filt = {'document_id': {'$in': document_ids}}

    # Over-fetch when filtering by page so we still return `limit` in-range hits
    fetch_k = limit * 3 if (start_page is not None or end_page is not None) else limit
    raw = await store.asimilarity_search_with_score(query, k=fetch_k, filter=filt)

    if start_page is None and end_page is None:
        return raw[:limit]

    filtered: list[tuple[Document, float]] = []
    for doc, score in raw:
        page = int((doc.metadata or {}).get('page') or 1)
        if start_page is not None and page < start_page:
            continue
        if end_page is not None and page > end_page:
            continue
        filtered.append((doc, score))
        if len(filtered) >= limit:
            break
    return filtered


def documents_to_chunk_dicts(
    results: list[tuple[Document, float]],
) -> list[dict]:
    """Map LangChain search results to the chunk shape used by the UI."""
    chunks: list[dict] = []
    for doc, score in results:
        meta = doc.metadata or {}
        description = meta.get('description') or meta.get('course') or None
        chunks.append(
            {
                'document_id': meta.get('document_id', ''),
                'document_title': meta.get('title') or 'Textbook',
                'description': description,
                'page_number': int(meta.get('page') or 1),
                'chapter': meta.get('chapter') or '',
                'sentence_start_idx': 0,
                'sentence_end_idx': 0,
                'text': doc.page_content,
                'similarity': float(score) if score is not None else 0.0,
                'metadata': dict(meta),
            }
        )
    return chunks


async def count_vectors() -> int:
    if _use_memory_store():
        return len(_memory_docs)
    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        return len(_memory_docs)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f'SELECT COUNT(*)::int AS n FROM {VECTOR_TABLE}')
    return int(row['n']) if row else 0


async def count_vectors_for_document(document_id: str) -> int:
    if _use_memory_store():
        return sum(1 for d in _memory_docs if d.get('metadata', {}).get('document_id') == document_id)
    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f'SELECT COUNT(*)::int AS n FROM {VECTOR_TABLE} WHERE document_id = $1',
            document_id,
        )
    return int(row['n']) if row else 0


async def sample_vectors(document_id: str, limit: int = 5) -> list[dict]:
    """Sample chunk rows for admin UI (no embeddings)."""
    if _use_memory_store():
        rows = [d for d in _memory_docs if d.get('metadata', {}).get('document_id') == document_id]
        return [
            {
                'text': r['page_content'],
                'metadata': r.get('metadata') or {},
                'page_number': int((r.get('metadata') or {}).get('page') or 1),
            }
            for r in rows[:limit]
        ]
    from db.client import get_pool

    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT content AS text, page, title, course, document_id, chapter
            FROM {VECTOR_TABLE}
            WHERE document_id = $1
            ORDER BY page
            LIMIT $2
            """,
            document_id,
            limit,
        )
    return [
        {
            'text': r['text'],
            'page_number': r['page'],
            'metadata': {
                'document_id': r['document_id'],
                'page': r['page'],
                'title': r['title'],
                'course': r['course'],
                'chapter': r.get('chapter') or '',
            },
        }
        for r in rows
    ]
