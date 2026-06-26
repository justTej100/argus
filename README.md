# Argus Study Buddy

Argus is a personal textbook RAG tool.

Upload PDFs, ask questions, and get answers with inline textbook citations in the form `[pX:sY]` so each claim is traceable to a page and sentence.

## Architecture

- FastAPI API and NiceGUI UI run in one Python process (`ui.run_with(app)`)
- Redis + RQ for background PDF ingestion jobs
- Supabase Storage for original PDFs
- Supabase Postgres + pgvector for chunk embeddings and metadata
- Gemini embeddings via `gemini-embedding-001`
- DeepSeek as default synthesis provider (`provider` can still be set to `gemini`)
- Optional subreddit context is separated and tagged as `source_type: community`

## File Map

- [backend/main.py](backend/main.py) is the app entrypoint: API routes, login, and NiceGUI pages.
- [backend/agents/IngestionAgent.py](backend/agents/IngestionAgent.py) handles PDF parsing, sentence splitting, chunking, and embeddings.
- [backend/agents/AnalysisAgent.py](backend/agents/AnalysisAgent.py) performs scoped vector retrieval.
- [backend/agents/ContextAgent.py](backend/agents/ContextAgent.py) fetches optional subreddit context.
- [backend/agents/SynthesisAgent.py](backend/agents/SynthesisAgent.py) builds the final response for each mode.
- [backend/agents/EvalAgent.py](backend/agents/EvalAgent.py) checks grounding and citation integrity.
- [backend/db/client.py](backend/db/client.py) owns the database pool and SQL helpers.
- [backend/storage.py](backend/storage.py) stores PDFs in Supabase or a local fallback.
- [backend/jobs.py](backend/jobs.py) enqueues ingestion jobs in RQ.
- [backend/auth.py](backend/auth.py) manages the session cookie.

## Implementation Notes

- Citation tags use the exact format `[pX:sY]` and are verified against the stored sentence table.
- Community context is never treated as textbook evidence.
- The app is designed for one person, so the auth and UI are intentionally simple.

## Agent Pipeline

1. IngestionAgent
   - Parse PDF with PyMuPDF
   - Split sentences with spaCy blank pipeline + sentencizer
   - Build overlapping sentence windows
   - Embed chunks and save with page/sentence metadata
2. AnalysisAgent
   - Resolve scope (`document`, `course`, or `library`)
   - Run pgvector similarity search over scoped documents
3. ContextAgent
   - If scope documents define `subreddits`, fetch supplementary Reddit context
4. SynthesisAgent
   - Modes: `chat`, `quiz`, `flashcards`, `summary`
   - Inject textbook chunks with citation tags
5. EvalAgent
   - Grounding check
   - Citation verification for every `[pX:sY]`

## Required Environment Variables

Use exactly these variables:

- `APP_PASSWORD`
- `REDIS_URL`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_BUCKET`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`

Optional for persistence and retrieval across restarts:

- `DATABASE_URL`

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
psql "$DATABASE_URL" -f backend/db/schema.sql
```

4. Run app + worker

```bash
make run
```

Or run separately:

```bash
make backend
make worker
```

## Routes

- `GET /health`
- `POST /auth/login`
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

1. Login with `APP_PASSWORD`
2. Upload a PDF in library page
3. Worker ingests and marks document `ready`
4. Ask a question in `/chat`
5. Answer contains `[pX:sY]` tags
6. Click a citation to open `/pdf/{document_id}?page=X`
