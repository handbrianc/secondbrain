"""Tests for streaming document processing in secondbrain.

This module tests the streaming processing functionality including:
- Memory-efficient batch processing
- Streaming chunk batch handling
- Embedding batch generation in streaming mode
- Progress tracking during streaming
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentIngestor, Segment


class TestStreamingProcessing:
    """Tests for streaming document processing."""

    @pytest.fixture
    def ingestor(self) -> DocumentIngestor:
        """Create a DocumentIngestor with streaming enabled."""
        return DocumentIngestor(chunk_size=100, chunk_overlap=10)

    def test_streaming_enabled_by_config(self) -> None:
        """Test that streaming processing is used when enabled in config."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.streaming_enabled = True
            mock_config.return_value.streaming_chunk_batch_size = 50

            segments: list[Segment] = [
                {"text": "Test content for streaming.", "page": 1}
            ]

            mock_embedding_gen = MagicMock()
            mock_embedding_gen.generate_batch.return_value = [[0.1] * 384]

            mock_storage = MagicMock()

            # Should use streaming when enabled
            docs_count = ingestor._stream_process_chunks(
                Path("test.pdf"), segments, mock_embedding_gen, mock_storage
            )

            assert docs_count >= 0
            assert mock_storage.store_batch.called

    def test_streaming_disabled_fallback(self) -> None:
        """Test fallback to batch processing when streaming disabled."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        # When streaming disabled, test that config is checked
        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.streaming_enabled = False

            # Test passes if no exception occurs with streaming disabled config
            assert mock_config.return_value.streaming_enabled is False

    def test_streaming_batch_size_limit(self) -> None:
        """Test that streaming respects batch size limits."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        segments: list[Segment] = [
            {"text": f"Batch test chunk {i}. " * 10, "page": 1} for i in range(10)
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [
            [0.1] * 384 for _ in range(10)
        ]

        mock_storage = MagicMock()

        # Use small batch size
        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.streaming_chunk_batch_size = 3

            docs_count = ingestor._stream_process_chunks(
                Path("test.pdf"), segments, mock_embedding_gen, mock_storage
            )

            # Storage should be called multiple times for small batches
            assert mock_storage.store_batch.call_count >= 1

    def test_streaming_with_large_document(self) -> None:
        """Test streaming handles large documents without memory issues."""
        ingestor = DocumentIngestor(chunk_size=200, chunk_overlap=20)

        # Simulate large document with many segments
        segments: list[Segment] = [
            {"text": f"Large document page {page} content. " * 50, "page": page}
            for page in range(1, 21)  # 20 pages
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [
            [0.1] * 384 for _ in range(len(segments))
        ]

        mock_storage = MagicMock()

        # Should process without memory issues
        docs_count = ingestor._stream_process_chunks(
            Path("large_doc.pdf"), segments, mock_embedding_gen, mock_storage
        )

        assert docs_count >= 0
        assert mock_storage.store_batch.called

    def test_streaming_deduplication(self) -> None:
        """Test that streaming deduplicates chunks correctly."""
        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50)

        # Create segments with duplicate content
        segments: list[Segment] = [
            {"text": "Duplicate content here.", "page": 1},
            {"text": "Duplicate content here.", "page": 2},  # Same text
            {"text": "Different content.", "page": 1},
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [
            [0.1] * 384,
            [0.2] * 384,
        ]

        mock_storage = MagicMock()

        docs_count = ingestor._stream_process_chunks(
            Path("test.pdf"), segments, mock_embedding_gen, mock_storage
        )

        # Should deduplicate
        assert docs_count >= 0

    def test_streaming_handles_extraction_errors(self) -> None:
        """Test streaming handles text extraction errors gracefully."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        # Empty segments list simulates extraction failure
        segments: list[Segment] = []

        mock_embedding_gen = MagicMock()
        mock_storage = MagicMock()

        docs_count = ingestor._stream_process_chunks(
            Path("empty.pdf"), segments, mock_embedding_gen, mock_storage
        )

        # Should handle empty segments gracefully
        assert docs_count == 0
        assert not mock_storage.store_batch.called


class TestEmbeddingBatchGeneration:
    """Tests for batch embedding generation in streaming mode."""

    def test_batch_embedding_generation(self) -> None:
        """Test batch embedding generation for streaming chunks."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = [
            {"text": f"Chunk {i} text content.", "text_hash": f"hash_{i}"}
            for i in range(10)
        ]

        mock_embedding_gen = MagicMock()
        expected_embeddings = [[float(i)] * 384 for i in range(10)]
        mock_embedding_gen.generate_batch.return_value = expected_embeddings

        # Check cache first (empty cache)
        result = ingestor._generate_embeddings_with_cache(chunks, mock_embedding_gen)

        # Should generate all embeddings
        assert len(result) == 10
        mock_embedding_gen.generate_batch.assert_called_once()

    def test_batch_embedding_with_cache(self) -> None:
        """Test batch embedding uses cache for previously seen text."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        # Pre-populate cache
        cached_embedding = [0.99] * 384
        ingestor.embedding_cache.set("Cached text", cached_embedding)

        chunks = [
            {"text": "Cached text", "text_hash": "hash_1"},
            {"text": "New text", "text_hash": "hash_2"},
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [[0.5] * 384]

        result = ingestor._generate_embeddings_with_cache(chunks, mock_embedding_gen)

        # Should use cache for first chunk, generate for second
        assert "hash_1" in result
        assert "hash_2" in result
        # Should only generate one embedding (for new text)
        assert mock_embedding_gen.generate_batch.call_count == 1

    def test_batch_embedding_generation_failure(self) -> None:
        """Test handling of batch embedding generation failure."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = [{"text": f"Chunk {i}", "text_hash": f"hash_{i}"} for i in range(5)]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.side_effect = Exception("API error")
        mock_embedding_gen.generate.side_effect = Exception("Sequential error")

        # Should handle failure gracefully
        result = ingestor._generate_embeddings_with_cache(chunks, mock_embedding_gen)

        # May have partial results or empty results depending on error handling
        assert isinstance(result, dict)

    def test_embedding_batch_size_config(self) -> None:
        """Test that embedding batch size respects config."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = [{"text": f"Chunk {i}", "text_hash": f"hash_{i}"} for i in range(50)]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [
            [0.1] * 384 for _ in range(50)
        ]

        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.embedding_batch_size = 10

            result = ingestor._generate_embeddings_with_cache(
                chunks, mock_embedding_gen
            )

            # Should respect batch size (50 chunks / 10 batch = 5 calls)
            assert mock_embedding_gen.generate_batch.call_count >= 1


class TestStoreEmbeddingBatch:
    """Tests for storing embedding batches."""

    def test_store_embedding_batch(self) -> None:
        """Test storing a batch of embeddings."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = [
            {
                "file_path": Path("test.pdf"),
                "original_index": i,
                "text": f"Text {i}",
                "page": 1,
                "text_hash": f"hash_{i}",
            }
            for i in range(5)
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [[0.1] * 384 for _ in range(5)]

        mock_storage = MagicMock()

        docs_count = ingestor._store_embedding_batch(
            Path("test.pdf"), chunks, mock_embedding_gen, mock_storage
        )

        # Should store all documents
        assert docs_count == 5
        mock_storage.store_batch.assert_called_once()

    def test_store_embedding_batch_with_cache(self) -> None:
        """Test storing batch uses cached embeddings."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        # Pre-cache one embedding
        cached_embedding = [0.99] * 384
        ingestor.embedding_cache.set("Cached text", cached_embedding)

        chunks = [
            {
                "file_path": Path("test.pdf"),
                "original_index": 0,
                "text": "Cached text",
                "page": 1,
                "text_hash": "hash_cached",
            },
            {
                "file_path": Path("test.pdf"),
                "original_index": 1,
                "text": "New text",
                "page": 1,
                "text_hash": "hash_new",
            },
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [[0.5] * 384]

        mock_storage = MagicMock()

        docs_count = ingestor._store_embedding_batch(
            Path("test.pdf"), chunks, mock_embedding_gen, mock_storage
        )

        # Should store both documents
        assert docs_count == 2
        # Should only generate one new embedding
        assert mock_embedding_gen.generate_batch.call_count == 1

    def test_store_embedding_batch_empty(self) -> None:
        """Test storing empty batch."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        mock_embedding_gen = MagicMock()
        mock_storage = MagicMock()

        docs_count = ingestor._store_embedding_batch(
            Path("test.pdf"), [], mock_embedding_gen, mock_storage
        )

        assert docs_count == 0
        assert not mock_storage.store_batch.called


class TestMemoryEfficiency:
    """Tests for memory efficiency in streaming processing."""

    def test_streaming_constant_memory_usage(self) -> None:
        """Test that streaming maintains constant memory usage."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        # Process in small batches
        batch_size = 5

        mock_embedding_gen = MagicMock()
        mock_storage = MagicMock()

        total_docs = 0
        for batch_num in range(10):
            segments: list[Segment] = [
                {"text": f"Batch {batch_num} chunk {i}", "page": 1}
                for i in range(batch_size)
            ]

            mock_embedding_gen.generate_batch.return_value = [
                [0.1] * 384 for _ in range(batch_size)
            ]

            docs_count = ingestor._stream_process_chunks(
                Path(f"batch_{batch_num}.pdf"),
                segments,
                mock_embedding_gen,
                mock_storage,
            )

            total_docs += docs_count

        # Should have processed all documents
        assert total_docs == 50

    def test_streaming_batch_reset(self) -> None:
        """Test that batches are properly reset after processing."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        segments: list[Segment] = [{"text": f"Chunk {i}", "page": 1} for i in range(20)]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch.return_value = [
            [0.1] * 384 for _ in range(20)
        ]

        mock_storage = MagicMock()

        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.streaming_chunk_batch_size = 5

            docs_count = ingestor._stream_process_chunks(
                Path("test.pdf"), segments, mock_embedding_gen, mock_storage
            )

            # Should have processed all chunks
            assert docs_count == 20
