CREATE EXTENSION IF NOT EXISTS vector;

-- App metadata for uploaded textbooks. Vectors live in argus_vectors (LangChain PGVectorStore).
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    course TEXT,
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

CREATE INDEX IF NOT EXISTS documents_course_idx
    ON documents (course);
