-- Argus Postgres schema (applied on startup via db/client.init_schema)
-- Vector embeddings: PGVectorStore table `argus_vectors` (created separately)

CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    total_pages INTEGER NOT NULL DEFAULT 0,
    storage_path TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    subreddits TEXT[],
    has_scan_warning BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    flashcards_open BOOLEAN NOT NULL DEFAULT FALSE,
    embed_total INTEGER NOT NULL DEFAULT 0,
    embed_done INTEGER NOT NULL DEFAULT 0,
    embed_resume_at TIMESTAMPTZ,
    chunks_skipped INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS flashcards_open BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embed_total INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embed_done INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embed_resume_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunks_skipped INTEGER NOT NULL DEFAULT 0;

-- Guest study rate limits (keyed by email); table name kept for compatibility
CREATE TABLE IF NOT EXISTS chat_usage (
    email TEXT PRIMARY KEY,
    last_chat_at TIMESTAMPTZ,
    day_date DATE,
    day_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS flashcard_subscriptions (
    email TEXT NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (email, document_id)
);

CREATE INDEX IF NOT EXISTS flashcard_subscriptions_document_idx
    ON flashcard_subscriptions (document_id);

CREATE TABLE IF NOT EXISTS document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL,
    sort_key INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS document_sections_document_idx
    ON document_sections (document_id, sort_key);

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'textbook',
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    topic TEXT,
    avatar_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER,
    leetcode_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS posts_created_at_idx ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS posts_account_idx ON posts (account_id);
