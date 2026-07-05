# Argus Study Buddy

Personal textbook RAG app: upload PDFs, ask questions, get tutor-style answers with **page citations** (`[p12]`). Built for one student (you) — Google sign-in, minimal black/blue UI, embedded PDF viewer.

**Stack:** FastAPI backend · React frontend · LangChain RAG · Gemini · Supabase Postgres + Storage

---

## What it does

1. **Sign in** with Google (allowlisted email only)
2. **Upload** PDF textbooks → background ingestion extracts text, chunks by page, embeds with Gemini
3. **Study** in chat, quiz, flashcard, or summary mode — answers cite textbook pages
4. **View** the PDF in-panel; citation chips jump to the right page
5. **Inspect** the database on `/admin` (chunk counts, samples, links to Supabase dashboard)

Citations are **page-level** (`[pN]`), driven by LangChain `Document.metadata.page` on each chunk.

---

## Repo layout

```
argus/
├── main.py                 # FastAPI app: API routes + serves React build
├── auth.py                 # Google OAuth + signed session cookies
├── citations.py            # [pN] parsing, validation, email link helpers
├── storage.py              # PDF files: Supabase Storage or local disk
├── jobs.py                 # In-process background ingestion (no Redis)
├── Makefile
├── requirements.txt
│
├── frontend/               # React + Vite UI (Library, Study, Admin, Login)
│   └── src/
│       ├── api.ts          # fetch wrappers for backend routes
│       ├── pages/          # LibraryPage, StudyPage, AdminPage, LoginPage
│       └── components/     # PdfViewer, ConfirmDeleteModal, …
│
├── agents/
│   ├── Pipeline.py         # Orchestrates LangChain RAG + citation eval
│   ├── IngestionAgent.py   # PDF → page text → LangChain chunks → vector store
│   └── EvalAgent.py        # Checks answers are prose + page refs are valid
│
├── ai/
│   ├── langchain_rag.py    # Page splitting + prompt formatting (metadata blocks)
│   ├── langchain_store.py  # PGVectorStore table `argus_vectors`
│   ├── langchain_chain.py  # LCEL retrieve → Gemini chat / JSON modes
│   ├── langchain_embeddings.py
│   ├── langchain_llm.py
│   └── clients.py          # Low-level Gemini HTTP (retries, batch embed for tests)
│
├── db/
│   ├── client.py           # `documents` table CRUD + scope resolution
│   └── schema.sql          # Postgres schema (vectors managed by LangChain)
│
├── mail/gmail.py           # Optional flashcard email via Gmail SMTP
└── tests/
```

---

## Architecture

```text
Browser (React)
    │  session cookie
    ▼
FastAPI (main.py)
    ├── /auth/google          Google OAuth
    ├── /documents            upload, list, delete PDFs
    ├── /chat                 LangChain RAG pipeline
    ├── /admin/*              DB stats (read-only)
    └── /*                    React SPA (frontend/dist)

Upload flow:
  PDF → storage.py (Supabase or local)
      → IngestionAgent (pymupdf4llm extract)
      → langchain_rag.split_pages_to_chunks (metadata: page, title, course)
      → langchain_store → argus_vectors (PGVectorStore)

Question flow:
  query → langchain_store.similarity_search (scoped by textbook)
        → langchain_chain (Gemini tutor prompt)
        → EvalAgent (citation check)
        → JSON response → React UI
```

**No Redis, no separate worker.** Ingestion runs as a background task in the same process.

---

## Quick start

**Prerequisites:** Python 3.12+, Node 18+, npm

```bash
cp .env.example .env
# Fill in at minimum: SECRET_KEY, ADMIN_EMAIL, Google OAuth, GEMINI_API_KEY
# Recommended: DATABASE_URL + Supabase storage keys (see below)

make install          # Python venv + pip
make app              # builds React + starts http://localhost:8000
```

Open http://localhost:8000 → **Sign in with Google** → upload a PDF on **Library** → wait for status **ready** → **Study**.

### Development (hot reload UI)

Terminal 1 — API:

```bash
make install
.venv/bin/uvicorn main:app --reload --port 8000
```

Terminal 2 — Vite (proxies API to :8000):

```bash
make frontend-dev     # http://localhost:5173
```

---

## Environment variables

Copy `.env.example` to `.env`. Full key setup is below.

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | Yes | Signs session cookies |
| `ADMIN_EMAIL` | Yes | Google account(s) allowed to sign in (comma-separated) |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth secret |
| `GOOGLE_REDIRECT_URI` | Yes | `http://localhost:8000/auth/google/callback` (local) |
| `GEMINI_API_KEY` | Yes | Embeddings + chat (LangChain Google GenAI) |
| `DATABASE_URL` | Recommended | Supabase Postgres URI — vectors + document metadata |
| `SUPABASE_URL` | Recommended | Project URL for Storage + dashboard links |
| `SUPABASE_SERVICE_KEY` | Recommended | **service_role** secret (PDF uploads) |
| `STORAGE_BACKEND` | Optional | `local` (dev) or `supabase` (prod; default when `ENVIRONMENT=production`) |
| `SUPABASE_BUCKET` | Optional | Storage bucket name (default `argus-pdfs`) |
| `ENVIRONMENT` | Optional | `production` → secure cookies + supabase storage default |
| `GEMINI_MODEL` | Optional | Chat model (default `gemini-2.5-flash`) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Optional | Email flashcards to yourself |
| `APP_BASE_URL` | Optional | Base URL in email citation links |

**Aliases:** `SUPABASE_SERVICE_ROLE_KEY` works instead of `SUPABASE_SERVICE_KEY`. Legacy `SUPABASE_KEY` only if it is a service_role secret (not publishable/anon).

---

## How to get each key

### `SECRET_KEY`

Random string for cookie signing:

```bash
openssl rand -hex 32
```

### `ADMIN_EMAIL`

Your Google address(es):

```env
ADMIN_EMAIL=you@gmail.com
```

Multiple accounts: `you@gmail.com,partner@gmail.com`

### Google OAuth (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → create or select a project
2. **APIs & Services → OAuth consent screen** — configure; add yourself as a **test user** if app is in Testing mode
3. **Credentials → Create credentials → OAuth client ID → Web application**
4. **Authorized redirect URIs:** add exactly:
   - Local: `http://localhost:8000/auth/google/callback`
   - Production: `https://your-domain.com/auth/google/callback`
5. Copy **Client ID** → `GOOGLE_CLIENT_ID`, **Client secret** → `GOOGLE_CLIENT_SECRET`
6. Set `GOOGLE_REDIRECT_URI` to match the URI you registered

### `GEMINI_API_KEY`

1. Go to [Google AI Studio → API keys](https://aistudio.google.com/apikey)
2. **Create API key** (use an existing Google Cloud project or create one)
3. Paste into `.env` as `GEMINI_API_KEY`

Used for:
- **Embeddings** — `models/gemini-embedding-001` at 3072 dimensions (LangChain)
- **Chat** — `gemini-2.5-flash` by default (override with `GEMINI_MODEL`)

Free tier has daily limits; if chat fails with 429, wait or switch models in `.env`.

### Supabase (database + PDF storage)

Create a free project at [supabase.com/dashboard](https://supabase.com/dashboard).

#### `DATABASE_URL` (Postgres)

1. Open your project → click **Connect** (top) or **Project Settings → Database**
2. Copy the **URI** connection string, e.g.:
   ```text
   postgresql://postgres.[ref]:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
   ```
3. Replace `[PASSWORD]` with your database password (URL-encode special chars: `@` → `%40`, `#` → `%23`)
4. Paste as `DATABASE_URL=...`

On startup Argus runs `db/schema.sql` and creates the LangChain vector table `argus_vectors`.

#### `SUPABASE_URL`

1. **Project Settings → API**
2. Copy **Project URL** → `https://xxxx.supabase.co`

#### `SUPABASE_SERVICE_KEY` (Storage uploads)

1. Same **Project Settings → API** page
2. Under **Project API keys**, reveal the **`service_role`** / **secret** key (`eyJ...` or `sb_secret_...`)
3. Paste as `SUPABASE_SERVICE_KEY=...`

**Do not use the publishable/anon key** — it cannot upload files server-side.

#### `STORAGE_BACKEND`

| Value | When to use |
|-------|-------------|
| `local` | Dev without Supabase; PDFs in `uploaded_pdfs/` |
| `supabase` | Production (Render/Railway); PDFs in cloud bucket |

Production default: if `ENVIRONMENT=production`, storage is `supabase` unless you override.

#### Example Supabase block

```env
DATABASE_URL=postgresql://postgres.xxxx:YOUR_PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
STORAGE_BACKEND=supabase
SUPABASE_BUCKET=argus-pdfs
```

### Gmail flashcards (optional)

1. Use a Gmail account → [Google App Passwords](https://myaccount.google.com/apppasswords) (requires 2FA)
2. Create an app password for “Mail”
3. Set `GMAIL_USER=you@gmail.com` and `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`
4. In Study mode, generate flashcards and check **Email flashcards** or use **Email last flashcards**

---

## Make commands

| Command | Description |
|---------|-------------|
| `make install` | Create `.venv`, install Python deps |
| `make frontend` | `npm install` + build React to `frontend/dist` |
| `make frontend-dev` | Vite dev server on :5173 (proxy to API) |
| `make app` | Build frontend + run FastAPI on :8000 |
| `make test` | Run pytest |
| `make stop` | Kill process on port 8000 |

---

## API routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/auth/google` | No | Start OAuth |
| GET | `/logout` | No | Clear session |
| GET | `/documents` | No | List textbooks |
| POST | `/documents` | Yes | Upload PDF |
| GET | `/documents/{id}/status` | No | Ingestion status |
| GET | `/documents/{id}/file` | Yes | PDF bytes (viewer) |
| DELETE | `/documents/{id}` | Yes | Delete one book |
| POST | `/documents/bulk-delete` | Yes | Delete many |
| POST | `/chat` | Yes | Ask question (RAG) |
| GET | `/admin/config` | Yes | Supabase dashboard URLs |
| GET | `/admin/stats` | Yes | Document + vector counts |
| GET | `/admin/documents/{id}/chunks` | Yes | Sample chunks |

React pages: `/login`, `/` (library), `/study`, `/admin`

---

## Deploy (Render / Railway)

One web service:

**Build:**
```bash
cd frontend && npm install && npm run build
pip install -r requirements.txt
```

**Start:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Env:** set all production vars; `GOOGLE_REDIRECT_URI` must match your live URL; `ENVIRONMENT=production`; `STORAGE_BACKEND=supabase`; `DATABASE_URL` + `SUPABASE_SERVICE_KEY`.

After deploy, **re-upload textbooks** if migrating from an older schema so vectors land in `argus_vectors`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Login redirect error | `GOOGLE_REDIRECT_URI` must match Google Console exactly |
| 401 on Study/Library | Sign in again; check `SECRET_KEY` did not change mid-session |
| Upload fails (storage) | Use `SUPABASE_SERVICE_KEY`, not publishable key; set `STORAGE_BACKEND=supabase` |
| Stuck on `processing` | Check terminal logs; usually `GEMINI_API_KEY` or PDF extract failure |
| Chat 429 / 503 | Gemini quota or outage; retry or change `GEMINI_MODEL` |
| DB connection error | URL-encode password in `DATABASE_URL`; wake paused Supabase project |
| Blank UI | Run `make frontend` before `make app`; need `frontend/dist` |
| Old books have no answers | Re-upload after LangChain migration — chunks live in `argus_vectors` |

---

## License

See [LICENSE](LICENSE).
