"""
Agent system — four named agents, each with a single responsibility.

Pipeline:
    SearchAgent   → fans out to all scrapers in parallel
    AnalysisAgent → embeds results, retrieves relevant context (RAG)
    SynthesisAgent → generates the final brief via LLM
    EvalAgent     → checks if claims in the brief are grounded in sources

This is intentionally named and documented for resume clarity.
Every agent is async, stateless, and composable.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ai.clients import AIClient, complete, embed
from scrapers.sources import (
    SourceItem,
    scrape_exa,
    scrape_github,
    scrape_hackernews,
    scrape_reddit,
    scrape_social,
)


# ---------------------------------------------------------------------------
# Shared result types
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    query: str
    query_type: str          # "person" | "topic"
    items: list[SourceItem]
    sources_hit: list[str]
    duration_ms: float
    errors: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    query: str
    items: list[SourceItem]          # items now have embeddings attached
    top_items: list[SourceItem]      # semantically closest to the query
    context_window: str              # text blob passed to the LLM
    token_estimate: int


@dataclass
class SynthesisResult:
    query: str
    query_type: str
    brief: str                       # the full AI-generated brief
    model_used: str
    provider: str
    sources_cited: list[str]


@dataclass
class EvalResult:
    passed: bool
    score: float                     # 0.0 – 1.0  (grounding confidence)
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]
    explanation: str


@dataclass
class PipelineResult:
    query: str
    query_type: str
    brief: str
    eval: EvalResult
    sources: list[dict]
    meta: dict[str, Any]


# ---------------------------------------------------------------------------
# SearchAgent
# ---------------------------------------------------------------------------

class SearchAgent:
    """
    Fans out to all configured scrapers in parallel using asyncio.gather.
    Returns a normalized list of SourceItems across all sources.

    Sources used:
        Free:  Reddit, HackerNews, GitHub
        Paid:  Exa (web), ScrapeCreators (TikTok/Instagram/X)
    """

    DEFAULT_SOURCES = ["reddit", "hackernews", "github"]
    PAID_SOURCES = ["exa", "tiktok", "instagram"]

    async def run(
        self,
        query: str,
        query_type: str = "topic",
        sources: list[str] | None = None,
        limit_per_source: int = 12,
    ) -> SearchResult:
        t0 = time.time()
        active_sources = sources or self.DEFAULT_SOURCES
        errors: list[str] = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = {}

            if "reddit" in active_sources:
                tasks["reddit"] = scrape_reddit(client, query, limit_per_source)
            if "hackernews" in active_sources:
                tasks["hackernews"] = scrape_hackernews(client, query, limit_per_source)
            if "github" in active_sources:
                tasks["github"] = scrape_github(client, query, limit_per_source)
            if "exa" in active_sources:
                tasks["exa"] = scrape_exa(client, query, limit_per_source)
            if "tiktok" in active_sources:
                tasks["tiktok"] = scrape_social(client, query, "tiktok", limit_per_source)
            if "instagram" in active_sources:
                tasks["instagram"] = scrape_social(client, query, "instagram", limit_per_source)

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        all_items: list[SourceItem] = []
        sources_hit: list[str] = []

        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                errors.append(f"{source_name}: {result}")
            elif result:
                all_items.extend(result)
                sources_hit.append(source_name)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped: list[SourceItem] = []
        for item in all_items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                deduped.append(item)

        return SearchResult(
            query=query,
            query_type=query_type,
            items=deduped,
            sources_hit=sources_hit,
            duration_ms=(time.time() - t0) * 1000,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# AnalysisAgent  (RAG retrieval)
# ---------------------------------------------------------------------------

class AnalysisAgent:
    """
    RAG retrieval layer.

    1. Embeds the query and all scraped items using the embedding model
    2. Ranks items by cosine similarity to the query vector
    3. Selects the top-K most relevant items as context
    4. Builds the context window that gets passed to the LLM

    This is the core RAG pattern:
        Retrieve → Embed → Rank → Augment
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

        # Rank by cosine similarity
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
        token_estimate = total_chars // 4  # rough GPT token estimate

        return AnalysisResult(
            query=query,
            items=items,
            top_items=top_items,
            context_window=context_window,
            token_estimate=token_estimate,
        )


# ---------------------------------------------------------------------------
# SynthesisAgent
# ---------------------------------------------------------------------------

class SynthesisAgent:
    """
    Generates the final brief using the AI model.

    Takes the RAG context window from AnalysisAgent and produces:
    - For topics: trend brief with signals, sentiment, key voices
    - For people: OSINT dossier with activity, footprint, summary

    Supports DeepSeek and Gemini interchangeably.
    """

    TOPIC_SYSTEM = """You are a research analyst. You synthesize scraped data from Reddit, 
HackerNews, GitHub, and the web into a concise, grounded intelligence brief.

Rules:
- Only use facts from the provided sources. Do not hallucinate.
- Cite sources by name (e.g. "per Reddit", "on HN", "GitHub shows").
- Structure: What's happening → Key signals → Sentiment → Notable voices → Summary
- Be specific. Use numbers from the sources (upvotes, stars, comments).
- Flag uncertainty when sources conflict or evidence is thin."""

    PERSON_SYSTEM = """You are an OSINT analyst. You build intelligence profiles of people 
from public data: Reddit posts, GitHub activity, HN comments, web mentions.

Rules:
- Only use facts from the provided sources. Do not hallucinate.
- Structure: Identity → Online presence → Recent activity → Technical signals → Summary
- Note which platforms they're active on, what they build, what they discuss.
- Be factual and neutral. Flag gaps in the data."""

    async def run(
        self,
        analysis: AnalysisResult,
        query_type: str,
        ai_client: AIClient,
    ) -> SynthesisResult:
        system = self.PERSON_SYSTEM if query_type == "person" else self.TOPIC_SYSTEM

        user_prompt = f"""Research query: {analysis.query}

Sources retrieved ({len(analysis.top_items)} items):
{analysis.context_window}

Write a comprehensive brief based solely on the above sources."""

        brief = await complete(
            ai_client,
            system=system,
            user=user_prompt,
            temperature=0.2,
            max_tokens=2000,
        )

        sources_cited = list({item.source for item in analysis.top_items})

        return SynthesisResult(
            query=analysis.query,
            query_type=query_type,
            brief=brief,
            model_used=ai_client.model,
            provider=ai_client.provider,
            sources_cited=sources_cited,
        )


# ---------------------------------------------------------------------------
# EvalAgent  (grounding check)
# ---------------------------------------------------------------------------

class EvalAgent:
    """
    Evaluates whether the synthesized brief is grounded in the source material.

    This is an LLM-as-judge eval pattern:
    1. Extract factual claims from the brief
    2. Check each claim against the retrieved sources
    3. Return a grounding score + list of ungrounded claims

    A claim is "grounded" if it can be directly verified in at least one source.
    Ungrounded claims = potential hallucinations.

    This pattern is in high demand for AI engineering roles — most companies
    ship AI and then ask "is this actually accurate?". This is how you answer.
    """

    EVAL_SYSTEM = """You are a fact-checking agent. You verify whether claims in an AI-generated 
brief are supported by the provided source documents.

For each claim in the brief:
1. Identify specific factual assertions (numbers, names, events, quotes)
2. Check if each assertion appears in the sources
3. Mark as GROUNDED (found in sources) or UNGROUNDED (not found / contradicted)

Return JSON only:
{
  "claims": [
    {"claim": "...", "grounded": true/false, "source": "reddit/hn/github/null"}
  ],
  "grounding_score": 0.0-1.0,
  "explanation": "..."
}"""

    async def run(
        self,
        synthesis: SynthesisResult,
        analysis: AnalysisResult,
        ai_client: AIClient,
    ) -> EvalResult:
        # Build a compact source summary for the eval
        source_summary = "\n".join(
            f"[{item.source}] {item.title}: {item.body[:200]}"
            for item in analysis.top_items[:10]
        )

        user_prompt = f"""Brief to evaluate:
{synthesis.brief}

Source documents:
{source_summary}

Check each factual claim in the brief against the sources."""

        try:
            raw = await complete(
                ai_client,
                system=self.EVAL_SYSTEM,
                user=user_prompt,
                temperature=0.1,
                max_tokens=1500,
                json_mode=True,
            )
            data = json.loads(raw)
            claims = data.get("claims", [])
            grounded = [c for c in claims if c.get("grounded")]
            ungrounded = [c["claim"] for c in claims if not c.get("grounded")]
            score = float(data.get("grounding_score", len(grounded) / max(len(claims), 1)))

            return EvalResult(
                passed=score >= 0.75,
                score=round(score, 3),
                claims_checked=len(claims),
                claims_grounded=len(grounded),
                ungrounded_claims=ungrounded,
                explanation=data.get("explanation", ""),
            )

        except Exception as exc:
            return EvalResult(
                passed=False,
                score=0.0,
                claims_checked=0,
                claims_grounded=0,
                ungrounded_claims=[],
                explanation=f"Eval failed: {exc}",
            )


# ---------------------------------------------------------------------------
# Pipeline  (wires all 4 agents together)
# ---------------------------------------------------------------------------

class ResearchPipeline:
    """
    Orchestrates the full agentic RAG pipeline:

        SearchAgent → AnalysisAgent → SynthesisAgent → EvalAgent

    This is the object the FastAPI routes call.
    """

    def __init__(self) -> None:
        self.search_agent = SearchAgent()
        self.analysis_agent = AnalysisAgent()
        self.synthesis_agent = SynthesisAgent()
        self.eval_agent = EvalAgent()

    async def run(
        self,
        query: str,
        query_type: str = "topic",
        provider: str = "deepseek",
        sources: list[str] | None = None,
    ) -> PipelineResult:
        from ai.clients import get_client
        ai_client = get_client(provider)  # type: ignore

        # Stage 1 — Search
        search = await self.search_agent.run(query, query_type, sources)

        # Stage 2 — Embed + RAG retrieval
        analysis = await self.analysis_agent.run(search)

        # Stage 3 — Synthesize
        synthesis = await self.synthesis_agent.run(analysis, query_type, ai_client)

        # Stage 4 — Eval (grounding check)
        eval_result = await self.eval_agent.run(synthesis, analysis, ai_client)

        return PipelineResult(
            query=query,
            query_type=query_type,
            brief=synthesis.brief,
            eval=eval_result,
            sources=[
                {
                    "source": item.source,
                    "title": item.title,
                    "url": item.url,
                    "engagement": item.engagement,
                }
                for item in analysis.top_items[:20]
            ],
            meta={
                "provider": provider,
                "model": ai_client.model,
                "sources_hit": search.sources_hit,
                "items_retrieved": len(search.items),
                "items_in_context": len(analysis.top_items),
                "search_duration_ms": round(search.duration_ms),
                "token_estimate": analysis.token_estimate,
                "grounding_score": eval_result.score,
                "errors": search.errors,
            },
        )