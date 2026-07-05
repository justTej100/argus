from __future__ import annotations

"""LangChain PGVectorStore — vector storage in Postgres table `argus_vectors`.

Each row stores:
  - content: chunk text
  - embedding: vector(3072) from Gemini
  - metadata columns: document_id, page, title, course

Without DATABASE_URL, falls back to an in-memory list (tests only).

Table is created on app startup via ensure_vector_table() in main.py lifespan.
"""

import logging
import os
import uuid
from typing import Any

from langchain_core.documents import Document
from langchain_postgres import Column, PGEngine, PGVectorStore

from ai.langchain_embeddings import VECTOR_SIZE, get_embeddings

logger = logging.getLogger(__name__)

VECTOR_TABLE = 'argus_vectors'
_engine: PGEngine | None = None
_store: PGVectorStore | None = None
_memory_docs: list[dict[str, Any]] = []

_metadata_columns = [
    Column(name='document_id', data_type='TEXT', nullable=False),
    Column(name='page', data_type='INTEGER', nullable=False),
    Column(name='title', data_type='TEXT', nullable=True),
    Column(name='course', data_type='TEXT', nullable=True),
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
    """Create argus_vectors table if missing."""
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
        if 'already exists' in str(exc).lower() or 'duplicate' in str(exc).lower():
            return
        logger.warning('Vector table init: %s', exc)


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
            metadata_columns=['document_id', 'page', 'title', 'course'],
        )
    return _store


def chunks_to_documents(chunks: list[dict]) -> list[Document]:
    """Convert split chunk dicts to LangChain Documents."""
    docs: list[Document] = []
    for chunk in chunks:
        meta = dict(chunk.get('metadata') or {})
        doc_id = str(meta.get('document_id') or chunk.get('document_id') or '')
        page = int(meta.get('page') or meta.get('page_number') or chunk.get('page_number') or 1)
        docs.append(
            Document(
                page_content=chunk['text'],
                metadata={
                    'document_id': doc_id,
                    'page': page,
                    'title': str(meta.get('title') or chunk.get('title') or ''),
                    'course': str(meta.get('course') or chunk.get('course') or ''),
                },
            )
        )
    return docs


async def add_document_chunks(document_id: str, chunks: list[dict]) -> int:
    """Embed and store chunks for one textbook."""
    global _memory_docs
    documents = chunks_to_documents(chunks)
    if not documents:
        return 0

    store = await get_vector_store()
    if store is None:
        _memory_docs = [d for d in _memory_docs if d.get('metadata', {}).get('document_id') != document_id]
        for doc in documents:
            _memory_docs.append(
                {
                    'page_content': doc.page_content,
                    'metadata': dict(doc.metadata),
                    'id': str(uuid.uuid4()),
                }
            )
        return len(documents)

    await store.adelete(filter={'document_id': document_id})
    ids = [str(uuid.uuid4()) for _ in documents]
    await store.aadd_documents(documents, ids=ids)
    return len(documents)


async def delete_document_vectors(document_id: str) -> None:
    """Remove all vectors for a document."""
    global _memory_docs
    store = await get_vector_store()
    if store is None:
        _memory_docs = [d for d in _memory_docs if d.get('metadata', {}).get('document_id') != document_id]
        return
    await store.adelete(filter={'document_id': document_id})


def _memory_search(query: str, document_ids: list[str], limit: int) -> list[tuple[Document, float]]:
    """Trivial fallback when no DATABASE_URL (tests)."""
    del query
    results: list[tuple[Document, float]] = []
    for row in _memory_docs:
        meta = row.get('metadata') or {}
        if meta.get('document_id') in document_ids:
            results.append(
                (
                    Document(page_content=row['page_content'], metadata=meta),
                    0.0,
                )
            )
    return results[:limit]


async def similarity_search(
    query: str,
    document_ids: list[str],
    *,
    limit: int = 12,
) -> list[tuple[Document, float]]:
    """Retrieve similar chunks scoped to document IDs."""
    if not document_ids:
        return []

    store = await get_vector_store()
    if store is None:
        return _memory_search(query, document_ids, limit)

    filt: dict[str, Any]
    if len(document_ids) == 1:
        filt = {'document_id': document_ids[0]}
    else:
        filt = {'document_id': {'$in': document_ids}}

    return await store.asimilarity_search_with_score(query, k=limit, filter=filt)


def documents_to_chunk_dicts(
    results: list[tuple[Document, float]],
) -> list[dict]:
    """Map LangChain search results to the chunk shape used by the UI."""
    chunks: list[dict] = []
    for doc, score in results:
        meta = doc.metadata or {}
        chunks.append(
            {
                'document_id': meta.get('document_id', ''),
                'document_title': meta.get('title') or 'Textbook',
                'course': meta.get('course') or None,
                'page_number': int(meta.get('page') or 1),
                'sentence_start_idx': 0,
                'sentence_end_idx': 0,
                'text': doc.page_content,
                'similarity': float(score) if score is not None else 0.0,
                'metadata': dict(meta),
            }
        )
    return chunks


async def count_vectors() -> int:
    """Total rows in argus_vectors."""
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
            SELECT content AS text, page, title, course, document_id
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
            },
        }
        for r in rows
    ]
