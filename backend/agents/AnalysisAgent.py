"""
AnalysisAgent — the RAG (Retrieval-Augmented Generation) layer.

RAG in plain English:
  Instead of asking an LLM "what do people think about Rust?" from memory,
  we retrieve real documents first, then ask "here are 15 real Reddit posts —
  summarize what these people think about Rust."

  This eliminates hallucination: the LLM can only say things that are in the
  documents we gave it. If something isn't in the sources, it can't claim it.

What this agent does:
  1. Embed the search query into a vector (a list of ~1536 numbers).
  2. Embed every retrieved source item into its own vector.
  3. Rank items by cosine similarity to the query vector.
  4. Select the top-K most relevant items as the LLM's "context window".
  5. Format them into a text block the LLM can read.

Why embeddings instead of keyword matching?
  Keyword search would miss "Ferris" (the Rust mascot) as relevant to a query
  about "Rust programming". Embeddings capture semantic meaning, so
  conceptually related content ranks highly even without exact word matches.
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
    items: list[SourceItem]         # all retrieved items with embeddings populated
    top_items: list[SourceItem]     # the TOP_K most semantically relevant items
    context_window: str             # formatted text blob passed to the LLM
    token_estimate: int             # rough estimate of how many LLM tokens this uses


class AnalysisAgent:
    """
    Embed + rank + select. The output feeds directly into SynthesisAgent.
    """

    TOP_K = 15              # how many items to pass to the LLM
    MAX_CONTEXT_CHARS = 12_000  # hard cap so we don't exceed the LLM's context limit

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """
        Measure how similar two vectors are, on a scale from -1 to 1.

        Cosine similarity = (a · b) / (|a| × |b|)

        1.0  = identical direction (very similar meaning)
        0.0  = perpendicular (unrelated)
        -1.0 = opposite direction (very different meaning)

        We use this instead of Euclidean distance because embedding vectors
        are normalized — their direction matters, not their length.
        """
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

        # Embed the query AND all items concurrently.
        # asyncio.gather runs all the embed() coroutines in parallel — much faster
        # than embedding them one by one. With 36 items this saves ~35× the
        # latency of a single embed call.
        embed_tasks = [embed(query)] + [embed(item.text_for_embedding()) for item in items]
        embeddings = await asyncio.gather(*embed_tasks, return_exceptions=True)

        # embeddings[0] is the query vector; embeddings[1:] are the item vectors.
        query_vec = embeddings[0] if not isinstance(embeddings[0], Exception) else None
        for i, item in enumerate(items):
            vec = embeddings[i + 1]
            if not isinstance(vec, Exception):
                item.embedding = vec   # attach the vector to the item for later use

        # Rank by cosine similarity: items whose embedding is closest to the
        # query embedding are most semantically relevant.
        if query_vec:
            scored = [
                (item, self._cosine_similarity(query_vec, item.embedding))
                for item in items
                if item.embedding   # skip any items where embedding failed
            ]
            scored.sort(key=lambda x: x[1], reverse=True)   # highest similarity first
            top_items = [item for item, _ in scored[: self.TOP_K]]
        else:
            # If the query embedding failed (e.g. network error), fall back
            # to using the first TOP_K items in their original order.
            top_items = items[: self.TOP_K]

        # Build the context window — a formatted text block the LLM will read.
        # We cap it at MAX_CONTEXT_CHARS to stay within LLM token limits.
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
                break   # stop adding items once we'd exceed the context limit
            context_parts.append(chunk)
            total_chars += len(chunk)

        context_window = "\n".join(context_parts)
        # Rough token estimate: LLMs use ~4 characters per token on average.
        token_estimate = total_chars // 4

        return AnalysisResult(
            query=query,
            items=items,
            top_items=top_items,
            context_window=context_window,
            token_estimate=token_estimate,
        )
