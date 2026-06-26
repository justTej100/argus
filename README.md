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
├── ai/                  # Gemini client (embeddings + chat)
├── db/                  # Postgres/pgvector helpers + schema.sql
├── ui/                  # Ice/cyber NiceGUI theme + KaTeX
└── tests/
```

## Architecture

- **FastAPI + NiceGUI** in one process — no separate frontend
- **In-process background tasks** for PDF ingestion (no Redis, no worker process)
- **pymupdf4llm** for LaTeX/math-aware PDF extraction (OCR fallback on scan pages)
- **Gemini** for embeddings and chat (single AI provider)
- **Supabase Postgres + pgvector** when `DATABASE_URL` is set — schema applies automatically on startup
- **Supabase Storage** when `SUPABASE_URL` + `SUPABASE_KEY` are set — bucket is auto-created
- **Local fallbacks** when Supabase vars are omitted: in-memory DB + `uploaded_pdfs/` on disk

## Quick start

```bash
cp .env.example .env
# Fill in keys (see below) — minimum: auth + GEMINI_API_KEY
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
| `GEMINI_API_KEY` | Yes | PDF embeddings and chat answers |
| `DATABASE_URL` | Recommended | Postgres URI from Supabase **Connect** or **Settings → Database** |
| `SUPABASE_URL` | Optional | `https://xxxx.supabase.co` from **Settings → API → Project URL** |
| `SUPABASE_KEY` | Optional | **`service_role`** secret from **Settings → API** (not `anon`) |
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
2. Paste into `.env` — used for both ingestion embeddings and study chat.

### Supabase setup (database + PDF storage)

Argus uses Supabase for two things only:

| `.env` variable | What it is | Where to get it |
|-----------------|------------|-----------------|
| `DATABASE_URL` | Postgres connection string | **Connect** button (top of project) or **Project Settings → Database** |
| `SUPABASE_URL` | Your project’s API base URL | **Project Settings → API → Project URL** |
| `SUPABASE_KEY` | Server secret for Storage uploads | **Project Settings → API → `service_role`** (not `anon`) |

You do **not** need to create a Storage bucket, run `psql`, or enable pgvector manually — Argus applies the schema on startup and creates the `argus-pdfs` bucket on first upload.

#### Step 0 — Create a project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) and sign in.
2. Click **New project**.
3. Pick an organization, name, and region.
4. Set a **database password** — copy it somewhere safe. You need it for `DATABASE_URL` and cannot recover it later (only reset).
5. Wait until the project finishes provisioning (~1–2 minutes).

#### Step 1 — `DATABASE_URL` (Postgres)

**Option A — Connect button (easiest)**

1. Open your project in the dashboard.
2. Click the green **Connect** button (top center of the project home page).
3. Open the **ORMs** or **Connection string** tab.
4. Copy the **URI** connection string. It looks like:
   ```
   postgresql://postgres.[PROJECT_REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
   or a direct form:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
   ```
5. Replace `[YOUR-PASSWORD]` with the database password from Step 0 — **do not include the square brackets**, only the password itself.
6. If the password contains `@`, `#`, `%`, `!`, or other special characters, [URL-encode](https://www.urlencoder.org/) it before pasting (e.g. `@` → `%40`, `#` → `%23`).
7. Paste into `.env` as `DATABASE_URL=...`

**Option B — Project Settings**

1. Left sidebar → **Project Settings** (gear icon at the bottom).
2. Click **Database**.
3. Scroll to **Connection string** / **Connection info**.
4. Choose **URI**, copy the string, replace the password placeholder, paste into `DATABASE_URL`.

**Which string to use?** Any of **Session pooler**, **Direct connection**, or **Transaction pooler** works for Argus. If one fails to connect, try **Session pooler** (port `5432` on the pooler host) or **Direct connection**.

#### Step 2 — `SUPABASE_URL` (Project URL)

1. Left sidebar → **Project Settings** (gear).
2. Click **API** (some dashboards label this **Data API**).
3. Under **Project URL**, copy the value. It looks like:
   ```
   https://abcdefghijklmnop.supabase.co
   ```
4. Paste into `.env`:
   ```
   SUPABASE_URL=https://abcdefghijklmnop.supabase.co
   ```

#### Step 3 — `SUPABASE_KEY` (service role secret)

Stay on the same **Project Settings → API** page:

1. Find the **Project API keys** section.
2. Copy the **`service_role`** key (labeled **secret** — click **Reveal** if hidden).
3. Paste into `.env`:
   ```
   SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

**Important:** Use `service_role`, not `anon`. The `anon` key is for browsers; Argus runs on the server and needs `service_role` to upload PDFs.

**New-style keys:** If your dashboard shows `sb_secret_...` instead of a JWT, use the **secret** key marked for server/backend use (same role as `service_role`).

#### Example `.env` block

```env
DATABASE_URL=postgresql://postgres.xxxxxxxxxxxx:YOUR_DB_PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### What Argus does automatically

On `make app` with these set:

- Runs `db/schema.sql` against `DATABASE_URL` (tables + pgvector index)
- On first PDF upload, creates the `argus-pdfs` Storage bucket if missing

#### Skip Supabase for a quick trial

Leave all three blank. Argus uses in-memory data and stores PDFs in `uploaded_pdfs/` on disk. Everything is lost when you restart the app.

#### Supabase troubleshooting

| Problem | Fix |
|---------|-----|
| `does not appear to be an IPv4 or IPv6 address` | Malformed `DATABASE_URL` — usually an unencoded `@` in the password, or `[brackets]` left around the host/password from the Supabase template. URL-encode the password and remove placeholder brackets |
| `password authentication failed` | Wrong DB password in `DATABASE_URL` — reset under **Project Settings → Database → Reset database password**, then update `.env` |
| `connection refused` / timeout | Project may be paused (free tier) — open the dashboard to wake it; try **Session pooler** URI instead of Direct |
| Storage upload fails | `SUPABASE_KEY` must be `service_role` / secret key, not `anon` |
| `extension "vector" does not exist` | Rare on hosted Supabase (usually pre-enabled); contact Supabase support or enable **vector** in **Database → Extensions** |


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
- **Chat errors** — check `GEMINI_API_KEY`
- **DB errors on startup** — see [Supabase troubleshooting](#supabase-troubleshooting) below; check `DATABASE_URL` password and that the project is not paused
