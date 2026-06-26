from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal
import httpx

"""
Provider wrappers for chat completion and embeddings.
Gemini is the default for everything (embeddings and chat) 
unless you specify "deepseek" (chat only).
"""

ModelProvider = Literal["deepseek", "gemini"]


@dataclass
class AIClient:
    provider: ModelProvider
    model: str
    api_key: str
    base_url: str


def get_client(provider: ModelProvider = "gemini") -> AIClient:
    """Return the chat-completion client for the requested provider."""
    
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
    
    """Send a completion request and return the assistant text."""
    if not client.api_key:
        raise RuntimeError(f"Missing API key for {client.provider}.")

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
    """Embed text with Gemini gemini-embedding-001."""
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY.")

    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": text}]},
            },
        )

        r.raise_for_status()
        values = r.json().get("embedding", {}).get("values")
        if not values:
            raise RuntimeError("Gemini embedding response missing values")
        
        return values
