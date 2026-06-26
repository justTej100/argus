CREATE EXTENSION IF NOT EXISTS vector;

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

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    sentence_start_idx INTEGER NOT NULL,
    sentence_end_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(3072) NOT NULL,
    bbox JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_sentences (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    sentence_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, page_number, sentence_idx)
);

CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS documents_course_idx
    ON documents (course);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON document_chunks (document_id);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON document_chunks
    USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);

CREATE INDEX IF NOT EXISTS sentences_lookup_idx
    ON document_sentences (document_id, page_number, sentence_idx);
