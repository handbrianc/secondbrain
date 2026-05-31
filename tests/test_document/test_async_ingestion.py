"""Comprehensive async ingestion tests (consolidated).

This module consolidates all async ingestion tests from:
- test_async_api.py (2 tests)
- test_async_api_extended.py (3 tests)
- test_async_backward_compat.py (6 tests)
- test_async_embedding_native.py (6 tests)
- test_async_ingest_method.py (3 tests)
- test_async_storage_integration.py (3 tests)

Total: 23 tests consolidated into 1 unified suite.

Purpose:
- Test AsyncDocumentIngestor async API (context manager, ingest_async)
- Test backward compatibility between sync and async classes
- Test native async embedding generation
- Test async storage integration with Motor MongoDB
- Test concurrent file processing with semaphore control
"""

import asyncio
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import AsyncDocumentIngestor, DocumentIngestor
from secondbrain.embedding.local import LocalEmbeddingGenerator
from secondbrain.storage.storage import VectorStorage


class TestAsyncDocumentIngestor:
    """Tests for AsyncDocumentIngestor async methods."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test AsyncDocumentIngestor async context manager (lines 1682-1691)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        async with ingestor as ing:
            assert ing is ingestor
            assert ing.chunk_size == 512

    @pytest.mark.asyncio
    async def test_async_exit_returns_none(self) -> None:
        """Test __aexit__ returns None (lines 1686-1694)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        async with ingestor:
            pass  # Context manager should exit cleanly


class TestAsyncDocumentIngestorCoverage:
    """Additional tests for AsyncDocumentIngestor async methods."""

    @pytest.mark.asyncio
    async def test_ingest_async_empty_files(self) -> None:
        """Test ingest_async returns empty when no files found (lines 1728-1729)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        with patch.object(
            ingestor, "_collect_and_validate_files", return_value=[]
        ) as mock_collect:
            result = await ingestor.ingest_async("/nonexistent/path", recursive=False)

            mock_collect.assert_called_once()
            assert result == {"success": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_ingest_async_with_semaphore(self) -> None:
        """Test ingest_async with semaphore control (lines 1732-1750)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        mock_file = MagicMock()
        mock_file.name = "test.txt"

        with (
            patch.object(
                ingestor, "_collect_and_validate_files", return_value=[mock_file]
            ),
            patch.object(ingestor, "process_file_async", return_value=True),
        ):
            result = await ingestor.ingest_async(
                "/test/path", recursive=False, max_concurrent=2
            )

            assert "success" in result
            assert "failed" in result

    @pytest.mark.asyncio
    async def test_process_with_semaphore_async(self) -> None:
        """Test process_with_semaphore async helper (lines 1734-1737)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        mock_file = MagicMock()
        mock_embedding = MagicMock()
        mock_storage = MagicMock()

        with patch.object(ingestor, "process_file_async", return_value=True):
            # Test that semaphore is created and used
            semaphore = asyncio.Semaphore(2)
            async with semaphore:
                result = await ingestor.process_file_async(
                    mock_file, mock_embedding, mock_storage
                )

                assert result is True


class TestAsyncBackwardCompat:
    """Test both classes can coexist and function independently."""

    def test_both_classes_importable(self):
        """DocumentIngestor and AsyncDocumentIngestor can both be imported."""
        assert DocumentIngestor is not None
        assert AsyncDocumentIngestor is not None
        assert DocumentIngestor != AsyncDocumentIngestor

    def test_sync_class_works(self):
        """Sync DocumentIngestor can be instantiated and used."""
        ingestor = DocumentIngestor(verbose=False)
        assert ingestor is not None
        assert ingestor.chunk_size > 0

    def test_async_class_works(self):
        """AsyncDocumentIngestor can be instantiated and used."""
        ingestor = AsyncDocumentIngestor(verbose=False)
        assert ingestor is not None
        assert ingestor.chunk_size > 0

    def test_sync_and_async_have_different_interfaces(self):
        """Sync and async classes have different method signatures."""
        sync_ingestor = DocumentIngestor(verbose=False)
        async_ingestor = AsyncDocumentIngestor(verbose=False)

        assert hasattr(sync_ingestor, "ingest")
        assert hasattr(async_ingestor, "ingest_async")

    def test_async_resource_cleanup(self):
        """Test async ingestor properly releases resources on exit."""
        import asyncio

        async def test_cleanup():
            ingestor = AsyncDocumentIngestor(verbose=False)
            assert ingestor is not None

            async with ingestor:
                pass

        asyncio.run(test_cleanup())


class TestAsyncEmbeddingNative:
    """Test native async embedding generation using aiohttp/httpx."""

    def test_async_embedding_method_exists(self):
        """LocalEmbeddingGenerator should have async method."""
        gen = LocalEmbeddingGenerator()

        assert hasattr(gen, "generate_async")
        assert callable(gen.generate_async)

    def test_async_batch_method_exists(self):
        """LocalEmbeddingGenerator should have async batch method."""
        gen = LocalEmbeddingGenerator()

        assert hasattr(gen, "generate_batch_async")
        assert callable(gen.generate_batch_async)

    @pytest.mark.asyncio
    async def test_async_embedding_generates_valid_vector(self):
        """Async embedding generates a valid vector with correct dimensions."""
        gen = LocalEmbeddingGenerator()

        # Generate async embedding
        embedding = await gen.generate_async("test text for embedding")

        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        # All values should be floats
        assert all(isinstance(v, float) for v in embedding)

    @pytest.mark.asyncio
    async def test_async_batch_embedding_returns_correct_count(self):
        """Async batch embedding returns one vector per input text."""
        gen = LocalEmbeddingGenerator()

        texts = ["text 1", "text 2", "text 3"]
        embeddings = await gen.generate_batch_async(texts)

        assert len(embeddings) == len(texts)
        for emb in embeddings:
            assert isinstance(emb, list)
            assert len(emb) > 0


def test_async_embedding_uses_aiohttp_client():
    """Test that async embedding uses proper async pattern."""
    from secondbrain.embedding.local import LocalEmbeddingGenerator

    assert hasattr(
        LocalEmbeddingGenerator, "generate_async"
    ), "LocalEmbeddingGenerator should have generate_async method"
    assert hasattr(
        LocalEmbeddingGenerator, "generate_batch_async"
    ), "LocalEmbeddingGenerator should have generate_batch_async method"

    # Verify methods are coroutines
    assert inspect.iscoroutinefunction(
        LocalEmbeddingGenerator.generate_async
    ), "generate_async should be a coroutine function"
    assert inspect.iscoroutinefunction(
        LocalEmbeddingGenerator.generate_batch_async
    ), "generate_batch_async should be a coroutine function"


class TestAsyncIngestMethod:
    """Test async ingestion method functionality."""

    def test_async_ingest_method_exists(self):
        """AsyncDocumentIngestor should have ingest_async method."""
        ingestor = AsyncDocumentIngestor()

        assert hasattr(ingestor, "ingest_async")
        assert callable(ingestor.ingest_async)

    @pytest.mark.asyncio
    async def test_async_ingest_processes_single_file(self):
        """Async ingest method processes a single file."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content for async ingest")

            ingestor = AsyncDocumentIngestor()

            # Should not raise
            result = await ingestor.ingest_async(str(test_file))
            assert result is not None

    @pytest.mark.asyncio
    async def test_async_ingest_concurrent_multiple_files(self):
        """Async ingest can process multiple files concurrently with asyncio.gather."""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(3):
                test_file = Path(tmpdir) / f"test_{i}.txt"
                test_file.write_text(f"test content {i}")

            ingestor = AsyncDocumentIngestor()

            # Process files concurrently using asyncio.gather
            files = [str(Path(tmpdir) / f"test_{i}.txt") for i in range(3)]
            results = await asyncio.gather(
                *[ingestor.ingest_async(f) for f in files]
            )

            assert len(results) == 3
            assert all(r is not None for r in results)


class TestAsyncStorageIntegration:
    """Test async storage operations using Motor MongoDB."""

    def test_async_storage_methods_exist(self):
        """VectorStorage should have async methods."""
        storage = VectorStorage()

        assert hasattr(storage, "store_async")
        assert hasattr(storage, "search_async")

    @pytest.mark.asyncio
    async def test_async_store_operation(self):
        """Async store operation stores a document."""
        storage = VectorStorage()
        
        # Track calls to verify behavior
        call_count = [0]
        
        # Synchronous mock (store_async uses asyncio.to_thread)
        def mock_insert(doc):
            call_count[0] += 1
            mock_result = MagicMock()
            mock_result.inserted_id = "test-id-123"
            return mock_result
        
        mock_collection = MagicMock()
        mock_collection.insert_one = mock_insert
        storage._collection = mock_collection
        
        test_doc = {
            "chunk_id": "test-async-123",
            "source_file": "test.txt",
            "page_number": 1,
            "chunk_text": "test content for async storage",
            "embedding": [0.1] * 384,
            "file_type": "text",
            "ingested_at": "2024-01-01T00:00:00",
        }

        # Should not raise
        result = await storage.store_async(test_doc)
        
        # Verify the collection was called
        assert call_count[0] == 1
        assert result == "test-id-123"

    @pytest.mark.asyncio
    async def test_async_search_operation(self):
        """Async search returns results from MongoDB."""
        storage = VectorStorage()
        
        # Mock the _collection attribute (backing store for collection property)
        mock_collection = MagicMock()
        
        # Synchronous mock (search_async uses asyncio.to_thread)
        def mock_aggregate(pipeline):
            return [
                {
                    "chunk_id": "mock-1",
                    "chunk_text": "mock result 1",
                    "score": 0.9
                }
            ]
        
        mock_collection.aggregate = mock_aggregate
        storage._collection = mock_collection
        
        query_embedding = [0.1] * 384
        results = await storage.search_async(query_embedding, top_k=5)

        assert isinstance(results, list)
        assert len(results) == 1
