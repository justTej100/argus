from __future__ import annotations

"""Gemini chat model wrapper for LangChain LCEL chains.

Default model: gemini-2.5-flash (override with GEMINI_MODEL). Set json_mode=True
for quiz / flashcard / summary structured outputs.
"""

import os

from langchain_google_genai import ChatGoogleGenerativeAI

DEFAULT_CHAT_MODEL = 'gemini-2.5-flash'


def get_chat_model(*, temperature: float = 0.4, json_mode: bool = False) -> ChatGoogleGenerativeAI:
    """Gemini chat model for tutor answers."""
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
    kwargs: dict = {
        'model': os.environ.get('GEMINI_MODEL', DEFAULT_CHAT_MODEL),
        'google_api_key': api_key,
        'temperature': temperature,
    }
    if json_mode:
        kwargs['response_mime_type'] = 'application/json'
    return ChatGoogleGenerativeAI(**kwargs)
