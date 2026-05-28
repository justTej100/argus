"""
AI model clients — DeepSeek and Gemini, hot-swappable.

Both providers expose an OpenAI-compatible /chat/completions endpoint.
If no API key is set the functions degrade gracefully so the app can
still be previewed (scraping and RAG still run, synthesis is mocked).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx

ModelProvider = Literal["deepseek", "gemini"]

PREVIEW_RESPONSE = (
    "[Preview mode] Argus retrieved real posts and ranked them by relevance, "
    "but AI synthesis requires an API key. "
    "Add DEEPSEEK_API_KEY or GEMINI_API_KEY to your .env file to enable full responses."
)


@dataclass
class AIClient:
    provider: ModelProvider
    model: str
    api_key: str
    base_url: str


def get_client(provider: ModelProvider = "deepseek") -> AIClient:
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
    Unified completion call. Both providers use the OpenAI-compatible endpoint.

    extra_messages: optional prior conversation turns inserted between the
    system prompt and the final user message (used for multi-turn chat).

    Returns a preview message instead of crashing when no API key is set.
    """
    if not client.api_key:
        if json_mode:
            return (
                '{"claims": [], "grounding_score": 0.0, '
                '"explanation": "No API key configured — eval skipped."}'
            )
        return PREVIEW_RESPONSE

    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }

    messages: list[dict] = [{"role": "system", "content": system}]
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({"role": "user", "content": user})

    payload: dict = {
        "model": client.model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"{client.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def embed(text: str) -> list[float]:
    """
    Generate an embedding vector for a piece of text.
    Uses DeepSeek's embedding endpoint (1536-dim).
    Falls back to a deterministic mock if no key is set (for dev/preview).
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        import hashlib
        import random
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(1536)]
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
