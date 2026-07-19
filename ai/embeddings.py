from __future__ import annotations

"""Gemini embedding model for PGVectorStore.

Uses GoogleGenerativeAIEmbeddings with output_dimensionality=3072 to match
gemini-embedding-001. Reads GEMINI_API_KEY or GOOGLE_API_KEY from the environment.
"""

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
