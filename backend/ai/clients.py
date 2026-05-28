"""
AI model clients — DeepSeek and Gemini, hot-swappable.

The key insight here: both DeepSeek and Gemini expose an OpenAI-compatible
/chat/completions REST endpoint. That means one `complete()` function works
for both — you just change the base_url and api_key.

If no API key is set, the functions degrade gracefully:
  - complete() returns a preview message instead of crashing.
  - embed() returns a deterministic random vector (same input → same vector).
    This means the RAG ranking still works in preview mode, it's just not
    semantically meaningful.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx

ModelProvider = Literal["deepseek", "gemini"]

# Shown to the user when they haven't set an API key yet.
PREVIEW_RESPONSE = (
    "[Preview mode] Argus retrieved real posts and ranked them by relevance, "
    "but AI synthesis requires an API key. "
    "Add DEEPSEEK_API_KEY or GEMINI_API_KEY to your .env file to enable full responses."
)


@dataclass
class AIClient:
    """Holds everything needed to make a request to one AI provider."""
    provider: ModelProvider
    model: str
    api_key: str
    base_url: str


def get_client(provider: ModelProvider = "deepseek") -> AIClient:
    """
    Return a configured AIClient for the requested provider.

    Uses .get() with an empty-string default instead of os.environ[] so the
    app doesn't crash on startup if the key isn't set — it just runs in
    preview mode until the key is added to .env.
    """
    if provider == "deepseek":
        return AIClient(
            provider="deepseek",
            model="deepseek-chat",
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com/v1",
        )
    if provider == "gemini":
        return AIClient(
            provider="gemini",
            model="gemini-2.0-flash",
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            # Google's Gemini API exposes an OpenAI-compatible endpoint at this path.
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
    raise ValueError(f"Unknown provider: {provider}")


async def complete(
    client: AIClient,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
    extra_messages: list[dict] | None = None,
) -> str:
    """
    Send a chat completion request to the AI provider and return the text.

    Parameters
    ----------
    system : str
        The system prompt — sets the AI's role and rules for this call.
    user : str
        The user message — usually the query + retrieved source documents.
    extra_messages : list[dict] | None
        Optional prior conversation turns (role/content dicts) inserted
        BETWEEN the system prompt and the final user message. This is how
        multi-turn chat works: the LLM sees the full history and can answer
        follow-up questions in context.
    json_mode : bool
        When True, tells the model to return valid JSON only. Used by
        EvalAgent which needs to parse a structured grounding-check result.
    """
    # Graceful preview mode — don't crash, just explain what's needed.
    if not client.api_key:
        if json_mode:
            # EvalAgent parses this, so return valid JSON with neutral values.
            return (
                '{"claims": [], "grounding_score": 0.0, '
                '"explanation": "No API key configured — eval skipped."}'
            )
        return PREVIEW_RESPONSE

    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }

    # Build the messages array: [system] + [history...] + [user]
    # The system prompt always goes first. Then any prior turns. Then the
    # current user message last — that's what the model will respond to.
    messages: list[dict] = [{"role": "system", "content": system}]
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({"role": "user", "content": user})

    payload: dict = {
        "model": client.model,
        "temperature": temperature,   # 0 = deterministic, 1 = creative
        "max_tokens": max_tokens,
        "messages": messages,
    }

    if json_mode:
        # This instructs the model to output only valid JSON — no prose around it.
        # Not all providers support this; both DeepSeek and Gemini do.
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"{client.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        # The response follows the OpenAI schema:
        # choices[0].message.content is the model's reply text.
        return r.json()["choices"][0]["message"]["content"]


async def embed(text: str) -> list[float]:
    """
    Turn a piece of text into a vector of 1536 numbers (an embedding).

    What's an embedding? The model reads the text and produces a list of
    numbers that captures its meaning. Texts with similar meanings end up
    with similar vectors. This is what lets AnalysisAgent rank search results
    by how relevant they are to the query — it compares vectors, not keywords.

    Falls back to a deterministic random vector in preview mode (no key).
    The mock is seeded by the text's MD5 hash, so the same text always
    produces the same vector — RAG ranking still works, just not semantically.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        import hashlib
        import random
        # Seed the RNG with the text hash so the same text always gets the
        # same fake vector. Without this, every call would produce a different
        # random vector and similarity scores would be meaningless.
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(1536)]
        # Normalize to unit length so cosine similarity comparisons are valid.
        magnitude = sum(x ** 2 for x in vec) ** 0.5
        return [x / magnitude for x in vec]

    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            "https://api.deepseek.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "deepseek-embedding", "input": text},
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
