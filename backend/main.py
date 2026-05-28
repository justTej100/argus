"""
Argus — FastAPI app.
Docs auto-generated at /docs once running.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load the single root .env (argus/.env) regardless of where uvicorn is invoked from.
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.pipeline import ResearchPipeline
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = ResearchPipeline()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    type: Literal["topic", "person"] = "topic"
    provider: Literal["deepseek", "gemini"] = "deepseek"
    sources: list[str] | None = None

    model_config = {
        "json_schema_extra": {
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
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
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
    passed: bool
    score: float
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]
    explanation: str


class SearchResponse(BaseModel):
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
    return {
        "name": "Argus API",
        "version": "1.0.0",
        "demo_key": "demo-key-argus",
        "docs": "/docs",
        "endpoints": {
            "POST /search": "Run the full agentic RAG pipeline",
            "POST /keys/generate": "Generate an API key",
            "GET /health": "Health check",
        },
    }


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/search", response_model=SearchResponse, tags=["Research"])
async def search(
    body: SearchRequest,
    key_data: dict = Depends(verify_api_key),
):
    """
    Run the full research pipeline:

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
        eval=EvalResponse(**vars(result.eval)),
        sources=result.sources,
        meta={**result.meta, "rate_limit": key_data},
    )


@app.post("/chat", response_model=SearchResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    key_data: dict = Depends(verify_api_key),
):
    """
    Multi-turn chat endpoint. Send the full conversation history and get back
    an AI response grounded in freshly scraped Reddit, HN, and GitHub data.

    The last `user` message is used as the search query. Prior messages are
    injected into the synthesis prompt so follow-up questions work naturally.
    """
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="At least one user message is required.")

    query = user_messages[-1].content

    # All messages except the final user message become conversation history
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