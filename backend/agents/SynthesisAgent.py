"""
SynthesisAgent — generates the final brief using the AI model.

Takes the RAG context window from AnalysisAgent and produces:
- Topic mode: trend brief with signals, sentiment, key voices
- Person mode: OSINT dossier with activity, footprint, summary

Supports DeepSeek and Gemini interchangeably via the shared client.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult


@dataclass
class SynthesisResult:
    query: str
    query_type: str
    brief: str
    model_used: str
    provider: str
    sources_cited: list[str]


class SynthesisAgent:

    TOPIC_SYSTEM = """You are a sharp, conversational research assistant. You read real posts from Reddit,
HackerNews, and GitHub and give the user a clear, engaging summary of what people are actually saying.

Rules:
- Only use facts from the provided sources. Do not hallucinate.
- Write in a direct, conversational tone — like a well-informed friend, not a corporate report.
- Cite where things come from (e.g. "on Reddit", "HN commenters say", "a GitHub repo with 3k stars").
- Cover: What's the vibe → Key things people are saying → Any interesting disagreements → Bottom line.
- Use real numbers from the sources (upvotes, comments, stars) to show what's getting traction.
- If you're in a multi-turn conversation, answer follow-ups naturally using prior context."""

    PERSON_SYSTEM = """You are a research assistant helping users find out what's publicly known about a person.
You read Reddit posts, GitHub activity, HN comments, and web mentions.

Rules:
- Only use facts from the provided sources. Do not hallucinate.
- Write in plain English — clear, factual, useful.
- Cover: Who they are → Where they're active → What they build/discuss → Key highlights.
- Note which platforms have the most signal. Flag gaps where data is thin."""

    async def run(
        self,
        analysis: AnalysisResult,
        query_type: str,
        ai_client: AIClient,
        conversation_history: list[dict] | None = None,
    ) -> SynthesisResult:
        system = self.PERSON_SYSTEM if query_type == "person" else self.TOPIC_SYSTEM

        user_prompt = f"""User question: {analysis.query}

Fresh data retrieved from Reddit, HackerNews, GitHub ({len(analysis.top_items)} posts/items):
{analysis.context_window}

Answer the user's question based solely on the above sources."""

        brief = await complete(
            ai_client,
            system=system,
            user=user_prompt,
            temperature=0.3,
            max_tokens=2000,
            extra_messages=conversation_history,
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