"""
AnalysisAgent — RAG retrieval layer.

1. Embeds the query and all scraped items
2. Ranks by cosine similarity to the query vector
3. Selects top-K most relevant as context
4. Builds the context window passed to the LLM

Pattern: Retrieve → Embed → Rank → Augment
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ai.clients import embed
from scrapers.sources import SourceItem
from agents.SearchAgent import SearchResult


@dataclass
class AnalysisResult:
    query: str
    items: list[SourceItem]         # all items with embeddings attached
    top_items: list[SourceItem]     # semantically closest to the query
    context_window: str             # text blob passed to the LLM
    token_estimate: int


class AnalysisAgent:
    """
    RAG retrieval layer. Embeds everything, ranks by cosine similarity,
    builds the context window the LLM actually sees.
    """

    TOP_K = 15
    MAX_CONTEXT_CHARS = 12_000

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x ** 2 for x in a) ** 0.5
        mag_b = sum(x ** 2 for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    async def run(self, search_result: SearchResult) -> AnalysisResult:
        query = search_result.query
        items = search_result.items

        if not items:
            return AnalysisResult(
                query=query,
                items=[],
                top_items=[],
                context_window="No results found.",
                token_estimate=0,
            )

        # Embed query + all items concurrently
        embed_tasks = [embed(query)] + [embed(item.text_for_embedding()) for item in items]
        embeddings = await asyncio.gather(*embed_tasks, return_exceptions=True)

        query_vec = embeddings[0] if not isinstance(embeddings[0], Exception) else None
        for i, item in enumerate(items):
            vec = embeddings[i + 1]
            if not isinstance(vec, Exception):
                item.embedding = vec

        # Rank by cosine similarity to the query
        if query_vec:
            scored = [
                (item, self._cosine_similarity(query_vec, item.embedding))
                for item in items
                if item.embedding
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            top_items = [item for item, _ in scored[: self.TOP_K]]
        else:
            top_items = items[: self.TOP_K]

        # Build context window
        context_parts = []
        total_chars = 0
        for item in top_items:
            chunk = (
                f"[{item.source.upper()}] {item.title}\n"
                f"URL: {item.url}\n"
                f"Engagement: {item.engagement}\n"
                f"{item.body[:400]}\n"
                "---"
            )
            if total_chars + len(chunk) > self.MAX_CONTEXT_CHARS:
                break
            context_parts.append(chunk)
            total_chars += len(chunk)

        context_window = "\n".join(context_parts)
        token_estimate = total_chars // 4

        return AnalysisResult(
            query=query,
            items=items,
            top_items=top_items,
            context_window=context_window,
            token_estimate=token_estimate,
        )