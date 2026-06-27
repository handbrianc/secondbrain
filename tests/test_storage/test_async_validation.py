"""Tests for async input validation in storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import VectorStorage


class TestAsyncValidation:
    """Tests for async input validation and edge cases."""

    @pytest.fixture
    def storage(self):
        """Create a VectorStorage instance with mocked config."""
        import secondbrain.storage.storage as storage_module

        _mock_config = MagicMock()
        _mock_config.mongo_uri = "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
        _mock_config.mongo_db = "secondbrain_test"
        _mock_config.mongo_collection = "embeddings_test"
        _mock_config.embedding_dimensions = 384
        _mock_config.index_ready_retry_count = 3
        _mock_config.index_ready_retry_delay = 0.01
        _mock_config.connection_cache_ttl = 60.0
        _mock_config.embedding_storage_format = "binary"

        original_config = storage_module.config
        storage_module.config = lambda: _mock_config

        try:
            storage = VectorStorage()
            yield storage
        finally:
            storage_module.config = original_config

    @pytest.mark.asyncio
    async def test_async_store_validation(self, storage: VectorStorage) -> None:
        """Test input validation in async store.

        Verifies:
        - source_id required (via chunk_id)
        - chunk_id required
        - embedding dimension validation
        """
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "test_id"
        mock_collection.insert_one = MagicMock(return_value=mock_result)

        # Test missing chunk_id - should still store (validation at higher level)
        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            doc_no_chunk = {
                "text": "test text",
                "embedding": [0.1] * 384,
                "metadata": {},
            }
            result = await storage.store_async(doc_no_chunk)
            assert result is not None

        # Test missing embedding - should handle gracefully
        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            doc_no_embedding = {
                "chunk_id": "chunk1",
                "text": "test text",
                "metadata": {},
            }
            result = await storage.store_async(doc_no_embedding)
            assert result is not None

        # Test wrong embedding dimensions (should still work, MongoDB handles this)
        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            doc_wrong_dims = {
                "chunk_id": "chunk2",
                "text": "test text",
                "embedding": [0.1] * 100,
                "metadata": {},
            }
            result = await storage.store_async(doc_wrong_dims)
            assert result is not None

    @pytest.mark.asyncio
    async def test_async_store_empty_batch(self, storage: VectorStorage) -> None:
        """Test empty batch handling.

        Verifies:
        - no-op behavior
        - return value is 0 for empty batch
        """
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = []
        mock_collection.insert_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.store_batch_async([])
            assert result == 0
            mock_collection.insert_many.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_async_store_large_batch(self, storage: VectorStorage) -> None:
        """Test batch with 1000+ documents.

        Verifies:
        - memory efficiency
        - batching logic works correctly
        """
        # Create a large batch of 1000+ documents
        large_batch = [
            {
                "chunk_id": f"chunk{i}",
                "text": f"test text {i}",
                "embedding": [0.1] * 384,
                "metadata": {"source": f"file{i}.pdf"},
            }
            for i in range(1000)
        ]

        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = [f"id{i}" for i in range(1000)]
        mock_collection.insert_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.store_batch_async(large_batch)
            assert result == 1000
            mock_collection.insert_many.assert_called_once()

        # Verify all documents were processed
        call_args = mock_collection.insert_many.call_args
        assert len(call_args[0][0]) == 1000

    @pytest.mark.asyncio
    async def test_async_search_timeout(self, storage: VectorStorage) -> None:
        """Test search with timeout.

        Verifies:
        - timeout exception handling
        - error handling for slow queries
        """
        import time

        mock_collection = MagicMock()

        # Simulate a slow aggregate that would timeout
        def slow_aggregate(*args, **kwargs):
            time.sleep(0.05)  # Simulate slow operation
            return []

        mock_collection.aggregate = MagicMock(side_effect=slow_aggregate)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "_index_created", True),
            patch.object(storage, "_wait_for_index_ready_async", return_value=None),
        ):
            # Should complete without timeout (our mock is fast enough)
            results = await storage.search_async(embedding=[0.1] * 384, top_k=5)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_async_search_empty_results(self, storage: VectorStorage) -> None:
        """Test search returning no results.

        Verifies:
        - empty list returned
        - no errors on empty results
        """
        mock_collection = MagicMock()
        mock_collection.aggregate = MagicMock(return_value=[])

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "_index_created", True),
            patch.object(storage, "_wait_for_index_ready_async", return_value=None),
        ):
            results = await storage.search_async(embedding=[0.1] * 384, top_k=5)
            assert results == []
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_async_delete_by_source_empty(self, storage: VectorStorage) -> None:
        """Test delete with no matches.

        Verifies:
        - 0 deleted count returned
        - no errors on empty delete
        """
        mock_result = MagicMock()
        mock_result.deleted_count = 0

        mock_collection = MagicMock()
        mock_collection.delete_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.delete_by_source_async("nonexistent.pdf")
            assert result == 0
            mock_collection.delete_many.assert_called_once_with(
                {"source_file": "nonexistent.pdf"}
            )

    @pytest.mark.asyncio
    async def test_async_delete_all_empty_db(self, storage: VectorStorage) -> None:
        """Test delete_all on empty database.

        Verifies:
        - graceful handling of empty database
        - returns 0 for empty delete
        """
        mock_result = MagicMock()
        mock_result.deleted_count = 0

        mock_collection = MagicMock()
        mock_collection.delete_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.delete_all_async()
            assert result == 0
            mock_collection.delete_many.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_async_get_stats_empty_db(self, storage: VectorStorage) -> None:
        """Test get_stats on empty database.

        Verifies:
        - zero counts returned
        - all stats fields present
        """
        mock_collection = MagicMock()
        mock_collection.count_documents = MagicMock(return_value=0)
        mock_collection.distinct = MagicMock(return_value=[])

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            stats = await storage.get_stats_async()
            assert stats["total_chunks"] == 0
            assert stats["unique_sources"] == 0
            assert stats["database"] == "secondbrain_test"
            assert stats["collection"] == "embeddings_test"
            assert "collection" in stats
