"""
Argus — FastAPI entry point.

This file only does two things:
  1. Defines the HTTP routes (what URLs the API responds to).
  2. Converts between HTTP request/response shapes and the pipeline's internal types.

All the real work happens in agents/pipeline.py. Keeping routes thin like this
makes it easy to swap the transport layer (e.g. add websockets, gRPC) later.

Run with:
    cd backend && uvicorn main:app --reload
Swagger UI (interactive docs): http://localhost:8000/docs
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Path(__file__) is this file (backend/main.py).
# .parent      → backend/
# .parent.parent → argus/   ← where the single .env lives
# This means you can run uvicorn from any directory and it still finds the .env.
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.Pipeline import ResearchPipeline
from api.keys import generate_api_key, verify_api_key

app = FastAPI(
    title="Argus API",
    description=(
        "Agentic RAG research pipeline. OSINT + trend analysis across "
        "Reddit, HN, GitHub, Exa, and social platforms.\n\n"
        "**Demo key:** `demo-key-argus` (10 requests/day)\n\n"
        "Use `POST /keys/generate` to get your own key."
    ),
    version="1.0.0",
)

# Allow all origins in dev so the Next.js frontend (localhost:3000) can call
# the backend (localhost:8000) without browser CORS errors.
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create the pipeline once at startup, not on every request.
# The agents inside it (SearchAgent, AnalysisAgent, etc.) are stateless,
# so a single shared instance is safe and avoids re-initialization overhead.
pipeline = ResearchPipeline()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
# Pydantic models do two things here:
#   1. Validate incoming JSON — FastAPI returns a 422 automatically if the
#      shape doesn't match, so we don't write any manual validation code.
#   2. Serialize outgoing data — the response_model= on each route uses these
#      to control exactly which fields the client sees.

class SearchRequest(BaseModel):
    query: str
    type: Literal["topic", "person"] = "topic"
    provider: Literal["deepseek", "gemini"] = "deepseek"
    sources: list[str] | None = None  # None = use all default sources

    model_config = {
        "json_schema_extra": {
            # These show up as example payloads in the /docs Swagger UI.
            "examples": [
                {
                    "query": "bitcoin ETF approval",
                    "type": "topic",
                    "provider": "deepseek",
                },
                {
                    "query": "Vitalik Buterin",
                    "type": "person",
                    "provider": "gemini",
                    "sources": ["reddit", "hackernews", "github"],
                },
            ]
        }
    }


class ChatMessage(BaseModel):
    # Same shape as the OpenAI messages array — role + content.
    # This makes it easy to swap in other LLM providers later.
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    # The frontend sends the ENTIRE conversation history on every request.
    # The backend doesn't store state — the client owns the history.
    # This is the same pattern OpenAI's chat API uses.
    messages: list[ChatMessage]
    provider: Literal["deepseek", "gemini"] = "deepseek"
    sources: list[str] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "messages": [
                        {"role": "user", "content": "What are devs saying about Rust right now?"}
                    ],
                    "provider": "deepseek",
                },
                {
                    # Multi-turn example: the second user message is a follow-up.
                    # The prior assistant turn gives the LLM context to answer it.
                    "messages": [
                        {"role": "user", "content": "Latest AI coding tools discussion"},
                        {"role": "assistant", "content": "People on HN are talking about..."},
                        {"role": "user", "content": "Which one has the most upvotes?"},
                    ],
                    "provider": "gemini",
                },
            ]
        }
    }


class EvalResponse(BaseModel):
    # Grounding check results from EvalAgent.
    # `score` is 0.0–1.0: what fraction of the AI's factual claims
    # could be verified against the retrieved source documents.
    passed: bool             # true if score >= 0.75
    score: float
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]   # the specific claims that couldn't be verified
    explanation: str


class SearchResponse(BaseModel):
    # Shared response shape for both /search and /chat.
    # `sources` is list[dict] (untyped) so both the old 4-field shape
    # and the new expanded shape (with body, author, etc.) both validate.
    query: str
    type: str
    brief: str
    eval: EvalResponse
    sources: list[dict]
    meta: dict


class KeyResponse(BaseModel):
    api_key: str
    plan: str
    daily_limit: int
    note: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Meta"])
def root():
    # Simple directory — useful when someone hits the API root in a browser.
    return {
        "name": "Argus API",
        "version": "1.0.0",
        "demo_key": "demo-key-argus",
        "docs": "/docs",
        "endpoints": {
            "POST /chat":          "Multi-turn chat grounded in real-time scraped data",
            "POST /search":        "Single-query RAG pipeline (original endpoint)",
            "POST /keys/generate": "Generate an API key",
            "GET /health":         "Health check",
        },
    }


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/search", response_model=SearchResponse, tags=["Research"])
async def search(
    body: SearchRequest,
    # Depends(verify_api_key) runs verify_api_key() before this function.
    # If the key is invalid or rate-limited it raises an HTTP exception and
    # this handler never runs. If it passes, key_data is returned and injected here.
    key_data: dict = Depends(verify_api_key),
):
    """
    Single-turn research pipeline:

    1. **SearchAgent** fans out to Reddit, HN, GitHub, Exa, etc. in parallel
    2. **AnalysisAgent** embeds results + ranks by semantic similarity (RAG)
    3. **SynthesisAgent** generates a brief via DeepSeek or Gemini
    4. **EvalAgent** grounding-checks the brief against the sources

    Returns the brief, grounding score, and all sources.
    """
    result = await pipeline.run(
        query=body.query,
        query_type=body.type,
        provider=body.provider,
        sources=body.sources,
    )
    return SearchResponse(
        query=result.query,
        type=result.query_type,
        brief=result.brief,
        # vars() turns the EvalResult dataclass into a plain dict so we can
        # unpack it into the EvalResponse Pydantic model.
        eval=EvalResponse(**vars(result.eval)),
        sources=result.sources,
        # Merge the pipeline's meta dict with the rate-limit info from the key check.
        meta={**result.meta, "rate_limit": key_data},
    )


@app.post("/chat", response_model=SearchResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    key_data: dict = Depends(verify_api_key),
):
    """
    Multi-turn chat endpoint.

    Extracts the latest user message as the search query, runs the full RAG
    pipeline against live data, then feeds the prior conversation turns into
    the LLM so follow-up questions are answered in context.
    """
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="At least one user message is required.")

    # The most recent user message drives the data retrieval.
    query = user_messages[-1].content

    # Everything before the final user message is "history" — it gets prepended
    # to the LLM prompt so the model knows what was said earlier in the chat.
    # If this is the first message, history is None and the pipeline runs normally.
    history = (
        [{"role": m.role, "content": m.content} for m in body.messages[:-1]]
        if len(body.messages) > 1
        else None
    )

    result = await pipeline.run(
        query=query,
        query_type="topic",
        provider=body.provider,
        sources=body.sources,
        conversation_history=history,
    )
    return SearchResponse(
        query=result.query,
        type=result.query_type,
        brief=result.brief,
        eval=EvalResponse(**vars(result.eval)),
        sources=result.sources,
        meta={**result.meta, "rate_limit": key_data},
    )


@app.post("/keys/generate", response_model=KeyResponse, tags=["Auth"])
def create_key(plan: Literal["free", "pro"] = "free"):
    """
    Generate a new API key.

    - **free**: 10 requests/day
    - **pro**: 1000 requests/day (hook up Stripe here in prod)
    """
    limits = {"free": 10, "pro": 1000}
    key = generate_api_key(plan)
    return KeyResponse(
        api_key=key,
        plan=plan,
        daily_limit=limits[plan],
        note="Save this key — it won't be shown again. Add to Postgres to activate in prod.",
    )
