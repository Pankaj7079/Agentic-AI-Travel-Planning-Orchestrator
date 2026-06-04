-- PariKrama database initialization
-- Runs once when the PostgreSQL container is created for the first time.

-- pgvector for embedding storage (RAG pipeline)
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_trgm for fuzzy text / keyword search (BM25-like)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- uuid-ossp for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify all extensions loaded
DO $$
BEGIN
  RAISE NOTICE 'pgvector version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
  RAISE NOTICE 'All PariKrama extensions loaded successfully';
END $$;
