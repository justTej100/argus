# Argus Study Buddy

Argus is a personal textbook RAG tool.

Upload PDFs, ask questions, and get answers with inline textbook citations in the form `[pX:sY]` so each claim is traceable to a page and sentence.

## Architecture

- FastAPI API and NiceGUI UI run in one Python process (`ui.run_with(app)`)
- Redis + RQ for background PDF ingestion jobs
- Supabase Storage for original PDFs
- Supabase Postgres + pgvector for chunk embeddings and metadata
- pymupdf4llm for LaTeX/math-aware PDF → markdown extraction (with OCR fallback)
- Gemini embeddings via `gemini-embedding-001`
- DeepSeek as default synthesis provider (`provider` can still be set to `gemini`)
- Optional subreddit context is separated and tagged as `source_type: community`

## File Map

- [main.py](main.py) is the app entrypoint: API routes, login, and NiceGUI pages.
- [agents/IngestionAgent.py](agents/IngestionAgent.py) handles PDF parsing, sentence splitting, chunking, and embeddings.
- [agents/AnalysisAgent.py](agents/AnalysisAgent.py) performs scoped vector retrieval.
- [agents/SynthesisAgent.py](agents/SynthesisAgent.py) builds the final response for each mode.
- [agents/EvalAgent.py](agents/EvalAgent.py) checks grounding and citation integrity.
- [agents/ContextAgent.py](agents/ContextAgent.py) fetches optional community context.
- [db/client.py](db/client.py) owns the database pool and SQL helpers.
- [storage.py](storage.py) stores PDFs in Supabase or a local fallback.
- [jobs.py](jobs.py) enqueues ingestion jobs in RQ.
- [auth.py](auth.py) manages Google OAuth and the session cookie.
- [ui/theme.py](ui/theme.py) applies the ice/cyber NiceGUI theme and KaTeX rendering.

## Implementation Notes

- Citation tags use the exact format `[pX:sY]` and are verified against the stored sentence table.
- Community context is never treated as textbook evidence.
- LaTeX-heavy PDFs are ingested via pymupdf4llm markdown extraction instead of raw `get_text()`.
- Chat answers support `$...$` and `$$...$$` math rendered with KaTeX.

## Agent Pipeline

1. IngestionAgent
   - Extract per-page markdown with pymupdf4llm
   - OCR fallback for image-only pages
   - Split sentences with spaCy sentencizer
   - Build overlapping sentence windows and embed chunks
2. AnalysisAgent
   - Resolve scope (`document`, `course`, or `library`)
   - Run pgvector similarity search over scoped documents
3. ContextAgent
   - Optional supplementary community context (stub)
4. SynthesisAgent
   - Modes: `chat`, `quiz`, `flashcards`, `summary`
   - Inject textbook chunks with citation tags and LaTeX math in answers
5. EvalAgent
   - Grounding check
   - Citation verification for every `[pX:sY]`

## Required Environment Variables

Use exactly these variables:

- `SECRET_KEY`
- `ADMIN_EMAIL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `REDIS_URL`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_BUCKET`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`

Optional for persistence and retrieval across restarts:

- `DATABASE_URL`

### Google OAuth setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0 Client ID (Web application).
2. Add `GOOGLE_REDIRECT_URI` as an authorized redirect URI (default: `http://localhost:8000/auth/google/callback`).
3. Copy the client ID and secret into `.env`.
4. Set `ADMIN_EMAIL` to the Google account(s) allowed to sign in (comma-separated for multiple).

## Setup

1. Create env file

```bash
cp .env.example .env
```

2. Create virtual environment and install dependencies

```bash
make install
```

3. Apply DB schema if you want persistent storage

```bash
psql "$DATABASE_URL" -f db/schema.sql
```

4. Run app + worker

```bash
make run
```

Or run separately:

```bash
make app
make worker
```

5. Run tests

```bash
make test
```

## Routes

- `GET /health`
- `GET /auth/google`
- `GET /auth/google/callback`
- `GET /logout`
- `GET /documents`
- `POST /documents` (session required)
- `GET /documents/{id}/status`
- `GET /documents/{id}/file` (session required)
- `DELETE /documents/{id}` (session required)
- `POST /chat` (session required)
- `POST /search` (session required)

NiceGUI pages:

- `/login`
- `/` library
- `/chat` study view
- `/pdf/{document_id}` PDF viewer

## End-to-End Flow

1. Sign in with Google at `/login`
2. Upload a PDF in library page
3. Worker ingests and marks document `ready`
4. Ask a question in `/chat`
5. Answer contains `[pX:sY]` tags and optional LaTeX math
6. Click a citation to open `/pdf/{document_id}?page=X`
