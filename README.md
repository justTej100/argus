# Argus

**Agentic RAG research pipeline — OSINT + trend analysis across Reddit, HN, GitHub, and the web.**

One search. Every public signal about a person or topic retrieved in parallel, embedded for semantic search, synthesized by AI, and grounding-checked before it reaches you.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-58a6ff?style=flat-square)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?style=flat-square)]()
[![pgvector](https://img.shields.io/badge/pgvector-semantic_search-4169e1?style=flat-square)]()
[![DeepSeek](https://img.shields.io/badge/AI-DeepSeek_%7C_Gemini-ff6b6b?style=flat-square)]()

---

## What it does

Search a topic or person. Get back an AI-generated brief grounded in real data from Reddit, HackerNews, GitHub, and the web — with a grounding score telling you how reliable the output is.

```bash
curl -X POST https://api.argus.dev/search \
  -H "x-api-key: demo-key-argus" \
  -H "Content-Type: application/json" \
  -d '{"query": "Vitalik Buterin", "type": "person", "provider": "deepseek"}'
```

```json
{
  "brief": "Vitalik Buterin has been most active on GitHub and Reddit...",
  "eval": {
    "passed": true,
    "score": 0.91,
    "claims_checked": 14,
    "claims_grounded": 13,
    "ungrounded_claims": []
  },
  "sources": [...],
  "meta": {
    "items_retrieved": 47,
    "grounding_score": 0.91,
    "search_duration_ms": 1240
  }
}
```

---

## Architecture

```
POST /search
     │
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
│  Generates grounded brief from context only         │
└─────────────────┬───────────────────────────────────┘
                  │  brief text
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
| `SynthesisAgent` | Generates brief via LLM | Prompt engineering |
| `EvalAgent` | Grounding check on the output | LLM-as-judge evals |

---

## AI Engineering concepts demonstrated

| Concept | Where | Why it matters |
|---------|-------|----------------|
| **Agentic systems** | `agents/pipeline.py` | 4 single-responsibility agents, composed into a pipeline |
| **RAG** | `AnalysisAgent` | Retrieved context injected into prompt — no hallucination from memory |
| **Embeddings + semantic search** | `ai/clients.py` + pgvector | Cosine similarity ranking, not keyword matching |
| **pgvector** | `db/schema.sql` + `db/client.py` | Vector search inside Postgres, `ivfflat` index |
| **LLM-as-judge evals** | `EvalAgent` | Second-pass grounding check, scores every output |
| **Switchable model providers** | `ai/clients.py` | DeepSeek + Gemini both via OpenAI-compatible endpoint |
| **API key auth + rate limiting** | `api/keys.py` | Redis sliding window, per-plan daily limits |

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
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── src/
│       └── app/
│           ├── layout.tsx            ← root layout, fonts, nav
│           ├── page.tsx              ← landing page (marketing + live demo)
│           ├── demo/
│           │   └── page.tsx          ← full demo UI (search, results, sources)
│           ├── docs/
│           │   └── page.tsx          ← API docs + code examples
│           └── components/
│               ├── SearchBar.tsx     ← query input + type/model toggles
│               ├── BriefCard.tsx     ← AI brief display
│               ├── SourcesList.tsx   ← sources with engagement stats
│               ├── GroundingBadge.tsx← score badge (green/yellow/red)
│               └── AgentStatus.tsx   ← live pipeline stage indicator
│
└── backend/                          ← FastAPI (Python)
    ├── requirements.txt
    ├── agents/
    │   └── pipeline.py               ← SearchAgent, AnalysisAgent, SynthesisAgent, EvalAgent
    ├── ai/
    │   └── clients.py                ← DeepSeek + Gemini clients + embed()
    ├── api/
    │   ├── main.py                   ← FastAPI routes
    │   └── keys.py                   ← API key auth + Redis rate limiting
    ├── db/
    │   ├── schema.sql                ← Postgres + pgvector schema
    │   └── client.py                 ← asyncpg helpers + semantic_search()
    └── scrapers/
        └── sources.py                ← Reddit, HN, GitHub, Exa, ScrapeCreators
```

---

## Sources

| Source | Needs key? | What you get |
|--------|-----------|-------------|
| Reddit | ❌ free | Posts, upvotes, comments |
| HackerNews | ❌ free | Stories, points, discussions |
| GitHub | ❌ free (token = higher limits) | Repos, stars, commit activity |
| Exa | ✅ `EXA_API_KEY` (1k free/month) | Semantic web search |
| TikTok/Instagram/X | ✅ `SCRAPECREATORS_API_KEY` (100 free) | Social posts + engagement |

Reddit, HN, and GitHub work with zero configuration.

---

## Setup — Backend

### Step 1 — Clone and install

```bash
git clone https://github.com/yourusername/argus
cd argus/backend
pip install -r requirements.txt
```

### Step 2 — Get a DeepSeek API key

1. Go to [platform.deepseek.com](https://platform.deepseek.com)
2. Sign up → API Keys → Create
3. Add $5 credit (you'll use maybe $0.10 testing this)

Or use Gemini — free tier available at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

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
cp .env.example .env
# fill in DEEPSEEK_API_KEY and DATABASE_URL at minimum
```

### Step 5 — Run the backend

```bash
cd backend
uvicorn api.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) — Swagger UI with every endpoint.

### Step 6 — Test it

```bash
curl -X POST http://localhost:8000/search \
  -H "x-api-key: demo-key-argus" \
  -H "Content-Type: application/json" \
  -d '{"query": "bitcoin ETF", "type": "topic", "provider": "deepseek"}'
```

---

## Setup — Frontend

### Step 1 — Install

```bash
cd argus/frontend
npm install
```

### Step 2 — Environment

```bash
cp .env.local.example .env.local
```

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000   # local dev
NEXT_PUBLIC_DEMO_KEY=demo-key-argus
```

### Step 3 — Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Pages

| Route | What it is |
|-------|-----------|
| `/` | Landing page — hero, live demo widget, feature breakdown, "Get API key" CTA |
| `/demo` | Full demo UI — search bar, agent status, brief output, sources panel, grounding badge |
| `/docs` | API reference — endpoints, request/response examples, code snippets in curl/Python/JS |

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

### Custom domain

Point `api.argus.dev` → Railway backend  
Point `argus.dev` → Vercel frontend  

---

## API Reference

### `POST /search`

**Headers:**
```
x-api-key: demo-key-argus
Content-Type: application/json
```

**Body:**
```json
{
  "query": "string",
  "type": "topic | person",
  "provider": "deepseek | gemini",
  "sources": ["reddit", "hackernews", "github", "exa", "tiktok"]
}
```

**Response:**
```json
{
  "query": "string",
  "type": "string",
  "brief": "AI-generated research brief",
  "eval": {
    "passed": true,
    "score": 0.91,
    "claims_checked": 14,
    "claims_grounded": 13,
    "ungrounded_claims": []
  },
  "sources": [
    {
      "source": "reddit",
      "title": "...",
      "url": "...",
      "engagement": { "upvotes": 2847, "comments": 312 }
    }
  ],
  "meta": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "sources_hit": ["reddit", "hackernews", "github"],
    "items_retrieved": 47,
    "items_in_context": 15,
    "grounding_score": 0.91,
    "search_duration_ms": 1240,
    "token_estimate": 3000
  }
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
| DeepSeek | — | ~$0.001 per full search |
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
- [ ] Streaming `/search/stream` SSE endpoint + frontend live updates
- [ ] Stripe for API key billing
- [ ] `/search/similar` — find past searches semantically similar to a new query
- [ ] Agent status websocket — frontend shows each agent completing in real time

---

## Stack

**Frontend:** Next.js 14 (App Router) · Tailwind CSS · TypeScript  
**Backend:** FastAPI · asyncpg · httpx · pgvector · Redis  
**AI:** DeepSeek API · Google Gemini API  
**DB:** PostgreSQL (Supabase) + pgvector extension  
**Deploy:** Vercel (frontend) · Railway (backend + Redis)  
**Sources:** Reddit · HackerNews · GitHub · Exa · ScrapeCreators
