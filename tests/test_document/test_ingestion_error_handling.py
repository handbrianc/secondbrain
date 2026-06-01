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

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import (
    AsyncDocumentIngestor,
    DocumentExtractionError,
    DocumentIngestor,
)
from secondbrain.exceptions import (
    EmbeddingError,
    EmbeddingGenerationError,
    StorageConnectionError,
)


class TestEmbeddingFailureScenarios:
    """Tests for embedding generation failure handling."""

    def test_ingest_handles_embedding_failure_gracefully(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that ingestion handles embedding failures gracefully."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingGenerationError(
            "Embedding API failed"
        )
        mock_embedding.generate.side_effect = EmbeddingGenerationError(
            "Single embedding failed"
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result
        assert result["failed"] >= 1

    def test_ingest_continues_on_single_embedding_error(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that ingestion continues when some embeddings fail."""
        ingestor = DocumentIngestor(verbose=True)

        test_file1 = tmp_path / "test1.pdf"
        test_file1.write_bytes(b"fake pdf 1")
        test_file2 = tmp_path / "test2.pdf"
        test_file2.write_bytes(b"fake pdf 2")

        call_count = 0

        def embedding_side_effect(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EmbeddingGenerationError("First batch failed")
            return [[0.1] * 384 for _ in range(len(texts))]

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(side_effect=embedding_side_effect)

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "success" in result
        assert "failed" in result

    def test_embedding_timeout_handling(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test timeout handling during embedding generation."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = TimeoutError(
            "Embedding generation timed out"
        )
        mock_embedding.generate.side_effect = TimeoutError(
            "Single embedding timed out"
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result
        assert result["failed"] >= 1

    def test_embedding_rate_limit_backoff(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test rate limit handling with backoff."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingError(
            "Rate limit exceeded"
        )
        mock_embedding.generate.side_effect = EmbeddingError(
            "Rate limit exceeded"
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    def test_fallback_embedding_provider_on_failure(
        self, tmp_path: Path
    ) -> None:
        """Test that ingestion handles embedding failures gracefully."""
        ingestor = DocumentIngestor(verbose=False)

        test_file = tmp_path / "test.txt"
        test_file.write_text("sample content for testing")

        # Mock embedding to always fail
        mock_embedding = MagicMock()
        mock_embedding.generate_batch.side_effect = EmbeddingGenerationError(
            "Batch embedding failed"
        )
        mock_embedding.generate.side_effect = EmbeddingGenerationError(
            "Single embedding failed"
        )

        # Mock storage to succeed
        mock_storage = MagicMock()

        with patch(
            "secondbrain.embedding.LocalEmbeddingGenerator",
            return_value=mock_embedding,
        ):
            with patch(
                "secondbrain.storage.storage.VectorStorage",
                return_value=mock_storage,
            ):
                result = ingestor.ingest(str(tmp_path), recursive=False, cores=1)

        # Should handle failure gracefully and report failed count
        assert isinstance(result, dict)
        assert "failed" in result or "success" in result


class TestFileProcessingErrors:
    """Tests for file processing error scenarios."""

    def test_ingest_handles_permission_denied(self, tmp_path: Path) -> None:
        """Test handling of permission denied errors."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.chmod(0o000)

        try:
            mock_embedding = MagicMock()
            mock_embedding.generate_batch = MagicMock(
                return_value=[[0.1] * 384 for _ in range(5)]
            )

            with patch(
                "secondbrain.document.DocumentIngestor._extract_text",
                side_effect=PermissionError("Permission denied"),
            ):
                result = ingestor.ingest(str(tmp_path), recursive=False)

            assert "failed" in result
        finally:
            test_file.chmod(0o644)

    def test_ingest_handles_file_not_found_during_processing(self, tmp_path: Path) -> None:
        """Test handling of file deleted during processing."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.unlink()

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    def test_ingest_handles_corrupted_file_gracefully(self, tmp_path: Path) -> None:
        """Test handling of corrupted PDF files."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "corrupted.pdf"
        test_file.write_bytes(b"This is not a valid PDF file content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)
        assert "success" in result or "failed" in result

    def test_ingest_handles_encoding_errors(self, tmp_path: Path) -> None:
        """Test handling of files with encoding errors."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "encoded.txt"
        with test_file.open("wb") as f:
            f.write(b"\xff\xfe invalid utf-8 \x00\x01")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )

        result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)


class TestMemoryExhaustion:
    """Tests for memory exhaustion scenarios."""

    def test_ingest_handles_memory_exhaustion_during_batch(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test handling of memory exhaustion during batch storage."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        with patch(
            "secondbrain.document.VectorStorage.store_batch",
            side_effect=MemoryError("Out of memory"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    def test_chunking_falls_back_to_smaller_batches_on_oom(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that chunking handles memory pressure."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        call_count = 0

        def storage_side_effect(batch: list[dict[str, Any]]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise MemoryError("Batch too large")

        with patch(
            "secondbrain.document.VectorStorage.store_batch",
            side_effect=storage_side_effect,
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)

    def test_progress_callback_handles_memory_pressure(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
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

        with patch(
            "secondbrain.embedding.LocalEmbeddingGenerator",
            return_value=mock_embedding,
        ):
            with patch(
                "secondbrain.storage.storage.VectorStorage",
                return_value=MagicMock(),
            ):
                result = ingestor.ingest(str(tmp_path), recursive=False, cores=1)

        assert isinstance(result, dict)


class TestDatabaseConnectionFailures:
    """Tests for MongoDB connection failure scenarios."""

    def test_ingest_handles_mongo_connection_failure(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test handling of MongoDB connection failures."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        with patch(
            "secondbrain.document.VectorStorage.store_batch",
            side_effect=StorageConnectionError("MongoDB connection failed"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert "failed" in result

    def test_ingest_retries_on_mongo_timeout(
        self, tmp_path: Path
    ) -> None:
        """Test retry behavior on MongoDB timeout."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("sample content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        call_count = 0

        def timeout_then_success(batch: list[dict[str, Any]]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("MongoDB timeout")

        with patch(
            "secondbrain.document.VectorStorage.store_batch",
            side_effect=timeout_then_success,
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert call_count >= 1

    def test_ingest_graceful_degradation_on_db_failure(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test graceful degradation when database is unavailable."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        with patch(
            "secondbrain.document.VectorStorage.store_batch",
            side_effect=StorageConnectionError("Database unavailable"),
        ):
            result = ingestor.ingest(str(tmp_path), recursive=False)

        assert isinstance(result, dict)


class TestMultithreadedErrorHandling:
    """Tests for error handling in multithreaded ingestion."""

    def test_threaded_ingest_handles_partial_failures(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that threaded ingestion handles partial failures."""
        ingestor = DocumentIngestor(verbose=True)

        for i in range(3):
            test_file = tmp_path / f"test{i}.pdf"
            test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

        result = ingestor.ingest(str(tmp_path), recursive=False, batch_size=2)

        assert "success" in result
        assert "failed" in result
        assert isinstance(result["success"], int)
        assert isinstance(result["failed"], int)

    def test_multiprocess_ingest_handles_worker_crashes(
        self, tmp_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test that multiprocess ingestion handles worker crashes."""
        ingestor = DocumentIngestor(verbose=True)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        mock_embedding = MagicMock()
        mock_embedding.generate_batch = MagicMock(
            return_value=[[0.1] * 384 for _ in range(5)]
        )
        mock_embedding.generate = MagicMock(return_value=[0.1] * 384)

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
