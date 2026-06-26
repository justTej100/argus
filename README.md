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

Also required for DB access:

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

3. Apply DB schema

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
