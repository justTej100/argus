# Argus Study Buddy

Argus is a personal textbook RAG tool. Upload PDFs, ask questions, and get answers with inline citations in the form `[pX:sY]` so each claim is traceable to a page and sentence.

Sign in with Google, upload textbooks, and study in chat/quiz/flashcard/summary modes. Answers can include LaTeX math (`$...$`) rendered with KaTeX.

## Repo layout

```
argus/
├── main.py              # FastAPI + NiceGUI entrypoint
├── auth.py              # Google OAuth + session cookies
├── jobs.py              # In-process background ingestion
├── storage.py           # PDF storage (Supabase or local fallback)
├── requirements.txt
├── Makefile
├── agents/              # Ingestion, retrieval, synthesis, eval pipeline
├── ai/                  # Gemini + DeepSeek clients
├── db/                  # Postgres/pgvector helpers + schema.sql
├── ui/                  # Ice/cyber NiceGUI theme + KaTeX
└── tests/
```

## Architecture

- **FastAPI + NiceGUI** in one process — no separate frontend
- **In-process background tasks** for PDF ingestion (no Redis, no worker process)
- **pymupdf4llm** for LaTeX/math-aware PDF extraction (OCR fallback on scan pages)
- **Gemini** for embeddings; **DeepSeek** default for chat (Gemini optional)
- **Supabase Postgres + pgvector** when `DATABASE_URL` is set — schema applies automatically on startup
- **Supabase Storage** when `SUPABASE_URL` + `SUPABASE_KEY` are set — bucket is auto-created
- **Local fallbacks** when Supabase vars are omitted: in-memory DB + `uploaded_pdfs/` on disk

## Quick start

```bash
cp .env.example .env
# Fill in keys (see below) — minimum: auth + GEMINI + DEEPSEEK
make install
make app          # http://localhost:8000
```

Open `/login`, sign in with Google, upload a PDF, go to `/chat`.

**You do not need Redis.** One command (`make app`) runs everything.

---

## Environment variables

| Variable | Required? | What it does |
|----------|-----------|--------------|
| `SECRET_KEY` | Yes | Signs session cookies |
| `ADMIN_EMAIL` | Yes | Google account(s) allowed to sign in (comma-separated) |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth |
| `GOOGLE_REDIRECT_URI` | Yes | Default: `http://localhost:8000/auth/google/callback` |
| `GEMINI_API_KEY` | Yes | PDF embeddings |
| `DEEPSEEK_API_KEY` | Yes* | Chat answers (*or use Gemini as provider) |
| `DATABASE_URL` | Recommended | Postgres persistence — schema auto-applies on startup |
| `SUPABASE_URL` | Optional | Cloud PDF storage |
| `SUPABASE_KEY` | Optional | Cloud PDF storage (service role key) |
| `ENVIRONMENT` | Optional | Set to `production` for secure cookies |

No `REDIS_URL`. No `SUPABASE_BUCKET` (defaults to `argus-pdfs`, created automatically). No manual `psql` step.

---

## How to get each key

### `SECRET_KEY`

```bash
openssl rand -hex 32
```

### `ADMIN_EMAIL`

Your Google address(es), comma-separated:

```
ADMIN_EMAIL=you@gmail.com
```

### Google OAuth

1. [Google Cloud Console](https://console.cloud.google.com/) → create/select a project
2. **APIs & Services → OAuth consent screen** — configure, add yourself as a test user if in Testing mode
3. **Credentials → Create → OAuth client ID → Web application**
4. Authorized redirect URI: `http://localhost:8000/auth/google/callback`
5. Copy **Client ID** → `GOOGLE_CLIENT_ID`, **Client secret** → `GOOGLE_CLIENT_SECRET`

### `GEMINI_API_KEY`

1. [Google AI Studio](https://aistudio.google.com/apikey) → **Create API key**
2. Paste into `.env`

### `DEEPSEEK_API_KEY`

1. [DeepSeek Platform](https://platform.deepseek.com/) → **API Keys** → create one
2. Paste into `.env`

### Supabase (persistence) — copy two values, nothing else

For data that survives restarts:

1. Create a free project at [supabase.com](https://supabase.com/)
2. **Project Settings → Database → Connection string** (URI) → `DATABASE_URL`
3. **Project Settings → API → Project URL** → `SUPABASE_URL`
4. **Project Settings → API → service_role** (secret) → `SUPABASE_KEY`

That's it. On first `make app`:

- `db/schema.sql` runs automatically against `DATABASE_URL`
- PDF bucket `argus-pdfs` is created automatically when you upload

Skip Supabase entirely for a quick local trial — the app uses in-memory storage and `uploaded_pdfs/` on disk (data lost on restart).

---

## Setup

```bash
cp .env.example .env
# edit .env
make install
make app
make test    # optional
```

## Make commands

| Command | Description |
|---------|-------------|
| `make install` | Create `.venv`, install deps |
| `make app` | Run the app on port 8000 |
| `make run` | Same as `make app` |
| `make test` | Run pytest |
| `make stop` | Kill process on port 8000 |

## Routes & UI

**API:** `/health`, `/auth/google`, `/logout`, `/documents`, `/documents/bulk-delete`, `/chat`, `/search`

**Pages:** `/login`, `/` (library), `/chat` (study), `/pdf/{id}` (viewer)

## End-to-end flow

1. Sign in at `/login`
2. Upload a PDF on the library page — ingestion runs in the background inside the same process
3. Poll until status is `ready`
4. On the library page, check the books you want to remove, click **Delete selected**, and confirm in the dialog
5. Ask questions in `/chat` with `[pX:sY]` citations

## Troubleshooting

- **Login fails** — `GOOGLE_REDIRECT_URI` must match Google Cloud Console exactly
- **Upload stuck on `processing`** — check terminal for ingestion errors (usually `GEMINI_API_KEY`)
- **Chat errors** — check `DEEPSEEK_API_KEY`
- **DB errors on startup** — verify `DATABASE_URL`; ensure Supabase project is awake
