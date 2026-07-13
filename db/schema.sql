-- Argus Postgres schema (applied on startup via db/client.init_schema)
-- Vector embeddings: LangChain PGVectorStore table `argus_vectors` (created separately)

CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'error')),
    total_pages INTEGER NOT NULL DEFAULT 0,
    storage_path TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    subreddits TEXT[],
    has_scan_warning BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    flashcards_open BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

-- Migrate existing databases that still have course instead of description
ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT;

-- Guest chat rate limits (keyed by email)
CREATE TABLE IF NOT EXISTS chat_usage (
    email TEXT PRIMARY KEY,
    last_chat_at TIMESTAMPTZ,
    day_date DATE,
    day_count INTEGER NOT NULL DEFAULT 0
);

-- Admin can open a textbook for guest flashcard signup
ALTER TABLE documents ADD COLUMN IF NOT EXISTS flashcards_open BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS flashcard_subscriptions (
    email TEXT NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (email, document_id)
);

CREATE INDEX IF NOT EXISTS flashcard_subscriptions_document_idx
    ON flashcard_subscriptions (document_id);
