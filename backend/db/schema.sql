-- Argus database schema
-- Run this once against your Postgres database before starting the backend.
--
-- Option A — psql:
--   psql "postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres" \
--     -f backend/db/schema.sql
--
-- Option B — Supabase dashboard:
--   SQL Editor → paste this file → Run
--
-- Requirements:
--   Postgres 14+  (gen_random_uuid() is built-in)
--   pgvector extension (included in Supabase free tier)

-- ── pgvector ──────────────────────────────────────────────────────────────
-- Adds the `vector` column type and the <=> cosine distance operator.
-- Must be enabled before creating any vector columns.
CREATE EXTENSION IF NOT EXISTS vector;

-- ── searches ─────────────────────────────────────────────────────────────
-- One row per pipeline run. Stores the query, the AI-generated answer,
-- and top-level metadata. source_items and eval_results link back here.
CREATE TABLE IF NOT EXISTS searches (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    query           TEXT        NOT NULL,
    query_type      TEXT        NOT NULL DEFAULT 'topic',   -- 'topic' | 'person'
    provider        TEXT        NOT NULL DEFAULT 'deepseek', -- 'deepseek' | 'gemini'
    brief           TEXT,                                   -- the AI-generated answer
    grounding_score FLOAT,                                  -- 0.0 – 1.0 from EvalAgent
    sources_hit     TEXT[],                                 -- e.g. ARRAY['reddit','hackernews']
    items_retrieved INTEGER,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── source_items ──────────────────────────────────────────────────────────
-- One row per retrieved post/repo/story. The embedding column is what
-- enables semantic search: you can query for items similar to a new
-- embedding without re-running the scrapers.
--
-- UNIQUE(item_id) deduplicates across searches — the same Reddit post
-- scraped twice only gets stored once, with the newer search_id.
CREATE TABLE IF NOT EXISTS source_items (
    id           SERIAL      PRIMARY KEY,
    search_id    UUID        REFERENCES searches(id) ON DELETE CASCADE,
    item_id      TEXT        NOT NULL UNIQUE,    -- MD5 of source+url (see sources.py)
    source       TEXT        NOT NULL,           -- 'reddit', 'hackernews', 'github', etc.
    title        TEXT,
    body         TEXT,
    url          TEXT,
    author       TEXT,
    container    TEXT,                           -- subreddit, org, channel, etc.
    published_at TEXT,                           -- unix timestamp string or ISO date
    engagement   JSONB       NOT NULL DEFAULT '{}',  -- upvotes, stars, comments, etc.
    metadata     JSONB       NOT NULL DEFAULT '{}',  -- source-specific extras
    embedding    vector(1536),                   -- 1536-dim DeepSeek embedding
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── eval_results ──────────────────────────────────────────────────────────
-- One row per EvalAgent run — the grounding check results for a search.
CREATE TABLE IF NOT EXISTS eval_results (
    id                SERIAL      PRIMARY KEY,
    search_id         UUID        REFERENCES searches(id) ON DELETE CASCADE,
    passed            BOOLEAN,
    score             FLOAT,
    claims_checked    INTEGER,
    claims_grounded   INTEGER,
    ungrounded_claims TEXT[],     -- the specific claims EvalAgent couldn't verify
    explanation       TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────

-- Fast lookup of items by search (used when loading a past search).
CREATE INDEX IF NOT EXISTS source_items_search_id_idx
    ON source_items (search_id);

-- Fast lookup of recent searches.
CREATE INDEX IF NOT EXISTS searches_created_at_idx
    ON searches (created_at DESC);

-- ivfflat index for fast approximate nearest-neighbor vector search.
-- This is what makes semantic_search() fast at scale.
--
-- How it works: divides the vector space into `lists` clusters (Voronoi cells).
-- At query time, only the nearest clusters are searched instead of every row.
--
-- lists=100 is a good default for up to ~1M vectors.
-- Rebuild the index (REINDEX) if you load a large batch of new vectors.
--
-- NOTE: this index requires at least one row in the table to be created.
-- If CREATE INDEX fails on an empty table, run it again after inserting data,
-- or use `CREATE INDEX ... WITH (lists = 1)` for development.
CREATE INDEX IF NOT EXISTS source_items_embedding_idx
    ON source_items
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
