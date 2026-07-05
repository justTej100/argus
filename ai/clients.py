from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx

"""Gemini client wrappers for chat completion and embeddings."""

DEFAULT_CHAT_MODEL = 'gemini-2.5-flash'
EMBED_MODEL = 'gemini-embedding-001'
EMBED_BATCH_SIZE = 100
EMBED_URL = (
    f'https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:batchEmbedContents'
)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class GeminiAPIError(RuntimeError):
    """Raised when Gemini returns a non-retryable or exhausted-retry error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AIClient:
    provider: str
    model: str
    api_key: str
    base_url: str


def get_client() -> AIClient:
    """Return the Gemini chat-completion client."""
    return AIClient(
        provider='gemini',
        model=os.environ.get('GEMINI_MODEL', DEFAULT_CHAT_MODEL),
        api_key=os.environ.get('GEMINI_API_KEY', ''),
        base_url='https://generativelanguage.googleapis.com/v1beta/openai',
    )


def _api_key() -> str:
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        raise GeminiAPIError('Missing GEMINI_API_KEY.')
    return key


def _gemini_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        err = payload.get('error', {})
        if isinstance(err, dict):
            return str(err.get('message') or err)
        return str(payload)
    except Exception:
        return response.text[:300] or f'HTTP {response.status_code}'


async def _post_json(url: str, *, headers: dict, payload: dict, retries: int = 4) -> dict:
    """POST JSON with retries on rate limits and transient Google outages (503/502)."""
    last_status: int | None = None
    last_message = ''
    async with httpx.AsyncClient(timeout=120) as http:
        for attempt in range(retries):
            response = await http.post(url, headers=headers, json=payload)
            last_status = response.status_code
            if response.status_code in _RETRYABLE_STATUS and attempt < retries - 1:
                retry_after = response.headers.get('retry-after')
                if retry_after:
                    delay = float(retry_after)
                elif response.status_code == 429:
                    delay = 5.0 * (attempt + 1)
                else:
                    delay = 2.0 * (2**attempt)
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 400:
                last_message = _gemini_error_message(response)
                if response.status_code == 503:
                    last_message = (
                        'Gemini is temporarily overloaded or down (503). '
                        'Wait a minute and try again. '
                        + last_message
                    )
                elif response.status_code == 429:
                    last_message = (
                        'Gemini rate limit reached (429). Wait a few minutes or check ai.dev/rate-limit. '
                        + last_message
                    )
                raise GeminiAPIError(
                    f'Gemini API error ({response.status_code}): {last_message}',
                    status_code=response.status_code,
                )
            return response.json()
    hint = last_message or 'Try again in a minute.'
    if last_status == 429:
        raise GeminiAPIError(f'Gemini rate limit reached after retries. {hint}', status_code=429)
    raise GeminiAPIError(f'Gemini unavailable after retries ({last_status}). {hint}', status_code=last_status or 503)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed up to EMBED_BATCH_SIZE texts in one Gemini request."""
    if not texts:
        return []
    if len(texts) > EMBED_BATCH_SIZE:
        raise ValueError(f'embed_batch supports at most {EMBED_BATCH_SIZE} texts')

    api_key = _api_key()
    payload = {
        'requests': [
            {
                'model': f'models/{EMBED_MODEL}',
                'content': {'parts': [{'text': text}]},
            }
            for text in texts
        ],
    }
    data = await _post_json(
        f'{EMBED_URL}?key={api_key}',
        headers={'Content-Type': 'application/json'},
        payload=payload,
        retries=2,
    )
    embeddings = data.get('embeddings') or []
    vectors: list[list[float]] = []
    for item in embeddings:
        values = item.get('values') if isinstance(item, dict) else None
        if not values:
            raise GeminiAPIError('Gemini batch embedding response missing values')
        vectors.append(values)
    if len(vectors) != len(texts):
        raise GeminiAPIError(
            f'Gemini returned {len(vectors)} embeddings for {len(texts)} inputs',
        )
    return vectors


async def embed_many(texts: list[str], *, batch_size: int = EMBED_BATCH_SIZE) -> list[list[float]]:
    """Embed many texts using batched API calls with light pacing."""
    if not texts:
        return []

    all_vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        all_vectors.extend(await embed_batch(batch))
        if start + batch_size < len(texts):
            await asyncio.sleep(0.25)
    return all_vectors


async def embed(text: str) -> list[float]:
    """Embed a single string."""
    return (await embed_many([text]))[0]


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
        raise GeminiAPIError('Missing GEMINI_API_KEY.')

    messages: list[dict] = [{'role': 'system', 'content': system}]
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({'role': 'user', 'content': user})

    payload: dict = {
        'model': client.model,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'messages': messages,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}

    data = await _post_json(
        f'{client.base_url}/chat/completions',
        headers={
            'Authorization': f'Bearer {client.api_key}',
            'Content-Type': 'application/json',
        },
        payload=payload,
        retries=2,
    )
    return data['choices'][0]['message']['content']
