"""
Pipeline.py — orchestrates the 4 agents in a fixed sequence.

This is the only file that main.py needs to import. It wires the agents
together and owns the data flow between them:

    SearchAgent → AnalysisAgent → SynthesisAgent → EvalAgent

Each agent has a single responsibility and a clean input/output contract.
That makes them easy to test in isolation, swap out, or run in different
orders if you want to experiment.

Why a ResearchPipeline class instead of a plain function?
  The agents are stateless, but having a class lets you inject different
  agent implementations (e.g. a mock SearchAgent in tests) without
  touching the orchestration logic.
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
    """
    The final output of the full pipeline — everything the API route needs
    to build a response. Keeping this as a dataclass (not a Pydantic model)
    means the pipeline is independent of FastAPI.
    """
    query: str
    query_type: str
    brief: str          # the AI-generated answer
    eval: EvalResult    # grounding check results
    sources: list[dict] # the actual posts the AI read (shown in the UI)
    meta: dict[str, Any]


class ResearchPipeline:
    def __init__(self) -> None:
        # Each agent is instantiated once and reused across all requests.
        # They're all stateless so this is safe.
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
        """
        Run the full 4-agent pipeline and return the combined result.

        conversation_history: prior chat turns from the /chat endpoint.
          Passed through to SynthesisAgent so the LLM can answer follow-up
          questions with awareness of what was said earlier.
        """
        # Resolve the AI client once here, then pass it to whichever agents
        # need it (Synthesis and Eval). This way agents don't need to know
        # about the provider selection logic.
        from ai.clients import get_client
        ai_client = get_client(provider)  # type: ignore

        # ── Stage 1: Search ───────────────────────────────────────────────
        # Fan out to Reddit, HN, GitHub, etc. in parallel.
        # Returns a flat list of SourceItems — same shape regardless of source.
        search = await self.search_agent.run(query, query_type, sources)

        # ── Stage 2: RAG retrieval ────────────────────────────────────────
        # Embed the query and every search result, then rank by cosine
        # similarity. Returns the top-15 most relevant items as a context window.
        analysis = await self.analysis_agent.run(search)

        # ── Stage 3: Synthesis ────────────────────────────────────────────
        # Feed the context window to the LLM and get a grounded answer.
        # If conversation_history is provided, it's prepended to the LLM
        # messages so follow-up questions work naturally.
        synthesis = await self.synthesis_agent.run(
            analysis, query_type, ai_client, conversation_history
        )

        # ── Stage 4: Eval ─────────────────────────────────────────────────
        # A second LLM call extracts every factual claim from the brief and
        # checks whether each one can be found in the source documents.
        # Returns a grounding score 0.0–1.0 and a list of unverified claims.
        eval_result = await self.eval_agent.run(synthesis, analysis, ai_client)

        # ── Optional: persist to Postgres ────────────────────────────────────
        # Only runs when DATABASE_URL is set. Wrapped in try/except so a DB
        # error never breaks the API response — persistence is best-effort.
        try:
            from db.client import get_pool, save_search, save_items, save_eval
            pool = await get_pool()
            if pool:
                async with pool.acquire() as conn:
                    search_id = await save_search(
                        conn,
                        query=query,
                        query_type=query_type,
                        provider=provider,
                        brief=synthesis.brief,
                        grounding_score=eval_result.score,
                        sources_hit=search.sources_hit,
                        items_retrieved=len(search.items),
                        duration_ms=round(search.duration_ms),
                    )
                    await save_items(conn, search_id, analysis.top_items)
                    await save_eval(
                        conn,
                        search_id=search_id,
                        passed=eval_result.passed,
                        score=eval_result.score,
                        claims_checked=eval_result.claims_checked,
                        claims_grounded=eval_result.claims_grounded,
                        ungrounded_claims=eval_result.ungrounded_claims,
                        explanation=eval_result.explanation,
                    )
        except Exception as db_exc:
            print(f"[db] Save failed (non-fatal): {db_exc}")

        return PipelineResult(
            query=query,
            query_type=query_type,
            brief=synthesis.brief,
            eval=eval_result,
            # Expand the full source fields so the frontend can display
            # the actual post content, not just the title and URL.
            sources=[
                {
                    "source":       item.source,
                    "title":        item.title,
                    "url":          item.url,
                    "body":         item.body,
                    "author":       item.author,
                    "container":    item.container,    # subreddit, GitHub org, etc.
                    "published_at": item.published_at,
                    "engagement":   item.engagement,
                }
                for item in analysis.top_items[:20]
            ],
            meta={
                "provider":          provider,
                "model":             ai_client.model,
                "sources_hit":       search.sources_hit,   # which scrapers returned data
                "items_retrieved":   len(search.items),    # total before RAG filtering
                "items_in_context":  len(analysis.top_items),  # top-K sent to LLM
                "search_duration_ms": round(search.duration_ms),
                "token_estimate":    analysis.token_estimate,
                "grounding_score":   eval_result.score,
                "errors":            search.errors,    # per-source scraper errors, if any
            },
        )
