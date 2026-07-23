# Argus

#TODO
- add a feat that looks up professional videos related to textbook concepts --> if LA then show LA lectures
Personal textbook social feed: doomscroll chapter personas, open cited PDF pages, generate chapter study packs (quiz / flashcards / summary) in-app or by email. Google sign-in; admins upload textbooks.

**Stack:** FastAPI · React/Vite · LangChain + Gemini · Supabase Postgres (pgvector) + Storage

---

## What it does

1. **Sign in** with Google (login page is the landing)
2. **Home feed** — Twitter-style doomscroll of textbook chapter accounts + seeded LeetCode accounts; open exact PDF pages from posts
3. **Upload** PDFs (admin) → junk-filtered chunking with **page + chapter** metadata → batched Gemini embeddings (pauses ~24h on rate limit, then resumes)
4. **Study** — pick textbook + chapter/section → generate quiz / flashcards / summary → view in-app and optionally email (guests rate-limited)
5. **Library / Admin** — manage textbooks and inspect vectors

Citations stay **page-level** (`[pN]`).

---

## Repo layout

```
argus/
├── main.py                 # FastAPI: API + React SPA
├── auth.py                 # Google OAuth + session cookies
├── rate_limit.py           # Guest study generation cooldown + daily cap
├── citations.py            # [pN] helpers
├── storage.py / jobs.py
├── frontend/               # React shell: left rail · feed · right news
├── agents/
│   ├── Pipeline.py         # Study RAG + EvalAgent
│   ├── IngestionAgent.py   # PDF → filter → sections → embed (resumable)
│   ├── FeedAgent.py        # Chapter personas + LeetCode seed posts
│   └── EvalAgent.py
├── ai/
│   ├── chunking.py         # Junk filter, chapters, split, prompt format
│   ├── vector_store.py     # PGVectorStore + batched embed resume
│   ├── study_generate.py   # quiz / flashcards / summary
│   ├── embeddings.py / llm.py / clients.py
├── db/                     # documents, sections, accounts, posts, schema
├── mail/gmail.py           # Study pack email
└── tests/
```

---

## Architecture

```text
Browser (React three-column shell)
    │  session cookie
    ▼
FastAPI (main.py)
    ├── /feed /news           Persona posts + right-rail status
    ├── /documents            PDFs + /sections
    ├── /study                Chapter-scoped study packs
    ├── /admin/*              DB stats
    └── /*                    SPA

Upload:
  PDF → extract → junk filter → document_sections
      → chunking (page + chapter metadata)
      → vector_store batches → argus_vectors
      → on 429: embedding_paused + resume ~24h
      → ready → FeedAgent chapter posts

Study:
  document + section → scoped similarity_search
      → study_generate (JSON) → EvalAgent → UI / email
```

**No Redis.** Ingestion + embed resume run in-process.

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

Open http://localhost:8000 → **Sign in with Google** → feed home → upload on **Library** → wait until **ready** → posts appear; use **Study** for chapter packs.

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
| `ADMIN_EMAIL` | Yes | Admin Google account(s) — unlimited study, upload/delete, `/admin` |
| `GUEST_STUDY_COOLDOWN_SECONDS` | Optional | Guest min seconds between study generations (default `300`) |
| `GUEST_STUDY_DAILY_LIMIT` | Optional | Guest max study generations per UTC day (default `10`) |
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
| `GEMINI_MODEL` | Optional | Study LLM (default `gemini-2.5-flash`) |
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

Admin Google address(es) with full access (upload, delete, database page, unlimited study). **Anyone** can sign in with Google as a guest; guests are rate-limited on study generation.

```env
ADMIN_EMAIL=you@gmail.com
```

Multiple admins: `you@gmail.com,partner@gmail.com`

Guest defaults: 1 study generation every 5 minutes and 10/day (`GUEST_STUDY_COOLDOWN_SECONDS`, `GUEST_STUDY_DAILY_LIMIT`).

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
- **Embeddings** — `models/gemini-embedding-001` at 3072 dimensions (batched; pauses ~24h on sustained 429)
- **Study generation** — `gemini-2.5-flash` by default (override with `GEMINI_MODEL`)

Free tier has daily limits; embedding jobs resume automatically after a pause.

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
4. In Study, pick a chapter, generate quiz/flashcards/summary, check **Email me**

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
| GET | `/me` | Yes | Email, `is_admin`, study quota |
| GET | `/feed` | Yes | Persona posts (newest first) |
| GET | `/news` | Yes | Right-rail status cards |
| GET | `/documents` | Yes | List textbooks |
| POST | `/documents` | Admin | Upload PDF |
| GET | `/documents/{id}/status` | Yes | Ingestion / embed status |
| GET | `/documents/{id}/sections` | Yes | Chapters for Study picker |
| GET | `/documents/{id}/file` | Yes | PDF bytes (viewer) |
| DELETE | `/documents/{id}` | Admin | Delete one book |
| POST | `/documents/bulk-delete` | Admin | Delete many |
| POST | `/study` | Yes | Chapter quiz/flashcards/summary (+ optional email) |
| GET | `/flashcards/offers` | Yes | Textbooks open for flashcard signup |
| POST | `/flashcards/subscribe` | Yes | Subscribe to a textbook's flashcards |
| POST | `/flashcards/unsubscribe` | Yes | Unsubscribe |
| POST | `/flashcards/broadcast` | Admin | Email flashcard deck to all subscribers |
| PATCH | `/documents/{id}/flashcards-open` | Admin | Open/close guest flashcard signup |
| GET | `/admin/config` | Admin | Supabase dashboard URLs |
| GET | `/admin/stats` | Admin | Document + vector counts |
| GET | `/admin/documents/{id}/chunks` | Admin | Sample chunks |

React pages: `/login`, `/` (feed), `/library`, `/study`, `/admin`

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
| Study / embed 429 | Gemini quota; study: wait for guest cooldown; embed: auto-resumes ~24h |
| DB connection error | URL-encode password in `DATABASE_URL`; wake paused Supabase project; copy a **fresh** URI from Dashboard → Database (error `tenant/user … not found` = wrong/old project ref). App falls back to in-memory if Postgres is unreachable. |
| Blank UI | Run `make frontend` before `make app`; need `frontend/dist` |
| Old books have no answers | Re-upload after LangChain migration — chunks live in `argus_vectors` |

---

## License

See [LICENSE](LICENSE).
