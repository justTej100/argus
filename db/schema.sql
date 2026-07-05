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
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

-- Migrate existing databases that still have course instead of description
ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT;
