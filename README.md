# Argus

**ChatGPT for fresh ideas — multi-turn chat grounded in real posts from Reddit, HN, and GitHub.**

Ask anything. Argus scrapes the internet in real time, ranks what's most relevant using embeddings, and gives you an AI answer built entirely from actual posts — not its training data. Every response shows you exactly which posts it read.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-58a6ff?style=flat-square)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?style=flat-square)]()
[![pgvector](https://img.shields.io/badge/pgvector-semantic_search-4169e1?style=flat-square)]()
[![DeepSeek](https://img.shields.io/badge/AI-DeepSeek_%7C_Gemini-ff6b6b?style=flat-square)]()

---

## Quick Start

**You need:** Python 3.12+, Node 18+.

```bash
# 1. Clone
git clone https://github.com/yourusername/argus
cd argus

# 2. Create your .env (one file, used by both backend and frontend)
cp .env.example .env
# Open .env and add at least one AI key (DEEPSEEK_API_KEY or GEMINI_API_KEY)

# 3. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload   # → http://localhost:8000

# 4. Frontend (new terminal, from the argus/ root)
cd frontend
npm install
npm run dev                 # → http://localhost:3000
```

Open [http://localhost:3000](http://localhost:3000) — the chat UI is the homepage.

**Preview mode (zero keys):** The app runs without any API keys — scraping and RAG still work, but AI synthesis returns a placeholder message instead of a real answer. Add `DEEPSEEK_API_KEY` or `GEMINI_API_KEY` to `.env` to unlock full responses.

All variables are documented in `.env.example`. `DATABASE_URL`, `GITHUB_TOKEN`, `EXA_API_KEY`, and `SCRAPECREATORS_API_KEY` are all optional.

---

## What it does

Type a question. Argus fans out to Reddit, HackerNews, and GitHub simultaneously, embeds and ranks the results by semantic relevance, then has DeepSeek or Gemini answer your question based solely on what it found. The UI shows you every source post — title, subreddit, upvotes, body excerpt, and a direct link — right below the answer.

Ask a follow-up. The full conversation history is passed back to the pipeline so the AI can answer in context, while every reply still pulls fresh data.

```bash
curl -X POST https://api.argus.dev/chat \
  -H "x-api-key: demo-key-argus" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What are devs saying about AI coding tools?"}],
    "provider": "deepseek"
  }'
```

```json
{
  "brief": "On HN, the most upvoted thread this week argues that Cursor has changed...",
  "eval": {
    "passed": true,
    "score": 0.93,
    "claims_checked": 11,
    "claims_grounded": 10,
    "ungrounded_claims": []
  },
  "sources": [
    {
      "source": "hackernews",
      "title": "Cursor is the first IDE that actually...",
      "url": "https://news.ycombinator.com/item?id=...",
      "body": "I've been using it for 3 months and the tab completion alone...",
      "container": "HackerNews",
      "published_at": "1748200000",
      "engagement": { "points": 847, "comments": 312 }
    }
  ],
  "meta": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "items_retrieved": 43,
    "items_in_context": 15,
    "grounding_score": 0.93,
    "search_duration_ms": 1190
  }
}
```

---

## Architecture

```
POST /chat  (or /search for single-turn)
     │
     │  messages array (full conversation history)
     ▼
┌─────────────────────────────────────────────────────┐
│  SearchAgent  (parallel fan-out)                    │
│  Reddit · HackerNews · GitHub · Exa · ScrapeCreators│
│  asyncio.gather — all sources hit simultaneously    │
└─────────────────┬───────────────────────────────────┘
                  │  N SourceItems (normalized schema)
                  ▼
┌─────────────────────────────────────────────────────┐
│  AnalysisAgent  (RAG retrieval)                     │
│  Embed query + items → cosine similarity rank       │
│  Select top-15 most relevant as context window      │
│  pgvector stores embeddings for semantic reuse      │
└─────────────────┬───────────────────────────────────┘
                  │  12k char context window
                  ▼
┌─────────────────────────────────────────────────────┐
│  SynthesisAgent                                     │
│  DeepSeek or Gemini — hot-swappable via provider=   │
│  Conversation history injected for multi-turn chat  │
│  Answers from context only — no hallucination       │
└─────────────────┬───────────────────────────────────┘
                  │  answer text
                  ▼
┌─────────────────────────────────────────────────────┐
│  EvalAgent  (LLM-as-judge grounding check)          │
│  Extracts factual claims → checks against sources   │
│  Returns score 0.0–1.0 + ungrounded claim list      │
└─────────────────────────────────────────────────────┘
```

### The 4 Agents

| Agent | What it does | Key pattern |
|-------|-------------|-------------|
| `SearchAgent` | Fans out to all scrapers simultaneously | `asyncio.gather` |
| `AnalysisAgent` | Embeds + ranks by semantic similarity | RAG / cosine similarity |
| `SynthesisAgent` | Generates answer via LLM with conversation context | Prompt engineering + multi-turn |
| `EvalAgent` | Grounding check on the output | LLM-as-judge evals |

---

## AI Engineering concepts demonstrated

| Concept | Where | Why it matters |
|---------|-------|----------------|
| **Agentic systems** | `agents/Pipeline.py` | 4 single-responsibility agents, composed into a pipeline |
| **RAG** | `AnalysisAgent` | Retrieved context injected into prompt — answers come from real posts, not model memory |
| **Multi-turn RAG chat** | `POST /chat` + `SynthesisAgent` | Conversation history threaded through the pipeline so follow-ups work |
| **Embeddings + semantic search** | `clients.py` + pgvector | Cosine similarity ranking, not keyword matching |
| **pgvector** | `db/schema.sql` + `db_client.py` | Vector search inside Postgres, `ivfflat` index |
| **LLM-as-judge evals** | `EvalAgent` | Second-pass grounding check, scores every output |
| **Switchable model providers** | `clients.py` | DeepSeek + Gemini both via OpenAI-compatible endpoint |
| **API key auth + rate limiting** | `keys.py` | Redis sliding window, per-plan daily limits |

---

## File structure

```
argus/
├── .env.example
├── .gitignore
├── README.md
│
├── frontend/                         ← Next.js 14 (App Router)
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.js
│   └── app/
│       ├── layout.tsx                ← root layout, fonts, nav
│       ├── page.tsx                  ← chat UI (sidebar, bubbles, sources strip)
│       ├── demo/
│       │   └── page.tsx              ← single-query demo with pipeline visualizer
│       └── docs/
│           └── page.tsx              ← API reference + code examples
│
└── backend/                          ← FastAPI (Python)
    ├── requirements.txt
    ├── main.py                       ← FastAPI routes (POST /chat, POST /search, etc.)
    ├── clients.py                    ← DeepSeek + Gemini clients + embed()
    ├── sources.py                    ← Reddit, HN, GitHub, Exa, ScrapeCreators scrapers
    ├── db_client.py                  ← asyncpg helpers + semantic_search()
    └── agents/
        ├── Pipeline.py               ← orchestrates the 4 agents
        ├── SearchAgent.py            ← parallel scraper fan-out
        ├── AnalysisAgent.py          ← embed + RAG ranking
        ├── SynthesisAgent.py         ← LLM synthesis with conversation history
        └── EvalAgent.py              ← LLM-as-judge grounding check
```

---

## Sources

| Source | Needs key? | What you get |
|--------|-----------|-------------|
| Reddit | free | Posts, upvotes, comments, subreddit |
| HackerNews | free | Stories, points, discussions |
| GitHub | free (token = higher limits) | Repos, stars, commit activity |
| Exa | `EXA_API_KEY` (1k free/month) | Semantic web search |
| TikTok/Instagram/X | `SCRAPECREATORS_API_KEY` (100 free) | Social posts + engagement |

Reddit, HN, and GitHub work with zero configuration.

---

## Setup — Backend

### Step 1 — Clone and install

```bash
git clone https://github.com/yourusername/argus
cd argus/backend
pip install -r requirements.txt
```

### Step 2 — Get an AI API key

**DeepSeek** (recommended — cheap and fast):
1. Go to [platform.deepseek.com](https://platform.deepseek.com)
2. Sign up → API Keys → Create
3. Add $5 credit (you'll use maybe $0.10 testing this)

**Gemini** (free tier):
- [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — 1M tokens/day free

### Step 3 — Set up Supabase (Postgres + pgvector)

1. Go to [supabase.com](https://supabase.com) → New Project
2. Settings → Database → Connection string → URI — copy it
3. Run the schema:

```bash
# Option A — psql
psql "postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres" \
  -f backend/db/schema.sql

# Option B — Supabase dashboard
# SQL Editor → paste contents of backend/db/schema.sql → Run
```

### Step 4 — Configure environment

```bash
# From the argus/ root (if you haven't already)
cp .env.example .env
# Fill in DEEPSEEK_API_KEY or GEMINI_API_KEY at minimum.
# Everything else is optional.
```

### Step 5 — Run

```bash
cd backend
uvicorn main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) — Swagger UI with every endpoint.

### Step 6 — Test the chat endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "x-api-key: demo-key-argus" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "what are people saying about rust?"}], "provider": "deepseek"}'
```

---

## Setup — Frontend

### Step 1 — Install

```bash
cd argus/frontend
npm install
```

### Step 2 — Environment

No separate frontend env file needed. `next.config.ts` reads the root `argus/.env`
automatically. If you need to override just the frontend vars, you can add them to
the root `.env`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000   # default
NEXT_PUBLIC_DEMO_KEY=demo-key-argus         # default
```

### Step 3 — Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Pages

| Route | What it is |
|-------|-----------|
| `/` | Chat UI — sidebar, multi-turn conversation, sources strip below every answer |
| `/demo` | Single-query demo — pipeline visualizer, full sources panel, grounding breakdown |
| `/docs` | API reference — endpoints, request/response examples, code snippets |

---

## Deploy

### Backend → Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Add a Redis service: New → Database → Redis
3. Set env vars in Railway dashboard (same as `.env`)
4. Railway auto-detects FastAPI — deploys automatically on push

### Frontend → Vercel

```bash
cd frontend
npx vercel
```

Set `NEXT_PUBLIC_API_URL` to your Railway backend URL in Vercel dashboard.

---

## API Reference

### `POST /chat` — multi-turn chat

Send the full conversation history. The last user message is used as the search query; prior messages are injected into the synthesis prompt so follow-ups work naturally.

**Headers:**
```
x-api-key: demo-key-argus
Content-Type: application/json
```

**Body:**
```json
{
  "messages": [
    {"role": "user", "content": "What are people saying about Rust?"},
    {"role": "assistant", "content": "On HN, the conversation is mostly about..."},
    {"role": "user", "content": "Which post had the most upvotes?"}
  ],
  "provider": "deepseek | gemini",
  "sources": ["reddit", "hackernews", "github"]
}
```

**Response:**
```json
{
  "brief": "AI answer grounded in freshly scraped posts",
  "eval": {
    "passed": true,
    "score": 0.93,
    "claims_checked": 11,
    "claims_grounded": 10,
    "ungrounded_claims": []
  },
  "sources": [
    {
      "source": "reddit",
      "title": "Why I switched from Go to Rust for my side project",
      "url": "https://reddit.com/r/rust/...",
      "body": "After 6 months the borrow checker finally clicked...",
      "author": "u/somedev",
      "container": "r/rust",
      "published_at": "1748100000",
      "engagement": { "upvotes": 1842, "comments": 204 }
    }
  ],
  "meta": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "items_retrieved": 38,
    "items_in_context": 15,
    "grounding_score": 0.93,
    "search_duration_ms": 1140
  }
}
```

### `POST /search` — single-turn (original endpoint, still available)

```json
{
  "query": "string",
  "type": "topic | person",
  "provider": "deepseek | gemini",
  "sources": ["reddit", "hackernews", "github", "exa", "tiktok"]
}
```

### `POST /keys/generate`

```bash
curl -X POST "http://localhost:8000/keys/generate?plan=free"
# returns { "api_key": "argus-fre-...", "plan": "free", "daily_limit": 10 }
```

### `GET /health`

```json
{ "status": "ok", "timestamp": 1234567890 }
```

---

## Cost to run

| Service | Free tier | Notes |
|---------|-----------|-------|
| DeepSeek | — | ~$0.001 per chat message |
| Gemini | 1M tokens/day | Free tier covers development |
| Supabase | 500MB | pgvector included |
| Railway | $5/mo credit | Covers backend + Redis |
| Vercel | Unlimited hobby | Free for frontend |
| Exa | 1000 searches/mo | Free tier |
| ScrapeCreators | 100 credits | Free tier |

**Total to ship: ~$0.** Production with real traffic: ~$10/mo.

---

## Roadmap

- [ ] Persist embeddings to Postgres (semantic search across history)
- [ ] Redis rate limiting (replace in-memory fallback)
- [ ] X/Twitter via ScrapeCreators
- [ ] Streaming `POST /chat/stream` SSE endpoint + frontend streaming text
- [ ] Persist chat sessions to Postgres (load past conversations)
- [ ] Stripe for API key billing
- [ ] Agent status websocket — real-time pipeline stage updates in the UI

---

## Stack

**Frontend:** Next.js 14 (App Router) · Tailwind CSS · TypeScript  
**Backend:** FastAPI · asyncpg · httpx · pgvector · Redis  
**AI:** DeepSeek API · Google Gemini API  
**DB:** PostgreSQL (Supabase) + pgvector extension  
**Deploy:** Vercel (frontend) · Railway (backend + Redis)  
**Sources:** Reddit · HackerNews · GitHub · Exa · ScrapeCreators
