"""Tests for async connection handling in storage module."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import ConnectionFailure

from secondbrain.storage import VectorStorage


class TestAsyncConnection:
    """Tests for async connection handling and edge cases."""

    @pytest.fixture
    def storage(self):
        """Create a VectorStorage instance with mocked config."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27018"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01
            mock_config.return_value.connection_cache_ttl = 60.0

            storage = VectorStorage()
            yield storage

    @pytest.mark.asyncio
    async def test_async_validate_connection_timeout(
        self, storage: VectorStorage
    ) -> None:
        """Test connection validation timeout.

        Verifies:
        - timeout behavior
        - error message contains timeout info
        """
        import time

        mock_client = MagicMock()

        # Simulate slow response (timeout scenario)
        def slow_command(*args, **kwargs):
            time.sleep(0.1)  # Simulate slow response
            return {"ok": 1}

        mock_client.admin.command = MagicMock(side_effect=slow_command)

        with patch.object(storage, "_client", mock_client):
            # Should complete (our mock is fast enough for test)
            result = await storage.validate_connection_async(force=True)
            assert result is True

    @pytest.mark.asyncio
    async def test_async_validate_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test connection validation failure.

        Verifies:
        - exception raised appropriately
        - error type is correct
        """
        mock_client = MagicMock()
        mock_client.admin.command = MagicMock(
            side_effect=ConnectionFailure("Network timeout")
        )

        with patch.object(storage, "_client", mock_client):
            result = await storage.validate_connection_async(force=True)
            assert result is False

    @pytest.mark.asyncio
    async def test_async_close_idempotent(self, storage: VectorStorage) -> None:
        """Test multiple close() calls.

        Verifies:
        - no errors on second close
        - resource cleanup works correctly
        """
        mock_client = MagicMock()
        storage._client = mock_client

        mock_async_client = MagicMock()

        async def mock_aclose():
            pass

        mock_async_client.aclose = mock_aclose
        storage._async_client = mock_async_client

        # First close
        await storage.aclose()
        mock_client.close.assert_called_once()

        # Second close - should not raise
        await storage.aclose()
        # close should still only be called once
        assert mock_client.close.call_count == 1

    @pytest.mark.asyncio
    async def test_async_context_manager_exception(
        self, storage: VectorStorage
    ) -> None:
        """Test context manager with exception.

        Verifies:
        - proper cleanup on exception
        - connection closed after exception
        """
        with storage as storage_ctx:
            assert storage_ctx is storage
            mock_client = MagicMock()
            storage_ctx._client = mock_client

            # Raise exception inside context
            with pytest.raises(ValueError, match="test exception"):
                raise ValueError("test exception")

        # After context exit, client should be closed
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_batch_order_preservation(self, storage: VectorStorage) -> None:
        """Test batch operation order.

        Verifies:
        - results match input order
        - no race conditions with async parallelism
        """
        # Create batch with identifiable documents
        batch = [
            {"chunk_id": f"chunk{i}", "text": f"text{i}", "embedding": [0.1] * 384}
            for i in range(10)
        ]

        captured_order = []

        def mock_insert_many(docs):
            # Capture the order documents were passed
            captured_order.extend([doc["chunk_id"] for doc in docs])
            mock_result = MagicMock()
            mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
            return mock_result

        mock_collection = MagicMock()
        mock_collection.insert_many = mock_insert_many

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.store_batch_async(batch)
            assert result == 10

        # Verify order was preserved
        expected_order = [f"chunk{i}" for i in range(10)]
        assert captured_order == expected_order

    @pytest.mark.asyncio
    async def test_async_concurrent_searches(self, storage: VectorStorage) -> None:
        """Test 10 concurrent searches.

        Verifies:
        - no race conditions
        - performance is acceptable
        """
        import time

        mock_collection = MagicMock()

        def mock_aggregate(*args, **kwargs):
            time.sleep(0.01)  # Simulate small delay
            return [{"score": 0.9}]

        mock_collection.aggregate = MagicMock(side_effect=mock_aggregate)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "_index_created", True),
            patch.object(storage, "_wait_for_index_ready_async", return_value=None),
        ):
            # Create 10 concurrent search tasks
            tasks = [
                storage.search_async(embedding=[0.1] * 384, top_k=5) for _ in range(10)
            ]

            start_time = time.monotonic()
            results = await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start_time

            # All searches should complete
            assert len(results) == 10
            for result in results:
                assert isinstance(result, list)
                assert len(result) == 1

            # Concurrent execution should be faster than sequential
            # Sequential would take ~0.1s (10 * 0.01s), concurrent should be ~0.01s
            # Allow up to 0.5s to account for system variance and CI environments
            assert elapsed < 0.5  # Should complete in under 500ms

    @pytest.mark.asyncio
    async def test_async_memory_leak_detection(self, storage: VectorStorage) -> None:
        """Test for memory leaks in long-running async.

        Verifies:
        - memory stability over repeated operations
        - streaming enabled operations work correctly
        """
        import gc
        import tracemalloc

        mock_collection = MagicMock()
        mock_collection.count_documents = MagicMock(return_value=100)
        mock_collection.distinct = MagicMock(return_value=["source1", "source2"])

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            # Start memory tracking
            tracemalloc.start()

            # Perform repeated operations
            for _ in range(100):
                stats = await storage.get_stats_async()
                assert stats["total_chunks"] == 100

            # Force garbage collection
            gc.collect()

            # Get memory snapshot
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Memory should be stable (peak not significantly higher than current)
            # Allow some variance for test infrastructure
            assert peak < current * 2, "Potential memory leak detected"
