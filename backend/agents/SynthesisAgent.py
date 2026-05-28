"""
SynthesisAgent — generates the final answer using an LLM.

This is where the "G" in RAG happens: Generation.

The agent receives the context window built by AnalysisAgent (up to 15
real posts formatted as text) and asks the LLM to answer the user's
question using only that content. The "only use the provided sources"
rule in the system prompt is what keeps the LLM from hallucinating.

Multi-turn chat: when conversation_history is provided, prior turns are
prepended to the LLM messages array. The model sees the full conversation
and can answer follow-ups like "expand on point 2" or "which of those
had the most upvotes?" coherently.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult


@dataclass
class SynthesisResult:
    query: str
    query_type: str
    brief: str           # the AI-generated answer text
    model_used: str      # e.g. "deepseek-chat"
    provider: str        # "deepseek" or "gemini"
    sources_cited: list[str]   # which source platforms were in the context


class SynthesisAgent:

    # The system prompt defines the AI's role and the rules it must follow.
    # "Only use facts from the provided sources" is the grounding constraint —
    # it tells the LLM to treat the context window as its only allowed knowledge.

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
        # Pick the right system prompt based on whether this is a topic or person query.
        system = self.PERSON_SYSTEM if query_type == "person" else self.TOPIC_SYSTEM

        # The user prompt contains two things:
        #   1. The user's actual question.
        #   2. The context window — all the source documents the LLM is allowed to use.
        # By putting the sources IN the prompt, we're doing the "A" in RAG:
        # Augmenting the generation with Retrieved content.
        user_prompt = f"""User question: {analysis.query}

Fresh data retrieved from Reddit, HackerNews, GitHub ({len(analysis.top_items)} posts/items):
{analysis.context_window}

Answer the user's question based solely on the above sources."""

        brief = await complete(
            ai_client,
            system=system,
            user=user_prompt,
            temperature=0.3,   # slightly higher than 0 for a natural, varied tone
            max_tokens=2000,
            # Conversation history slots in between the system prompt and this
            # user message. The LLM sees: [system] → [prior turns] → [current query + sources].
            extra_messages=conversation_history,
        )

        # Record which source platforms appeared in the context — useful for
        # the frontend to show "answered using reddit, hackernews" etc.
        sources_cited = list({item.source for item in analysis.top_items})

        return SynthesisResult(
            query=analysis.query,
            query_type=query_type,
            brief=brief,
            model_used=ai_client.model,
            provider=ai_client.provider,
            sources_cited=sources_cited,
        )
