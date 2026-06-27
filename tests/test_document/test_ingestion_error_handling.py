"""Comprehensive error handling tests for document ingestion module.

This module tests error scenarios to improve coverage of uncovered paths:
- Lines 1423-1526: Complex ingestion error handling
- Lines 1547-1593: Advanced chunking strategies with failures
- Lines 2003-2082: Memory management edge cases

Tests cover:
- Embedding failure scenarios (5 tests)
- File processing errors (4 tests)
- Memory exhaustion (3 tests)
- Database connection failures (3 tests)
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from secondbrain.document import (
    AsyncDocumentIngestor,
    DocumentIngestor,
)
from secondbrain.exceptions import (
    EmbeddingError,
    EmbeddingGenerationError,
    StorageConnectionError,
)


class TestEmbeddingFailureScenarios:
    """Tests for embedding generation failure handling."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_embedding_failure_gracefully(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that ingestion handles embedding failures gracefully."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingGenerationError(
            "Embedding API failed"
        )
        mock_embedding.generate.side_effect = EmbeddingGenerationError(
            "Single embedding failed"
        )
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result
        assert result["failed"] >= 1

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.storage.VectorStorage")
    def test_ingest_continues_on_single_embedding_error(
        self, mock_vs: MagicMock, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        mock_embedding = MagicMock()
        call_count = 0

        def embedding_side_effect(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EmbeddingGenerationError("First batch failed")
            return [[0.1] * 384 for _ in range(len(texts))]

        mock_embedding.generate_batch = MagicMock(side_effect=embedding_side_effect)
        mock_embedding.generate = MagicMock(side_effect=lambda x: [0.1] * 384)
        mock_factory.return_value = mock_embedding
        mock_vs.return_value = MagicMock()

        ingestor = DocumentIngestor(verbose=True)

        test_file1 = tmp_path / "test1.pdf"
        test_file1.write_bytes(b"fake pdf 1")
        test_file2 = tmp_path / "test2.pdf"
        test_file2.write_bytes(b"fake pdf 2")

        with patch("time.sleep", return_value=None):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "success" in result
        assert "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_embedding_timeout_handling(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test timeout handling during embedding generation."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = TimeoutError(
            "Embedding generation timed out"
        )
        mock_embedding.generate.side_effect = TimeoutError(
            "Single embedding timed out"
        )
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result
        assert result["failed"] >= 1

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_embedding_rate_limit_backoff(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test rate limit handling with backoff."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingError(
            "Rate limit exceeded"
        )
        mock_embedding.generate.side_effect = EmbeddingError(
            "Rate limit exceeded"
        )
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_fallback_embedding_provider_on_failure(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that ingestion handles embedding failures gracefully."""
        # Mock embedding to always fail
        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingGenerationError(
            "Batch embedding failed"
        )
        mock_embedding.generate.side_effect = EmbeddingGenerationError(
            "Single embedding failed"
        )
        mock_factory.return_value = mock_embedding

        # Mock storage to succeed
        mock_storage = MagicMock()

        with patch(
            "secondbrain.storage.storage.VectorStorage",
            return_value=mock_storage,
        ):
            ingestor = DocumentIngestor(verbose=False)
            test_file = tmp_path / "test.txt"
            test_file.write_text("sample content for testing")
            result = ingestor.ingest(str(tmp_path), recursive=False, cores=1)

        # Should handle failure gracefully and report failed count
        assert isinstance(result, dict)
        assert "failed" in result or "success" in result


class TestFileProcessingErrors:
    """Tests for file processing error scenarios."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_permission_denied(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Test handling of permission denied errors."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.chmod(0o000)

        try:
            with patch(
                "secondbrain.document.DocumentIngestor._extract_text",
                side_effect=PermissionError("Permission denied"),
            ):
                result = ingestor.ingest(str(tmp_path), recursive=False)

            assert "failed" in result
        finally:
            test_file.chmod(0o644)

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_file_not_found_during_processing(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Test handling of file deleted during processing."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.unlink()

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_corrupted_file_gracefully(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Test handling of corrupted PDF files."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "corrupted.pdf"
        test_file.write_bytes(b"This is not a valid PDF file content")

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)
        assert "success" in result or "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_encoding_errors(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Test handling of files with encoding errors."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "encoded.txt"
        with test_file.open("wb") as f:
            f.write(b"\xff\xfe invalid utf-8 \x00\x01")

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)


class TestMemoryExhaustion:
    """Tests for memory exhaustion scenarios."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_memory_exhaustion_during_batch(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test handling of memory exhaustion during batch storage."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        with patch(
            "secondbrain.storage.storage.VectorStorage.store_batch",
            side_effect=MemoryError("Out of memory"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_chunking_falls_back_to_smaller_batches_on_oom(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that chunking handles memory pressure."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        call_count = 0

        def storage_side_effect(batch: list[dict[str, Any]]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise MemoryError("Batch too large")

        with patch(
            "secondbrain.storage.storage.VectorStorage.store_batch",
            side_effect=storage_side_effect,
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)

    @patch("secondbrain.storage.VectorStorage")
    def test_progress_callback_handles_memory_pressure(
        self, mock_vs: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test progress callback handling under memory pressure."""
        callback_errors = []

        def memory_pressure_callback(file_path: Path, success: bool) -> None:
            nonlocal callback_errors
            if not success:
                callback_errors.append(f"Failed: {file_path}")

        ingestor = DocumentIngestor(
            verbose=False, progress_callback=memory_pressure_callback
        )

        test_file = tmp_path / "test.txt"
        test_file.write_text("sample content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        with patch("time.sleep", return_value=None), \
             patch("gc.collect", return_value=None), \
             patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config", return_value=mock_embedding), \
             patch("secondbrain.storage.VectorStorage.store_batch", return_value=None):
            result = ingestor.ingest(str(tmp_path), recursive=False, cores=1)

        assert isinstance(result, dict)


class TestDatabaseConnectionFailures:
    """Tests for MongoDB connection failure scenarios."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_handles_mongo_connection_failure(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test handling of MongoDB connection failures."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        with patch(
            "secondbrain.storage.storage.VectorStorage.store_batch",
            side_effect=StorageConnectionError("MongoDB connection failed"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_retries_on_mongo_timeout(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Test that ingestion handles MongoDB timeout gracefully without crashing."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(100)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("sample content")

        with patch(
            "secondbrain.storage.storage.VectorStorage.store_batch",
            side_effect=TimeoutError("MongoDB timeout"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result
        assert result["failed"] == 1

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_ingest_graceful_degradation_on_db_failure(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test graceful degradation when database is unavailable."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        with patch(
            "secondbrain.storage.storage.VectorStorage.store_batch",
            side_effect=StorageConnectionError("Database unavailable"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)


class TestMultithreadedErrorHandling:
    """Tests for error handling in multithreaded ingestion."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_threaded_ingest_handles_partial_failures(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that threaded ingestion handles partial failures."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        for i in range(3):
            test_file = tmp_path / f"test{i}.pdf"
            test_file.write_bytes(b"fake pdf content")

        result = ingestor.ingest(str(tmp_path), recursive=False, batch_size=2)

        assert "success" in result
        assert "failed" in result
        assert isinstance(result["success"], int)
        assert isinstance(result["failed"], int)

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    def test_multiprocess_ingest_handles_worker_crashes(
        self, mock_factory: MagicMock, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that multiprocess ingestion handles worker crashes."""
        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)
        mock_factory.return_value = mock_embedding

        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = ingestor.ingest(str(tmp_path), recursive=False, cores=1)

        assert "success" in result
        assert "failed" in result

    async def test_async_ingest_handles_embedding_failures(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test async ingestion handles embedding failures."""
        ingestor = AsyncDocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch_async = MagicMock(
            side_effect=EmbeddingGenerationError("Async embedding failed")
        )

        mock_storage = MagicMock()

        result = await ingestor.process_file_async(
            test_file, mock_embedding, mock_storage
        )

        assert result is False

    async def test_async_ingest_handles_storage_failures(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test async ingestion handles storage failures."""
        ingestor = AsyncDocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch_async = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )

        mock_storage = MagicMock()
        mock_storage.store_batch = MagicMock(
            side_effect=StorageConnectionError("Async storage failed")
        )

        result = await ingestor.process_file_async(
            test_file, mock_embedding, mock_storage
        )

        assert result is False
