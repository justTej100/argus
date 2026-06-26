from __future__ import annotations

"""Scope-aware retrieval over textbook chunks.

The analysis step converts the user question into an embedding, resolves the
active scope into document IDs, and retrieves the best chunk matches from the
database.
"""

from dataclasses import dataclass

from ai.clients import embed
from db.client import get_scope_document_ids, retrieve_similar_chunks


@dataclass
class AnalysisResult:
    query: str
    scope: dict
    document_ids: list[str]
    chunks: list[dict]


class AnalysisAgent:
    """Resolve scope and retrieve the most relevant textbook chunks."""
    async def run(self, query: str, scope: dict | None = None, limit: int = 12) -> AnalysisResult:
        query_embedding = await embed(query)
        document_ids = await get_scope_document_ids(scope)
        chunks = await retrieve_similar_chunks(query_embedding, document_ids, limit=limit)
        return AnalysisResult(
            query=query,
            scope=scope or {'type': 'library'},
            document_ids=document_ids,
            chunks=chunks,
        )
