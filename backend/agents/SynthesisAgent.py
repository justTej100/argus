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