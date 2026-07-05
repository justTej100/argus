from __future__ import annotations

import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings

EMBED_MODEL = 'models/gemini-embedding-001'
VECTOR_SIZE = 3072


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Gemini embeddings at 3072 dimensions (matches existing schema)."""
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
    return GoogleGenerativeAIEmbeddings(
        model=EMBED_MODEL,
        google_api_key=api_key,
        output_dimensionality=VECTOR_SIZE,
    )
