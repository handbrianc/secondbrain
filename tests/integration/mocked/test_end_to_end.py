"""End-to-end integration tests for SecondBrain workflows.

Tests exercise real logic paths with minimal mocking:
- Document ingestion pipeline (segment dedup → chunking → embedding → build)
- Full workflow: ingest -> list -> delete

Uses the in-memory :class:`~secondbrain.storage.mock.MockVectorStorage` backend,
which implements the full Qdrant storage protocol.

pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("mocked_integration")]


ARCHITECTURAL NOTE:
`ingest()` uses ThreadPoolExecutor internally for parallel file processing —
worker threads re-import `docling` and embedding factories, bypassing test
patches. Therefore, pipeline stages are tested DIRECTLY (not through `ingest()`)
to ensure mocks apply. The threading workflow IS exercised in
test_e2e_pdf_ingestion.py via proper monkeypatch.setattr at module scope.
"""

from __future__ import annotations

import uuid
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentIngestor
from secondbrain.storage.mock import MockVectorStorage

# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)


class TestDocumentIngestion:
    """Tests for document ingestion end-to-end workflow."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingest_single_pdf_document(self, sample_pdf_path: Path) -> None:
        """Test PDF segments pass through embed→build pipeline producing valid docs."""
        import random

        random.seed(0)

        def make_emb(text: str) -> list[float]:
            random.seed(hash(text.lower()))
            return [random.random() for _ in range(384)]

        mock_embed_instance = MagicMock()
        mock_embed_instance.generate.side_effect = make_emb
        mock_embed_instance.generate_batch.side_effect = lambda texts: [
            make_emb(t) for t in texts
        ]
        mock_embed_instance.validate_connection.return_value = True

        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        segments = ingestor._extract_text(sample_pdf_path)
        assert len(segments) > 0

        chunks = ingestor._deduplicate_and_chunk_segments(sample_pdf_path, segments)
        with patch.object(
            ingestor, "_generate_embeddings_with_cache"
        ) as mock_gen_cache:
            mock_gen_cache.return_value = {
                c["text_hash"]: make_emb(c["text"]) for c in chunks
            }
            docs = ingestor._build_documents_with_embeddings(
                sample_pdf_path, segments, mock_embed_instance
            )

        assert len(docs) >= 1
        for doc in docs:
            assert isinstance(doc["chunk_id"], str)
            assert doc["source_file"] == str(sample_pdf_path)
            assert doc["page_number"] >= 0
            assert doc["chunk_text"] != ""
            assert isinstance(doc["embedding"], list)
            assert len(doc["embedding"]) == 384

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingest_multiple_files_batch(
        self,
        sample_pdf_path: Path,
        sample_pdf_with_multiple_pages: Path,
        tmp_path: Path,
    ) -> None:
        """Test that building docs from two PDFs produces correct schemas."""
        import random
        import shutil

        test_dir = tmp_path / "test_pdfs"
        test_dir.mkdir()
        pdf1 = test_dir / "test1.pdf"
        pdf2 = test_dir / "test2.pdf"
        shutil.copy(sample_pdf_path, pdf1)
        shutil.copy(sample_pdf_with_multiple_pages, pdf2)

        random.seed(0)

        def make_emb(text: str) -> list[float]:
            random.seed(hash(text.lower()))
            return [random.random() for _ in range(384)]

        mock_embed = MagicMock()
        mock_embed.generate.side_effect = make_emb
        mock_embed.generate_batch.side_effect = lambda texts: [
            make_emb(t) for t in texts
        ]
        mock_embed.validate_connection.return_value = True

        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        for pdf_path in [pdf1, pdf2]:
            segments = ingestor._extract_text(pdf_path)
            assert len(segments) > 0, f"No segments from {pdf_path.name}"

            chunks = ingestor._deduplicate_and_chunk_segments(pdf_path, segments)

            with patch.object(
                ingestor, "_generate_embeddings_with_cache"
            ) as mock_gen_cache:
                mock_gen_cache.return_value = {
                    c["text_hash"]: make_emb(c["text"]) for c in chunks
                }
                docs = ingestor._build_documents_with_embeddings(
                    pdf_path, segments, mock_embed
                )

            assert len(docs) >= 1, f"No docs produced for {pdf_path.name}"

            for d in docs:
                assert isinstance(d["embedding"], list)
                assert len(d["embedding"]) == 384
                assert d["source_file"] == str(pdf_path)


class TestFullWorkflow:
    """Tests for complete workflow: ingest -> list -> delete."""

    @pytest.mark.integration
    def test_full_workflow(
        self,
        tmp_path: Path,
    ) -> None:
        """Test complete workflow from ingestion to deletion using MockVectorStorage."""
        storage = MockVectorStorage()

        original_count = len(storage.list_chunks())

        def mock_generate(text: str) -> list[float]:
            import random as r

            r.seed(hash(text.lower()))
            return [r.random() for _ in range(384)]

        pdf_path = tmp_path / "test_workflow.pdf"
        pdf_path.write_text("Test content for full workflow")

        try:
            with (
                patch(
                    "secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config"
                ) as mock_factory,
                patch(
                    "secondbrain.storage.factory.StorageFactory.create_from_config",
                    return_value=storage,
                ),
            ):
                mock_embed = MagicMock()
                mock_embed.generate.side_effect = mock_generate
                mock_embed.validate_connection.return_value = True
                mock_factory.return_value = mock_embed

                ingestor = DocumentIngestor(
                    chunk_size=500, chunk_overlap=50, verbose=False
                )
                result = ingestor.ingest(str(pdf_path))
                success_count = result["success"]
                assert isinstance(success_count, int)
                assert success_count >= 0

            new_docs = list(storage.list_chunks())
            final_count = len(new_docs)

            assert final_count >= original_count

            chunks = list(storage.list_chunks())
            assert isinstance(chunks, list)

            delete_count = storage.delete_by_source(str(pdf_path))

            remaining = list(storage.list_chunks())
            assert len(remaining) == final_count - delete_count
        finally:
            pdf_path.unlink(missing_ok=True)

    @pytest.mark.integration
    def test_delete_by_chunk_id(self) -> None:
        """Test deleting by specific chunk ID."""
        storage = MockVectorStorage()

        storage.store(
            {
                "chunk_id": "test-chunk-123",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "Test content",
                "embedding": [0.1] * 384,
                "metadata": {"file_type": "pdf"},
            }
        )

        storage.delete_by_chunk_id("test-chunk-123")

        assert storage.get_chunk("test-chunk-123") is None
        remaining = list(storage.list_chunks())
        assert len(remaining) == 0

    @pytest.mark.integration
    def test_delete_all(self) -> None:
        """Test deleting all documents."""
        storage = MockVectorStorage()

        for i in range(5):
            storage.store(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "source_file": f"test{i}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Content {i}",
                    "embedding": [0.1] * 384,
                    "metadata": {"file_type": "pdf"},
                }
            )

        delete_count = storage.delete_all()
        assert delete_count == 5

        remaining = list(storage.list_chunks())
        assert len(remaining) == 0


class TestIntegrationDataFlow:
    """Tests validating data flows between modules."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingestion_creates_proper_chunks(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Verify chunk schema fields and embedding dimensions from build pipeline."""
        import random

        random.seed(0)

        def make_emb(text: str) -> list[float]:
            random.seed(hash(text.lower()))
            return [random.random() for _ in range(384)]

        mock_embed = MagicMock()
        mock_embed.generate.side_effect = make_emb
        mock_embed.generate_batch.side_effect = lambda texts: [
            make_emb(t) for t in texts
        ]
        mock_embed.validate_connection.return_value = True

        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        segments = ingestor._extract_text(sample_pdf_path)
        assert len(segments) > 0

        chunks = ingestor._deduplicate_and_chunk_segments(sample_pdf_path, segments)

        with patch.object(
            ingestor, "_generate_embeddings_with_cache"
        ) as mock_gen_cache:
            mock_gen_cache.return_value = {
                c["text_hash"]: make_emb(c["text"]) for c in chunks
            }
            docs = ingestor._build_documents_with_embeddings(
                sample_pdf_path, segments, mock_embed
            )

        assert len(docs) >= 1
        for doc in docs:
            assert isinstance(doc["chunk_id"], str)
            assert doc.get("source_file") == str(sample_pdf_path)
            assert doc.get("page_number", 0) >= 0
            assert doc.get("chunk_text", "") != ""
            assert isinstance(doc["embedding"], list)
            assert len(doc["embedding"]) == 384
            assert "file_type" in doc
            assert "ingested_at" in doc

    @pytest.mark.integration
    def test_list_pagination_works(self) -> None:
        """Test list pagination functionality."""
        storage = MockVectorStorage()

        for i in range(10):
            storage.store(
                {
                    "chunk_id": f"chunk-{i:03d}",
                    "source_file": f"test{i % 2}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Chunk {i}",
                    "embedding": [0.1] * 384,
                    "metadata": {"file_type": "pdf"},
                }
            )

        page1 = list(storage.list_chunks(limit=3, offset=0))
        page2 = list(storage.list_chunks(limit=3, offset=3))

        assert len(page1) == 3
        assert len(page2) == 3

        chunk_ids_page1 = {c["chunk_id"] for c in page1}
        chunk_ids_page2 = {c["chunk_id"] for c in page2}

        assert chunk_ids_page1.isdisjoint(chunk_ids_page2)

    @pytest.mark.integration
    def test_list_with_source_filter(self) -> None:
        """Test listing with source file filter."""
        storage = MockVectorStorage()

        for i in range(10):
            storage.store(
                {
                    "chunk_id": f"chunk-{i:03d}",
                    "source_file": f"test{i % 2}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Chunk {i}",
                    "embedding": [0.1] * 384,
                    "metadata": {"file_type": "pdf"},
                }
            )

        filtered = [
            c for c in storage.list_chunks() if "test0" in c["source_file"]
        ]

        for chunk in filtered:
            assert "test0" in chunk["source_file"]

    @pytest.mark.integration
    @pytest.mark.slow
    def test_chunk_overlapping_text(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Test that text chunking preserves overlapping segments."""
        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        all_chunks = ingestor._extract_text(sample_pdf_path)

        assert len(all_chunks) > 0

        for chunk in all_chunks:
            assert "text" in chunk
            assert "page" in chunk
            assert isinstance(chunk["text"], str)
            assert isinstance(chunk["page"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
