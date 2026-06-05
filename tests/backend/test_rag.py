"""
Phase 2 Tests: RAG chunker, embedder, RRF fusion, and document API.

These tests cover the RAG pipeline core logic without requiring a live DB
for unit tests, and use the test DB fixture for integration tests.

Test categories:
    Unit: chunker, embeddings (mock), RRF math
    Integration: document upload/list/delete API via HTTP client
"""

from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

from httpx import AsyncClient

# ── Unit Tests: Chunker ────────────────────────────────────────────────────────


class TestChunker:
    """Tests for the document chunking logic."""

    def test_chunk_text_returns_list(self):
        """chunk_text should return a non-empty list of dicts."""
        from parikrama.rag.chunker import chunk_text

        text = "Manali is a beautiful hill station in Himachal Pradesh. " * 50
        chunks = chunk_text(text)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunk_dict_has_required_keys(self):
        """Each chunk dict must have content, chunk_index, token_count, metadata."""
        from parikrama.rag.chunker import chunk_text

        text = "Hello world. " * 200
        chunks = chunk_text(text)
        for chunk in chunks:
            assert "content" in chunk
            assert "chunk_index" in chunk
            assert "token_count" in chunk
            assert "metadata" in chunk

    def test_chunk_indices_are_sequential(self):
        """Chunk indices must be monotonically increasing starting from 0."""
        from parikrama.rag.chunker import chunk_text

        text = "Travel guide for Manali. " * 200
        chunks = chunk_text(text)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_respects_max_size(self):
        """No chunk should exceed 2x the configured chunk size in characters."""
        from parikrama.rag.chunker import CHUNK_SIZE_CHARS, chunk_text

        text = "The quick brown fox jumps over the lazy dog. " * 500
        chunks = chunk_text(text)
        for chunk in chunks:
            assert len(chunk["content"]) <= CHUNK_SIZE_CHARS * 2, (
                f"Chunk too large: {len(chunk['content'])} chars"
            )

    def test_chunk_metadata_is_merged(self):
        """Caller-provided metadata should appear in every chunk's metadata."""
        from parikrama.rag.chunker import chunk_text

        text = "Manali hotels. " * 100
        meta = {"destination": "Manali", "source": "test"}
        chunks = chunk_text(text, metadata=meta)
        for chunk in chunks:
            assert chunk["metadata"]["destination"] == "Manali"
            assert chunk["metadata"]["source"] == "test"

    def test_chunk_empty_text_returns_empty(self):
        """Empty or whitespace-only input should return an empty list."""
        from parikrama.rag.chunker import chunk_text

        assert chunk_text("") == []
        assert chunk_text("   \n  \t  ") == []

    def test_chunk_hindi_text(self):
        """Hindi text should be chunked without errors."""
        from parikrama.rag.chunker import chunk_text

        text = "मनाली एक सुंदर हिल स्टेशन है। यहाँ की वादियाँ बहुत खूबसूरत हैं। " * 100
        chunks = chunk_text(text)
        assert len(chunks) > 0
        # All chunks should have some content
        for chunk in chunks:
            assert len(chunk["content"].strip()) > 0

    def test_chunk_pages(self):
        """chunk_pages should assign page numbers to metadata."""
        from parikrama.rag.chunker import chunk_pages

        pages = [
            "Page one content about Delhi. " * 50,
            "Page two content about Manali. " * 50,
        ]
        chunks = chunk_pages(pages, metadata={"source": "test_pdf"})
        assert len(chunks) > 0
        # Verify page metadata is present
        page_numbers = {c["metadata"].get("page") for c in chunks}
        assert 1 in page_numbers or 2 in page_numbers

    def test_token_count_is_positive(self):
        """Token count estimate must be >= 1 for non-empty chunks."""
        from parikrama.rag.chunker import chunk_text

        text = "Short text. " * 20
        chunks = chunk_text(text)
        for chunk in chunks:
            assert chunk["token_count"] >= 1


# ── Unit Tests: Embedding Service ──────────────────────────────────────────────


class TestEmbeddingService:
    """Tests for the EmbeddingService (mocked to avoid loading the 80MB model)."""

    @patch("parikrama.rag.embeddings.SentenceTransformer")
    def test_embed_text_returns_list(self, mock_transformer):
        """embed_text should return a Python list of floats."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros(384, dtype="float32")
        mock_transformer.return_value = mock_model

        from parikrama.rag.embeddings import EmbeddingService

        service = EmbeddingService()
        result = service.embed_text("test query")

        assert isinstance(result, list)
        assert len(result) == 384

    @patch("parikrama.rag.embeddings.SentenceTransformer")
    def test_embed_batch_length_matches_input(self, mock_transformer):
        """embed_batch result length must equal input list length."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((3, 384), dtype="float32")
        mock_transformer.return_value = mock_model

        from parikrama.rag.embeddings import EmbeddingService

        service = EmbeddingService()
        texts = ["text1", "text2", "text3"]
        result = service.embed_batch(texts)

        assert len(result) == 3
        assert all(len(e) == 384 for e in result)

    @patch("parikrama.rag.embeddings.SentenceTransformer")
    def test_embed_batch_empty_input(self, mock_transformer):
        """embed_batch with empty list should return empty list without calling model."""
        from parikrama.rag.embeddings import EmbeddingService

        service = EmbeddingService()
        result = service.embed_batch([])
        assert result == []

    def test_query_hash_is_deterministic(self):
        """Same text should always produce the same hash."""
        from parikrama.rag.embeddings import EmbeddingService

        h1 = EmbeddingService.query_hash("hotels in manali")
        h2 = EmbeddingService.query_hash("hotels in manali")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_query_hash_case_insensitive(self):
        """Query hash should normalize to lowercase before hashing."""
        from parikrama.rag.embeddings import EmbeddingService

        h1 = EmbeddingService.query_hash("Hotels In Manali")
        h2 = EmbeddingService.query_hash("hotels in manali")
        assert h1 == h2


# ── Unit Tests: RRF Fusion ─────────────────────────────────────────────────────


class TestRRFFusion:
    """Tests for the Reciprocal Rank Fusion algorithm."""

    def _make_retriever(self):
        """Create a HybridRetriever with a mocked DB session."""
        from unittest.mock import MagicMock

        from parikrama.rag.retriever import HybridRetriever

        return HybridRetriever(db=MagicMock())

    def _make_results(self, chunk_ids: list[str]) -> list[dict]:
        return [
            {
                "chunk_id": cid,
                "content": f"content_{cid}",
                "metadata": {},
                "document_id": "doc-1",
                "score": 0.9 - i * 0.1,
                "source": "test",
            }
            for i, cid in enumerate(chunk_ids)
        ]

    def test_rrf_merges_unique_results(self):
        """RRF should include all unique chunk IDs from both lists."""
        retriever = self._make_retriever()
        semantic = self._make_results(["a", "b", "c"])
        keyword = self._make_results(["c", "d", "e"])
        merged = retriever._reciprocal_rank_fusion(semantic, keyword, 0.6, 0.4)
        merged_ids = {r["chunk_id"] for r in merged}
        assert {"a", "b", "c", "d", "e"} == merged_ids

    def test_rrf_overlap_boosts_score(self):
        """A chunk appearing in both lists should score higher than chunks in only one."""
        retriever = self._make_retriever()
        # chunk "shared" appears in both lists at rank 0
        semantic = self._make_results(["shared", "only_sem"])
        keyword = self._make_results(["shared", "only_kw"])
        merged = retriever._reciprocal_rank_fusion(semantic, keyword, 0.5, 0.5)

        scores = {r["chunk_id"]: r["rrf_score"] for r in merged}
        assert scores["shared"] > scores["only_sem"]
        assert scores["shared"] > scores["only_kw"]

    def test_rrf_sorted_descending(self):
        """Merged results must be sorted by rrf_score descending."""
        retriever = self._make_retriever()
        semantic = self._make_results(["a", "b", "c"])
        keyword = self._make_results(["d", "a", "e"])
        merged = retriever._reciprocal_rank_fusion(semantic, keyword, 0.6, 0.4)
        scores = [r["rrf_score"] for r in merged]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_empty_inputs(self):
        """RRF with both empty lists should return empty list."""
        retriever = self._make_retriever()
        merged = retriever._reciprocal_rank_fusion([], [], 0.6, 0.4)
        assert merged == []

    def test_rrf_one_empty_input(self):
        """RRF with one empty list should still return non-empty results."""
        retriever = self._make_retriever()
        semantic = self._make_results(["a", "b"])
        merged = retriever._reciprocal_rank_fusion(semantic, [], 0.6, 0.4)
        assert len(merged) == 2


# ── Integration Tests: Document API ───────────────────────────────────────────


class TestDocumentAPI:
    """Integration tests for the document upload/list/get/delete API."""

    # ── Fixture helpers ────────────────────────────────────────────────────────

    async def _get_auth_headers(self, client: AsyncClient) -> dict:
        """Register a test user and return Authorization header with their token."""
        email = f"ragtest_{uuid.uuid4().hex[:8]}@example.com"
        # Register — returns {"user": {...}, "tokens": {"access_token": ...}}
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPass123!", "name": "RAG Tester"},
        )
        assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
        token = reg_resp.json()["tokens"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    # ── Tests ──────────────────────────────────────────────────────────────────

    @patch("parikrama.services.storage_service.Minio")
    @patch("parikrama.services.document_service.DocumentService._queue_processing")
    async def test_upload_document_success(self, mock_queue, mock_minio_class, client: AsyncClient):
        """POST /documents/upload should return 201 with document metadata."""
        # Mock MinIO to avoid requiring a running MinIO server
        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.return_value = None
        mock_queue.return_value = None

        headers = await self._get_auth_headers(client)
        fake_pdf = b"%PDF-1.4 fake content for testing " + b"A" * 100

        resp = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("test_guide.pdf", BytesIO(fake_pdf), "application/pdf")},
            data={"destination": "Manali"},
        )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data
        assert data["filename"] == "test_guide.pdf"
        assert data["status"] == "uploaded"
        assert data["destination"] == "Manali"

    @patch("parikrama.services.storage_service.Minio")
    @patch("parikrama.services.document_service.DocumentService._queue_processing")
    async def test_list_documents_empty(self, mock_queue, mock_minio_class, client: AsyncClient):
        """GET /documents should return empty list for new user."""
        headers = await self._get_auth_headers(client)
        resp = await client.get("/api/v1/documents", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @patch("parikrama.services.storage_service.Minio")
    @patch("parikrama.services.document_service.DocumentService._queue_processing")
    async def test_upload_then_get_document(
        self, mock_queue, mock_minio_class, client: AsyncClient
    ):
        """Upload a document then GET it by ID — should return same data."""
        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.return_value = None
        mock_queue.return_value = None

        headers = await self._get_auth_headers(client)
        fake_pdf = b"%PDF-1.4 " + b"B" * 200

        upload_resp = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("manali_guide.pdf", BytesIO(fake_pdf), "application/pdf")},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == doc_id
        assert get_resp.json()["filename"] == "manali_guide.pdf"

    async def test_get_nonexistent_document_returns_404(self, client: AsyncClient):
        """GET /documents/{random_uuid} should return 404."""
        headers = await self._get_auth_headers(client)
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/documents/{fake_id}", headers=headers)
        assert resp.status_code == 404

    @patch("parikrama.services.storage_service.Minio")
    @patch("parikrama.services.document_service.DocumentService._queue_processing")
    async def test_delete_document_success(self, mock_queue, mock_minio_class, client: AsyncClient):
        """Upload then DELETE a document — should return 204."""
        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.return_value = None
        mock_client.remove_object.return_value = None
        mock_queue.return_value = None

        headers = await self._get_auth_headers(client)
        fake_pdf = b"%PDF-1.4 " + b"C" * 100

        upload_resp = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("to_delete.pdf", BytesIO(fake_pdf), "application/pdf")},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_upload_empty_file_returns_400(self, client: AsyncClient):
        """Uploading an empty file should return 400."""
        headers = await self._get_auth_headers(client)
        resp = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code in (400, 422)

    async def test_upload_requires_auth(self, client: AsyncClient):
        """Document upload without auth should return 401."""
        fake_pdf = b"%PDF-1.4 test"
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", BytesIO(fake_pdf), "application/pdf")},
        )
        assert resp.status_code == 401
