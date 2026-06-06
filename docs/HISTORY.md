# PariKrama Development History

## Session: June 5, 2026

### **Phase 2 Complete: RAG Pipeline + Knowledge Base**
Today's session focused entirely on building out the intelligence layer (Phase 2), creating a production-grade Retrieval-Augmented Generation (RAG) pipeline to ground the AI agents in factual travel knowledge.

**Key Achievements:**
1. **RAG Core Implementation:**
   - Integrated `sentence-transformers` for embedding extraction using `all-MiniLM-L6-v2`.
   - Developed a robust chunking strategy in `chunker.py` using `RecursiveCharacterTextSplitter` tailored for English and Hindi (detecting purna viram)।
   - Built a `HybridRetriever` using `pgvector` for semantic cosine-similarity search, and PostgreSQL trigram (`pg_trgm`) for BM25-style keyword search.
   - Merged semantic and keyword search results using Reciprocal Rank Fusion (RRF), weighted 60/40.
   - Added an optional cross-encoder reranking step (`ms-marco-MiniLM-L-6-v2`) to boost precision on top-K results.

2. **Database & Services:**
   - Configured MinIO for secure document file storage (`storage_service.py`).
   - Extended the data models with `DocumentChunk` utilizing the Postgres `Vector(384)` type, and updated Alembic migrations (0002_document_chunks) to include `pg_trgm` and `vector` extensions, alongside HNSW and GIN indices.
   - Implemented a Celery background worker task (`document_tasks.py`) that asynchronously downloads PDFs from MinIO, extracts text via `PyMuPDF`, chunks, embeds, and stores the chunks directly in Postgres.

3. **API & Testing:**
   - Added REST APIs for document management (`/api/v1/documents/upload`, `list`, `get`, `delete`) and RAG searching (`/api/v1/rag/search`, `semantic`, `keyword`).
   - Wrote comprehensive tests for chunking, mock embedding, RRF math, and Document APIs.
   - Passed 51/51 automated tests (25 from Phase 1, 26 from Phase 2).

**Next Step:**
- **Phase 3:** LLM Router + Agent Foundation (Implementing the multi-model router with Gemini primary/Groq fallback, plus base agent structures).
