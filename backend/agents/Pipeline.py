"""
pipeline.py — orchestrates the 4 agents in sequence.

SearchAgent → AnalysisAgent → SynthesisAgent → EvalAgent

This is the only file that api/main.py needs to import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.SearchAgent import SearchAgent, SearchResult
from agents.AnalysisAgent import AnalysisAgent, AnalysisResult
from agents.SynthesisAgent import SynthesisAgent, SynthesisResult
from agents.EvalAgent import EvalAgent, EvalResult


@dataclass
class PipelineResult:
    query: str
    query_type: str
    brief: str
    eval: EvalResult
    sources: list[dict]
    meta: dict[str, Any]


class ResearchPipeline:
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
        conversation_history: list[dict] | None = None,
    ) -> PipelineResult:
        from ai.clients import get_client
        ai_client = get_client(provider)  # type: ignore

        # Stage 1 — Search
        search = await self.search_agent.run(query, query_type, sources)

        # Stage 2 — Embed + RAG retrieval
        analysis = await self.analysis_agent.run(search)

        # Stage 3 — Synthesize (with optional conversation history for multi-turn chat)
        synthesis = await self.synthesis_agent.run(
            analysis, query_type, ai_client, conversation_history
        )

        # Stage 4 — Eval
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
                    "body": item.body,
                    "author": item.author,
                    "container": item.container,
                    "published_at": item.published_at,
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