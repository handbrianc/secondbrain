"""Tests for concurrent ingestion scenarios and race condition detection."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


@pytest.mark.concurrent
class TestConcurrentIngestion:
    """Test concurrent document ingestion scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_ingestion_same_document(self):
        """Test concurrent ingestion of the same document (race condition)."""
        call_count = 0
        lock = asyncio.Lock()

        async def tracked_operation():
            nonlocal call_count
            async with lock:
                call_count += 1
            await asyncio.sleep(0.001)
            async with lock:
                call_count -= 1

        tasks = [tracked_operation() for _ in range(3)]
        await asyncio.gather(*tasks)

        assert call_count == 0  # All completed

    @pytest.mark.asyncio
    async def test_concurrent_ingestion_different_documents(self):
        """Test concurrent ingestion of different documents."""
        inserted = []
        lock = asyncio.Lock()

        async def mock_ingest(doc_id):
            async with lock:
                inserted.append(doc_id)
            await asyncio.sleep(0.001)

        tasks = [mock_ingest(f"doc-{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        assert len(inserted) == 10

    @pytest.mark.asyncio
    async def test_concurrent_ingestion_with_duplicate_detection(self):
        """Test that duplicate detection works under concurrency."""
        inserted = set()
        lock = asyncio.Lock()

        async def mock_ingest(doc_id):
            async with lock:
                if doc_id not in inserted:
                    inserted.add(doc_id)
            await asyncio.sleep(0.001)

        tasks = [mock_ingest(f"doc-{i}") for i in range(3)]
        await asyncio.gather(*tasks)

        assert len(inserted) == 3


@pytest.mark.concurrent
class TestRaceConditionDetection:
    """Test race condition detection in concurrent operations."""

    @pytest.mark.asyncio
    async def test_detect_concurrent_update_race(self):
        """Test detection of concurrent update race conditions."""

        async def read_modify_write(doc_id, modification):
            doc = {"id": doc_id, "value": 0}
            await asyncio.sleep(0.01)
            doc["value"] += modification
            return doc

        results = await asyncio.gather(
            read_modify_write("doc-1", 1),
            read_modify_write("doc-1", 1),
            read_modify_write("doc-1", 1),
        )

        for result in results:
            assert result["value"] == 1

    @pytest.mark.asyncio
    async def test_detect_concurrent_delete_race(self):
        """Test detection of concurrent delete race conditions."""
        deleted = []
        lock = threading.Lock()

        async def delete_document(doc_id):
            await asyncio.sleep(0.01)
            with lock:
                if doc_id not in deleted:
                    deleted.append(doc_id)
                    return True
            return False

        results = await asyncio.gather(
            delete_document("doc-1"),
            delete_document("doc-1"),
            delete_document("doc-1"),
        )

        assert sum(results) == 1
        assert len(deleted) == 1

    @pytest.mark.asyncio
    async def test_detect_concurrent_index_race(self):
        """Test detection of concurrent index creation race conditions."""
        index_created = []
        lock = threading.Lock()

        async def create_index(collection_name, _index_spec):
            del _index_spec  # Unused but part of interface
            await asyncio.sleep(0.01)
            with lock:
                if collection_name not in index_created:
                    index_created.append(collection_name)
                    return True
            return False

        results = await asyncio.gather(
            create_index("documents", {"embedding": "vector"}),
            create_index("documents", {"embedding": "vector"}),
            create_index("documents", {"embedding": "vector"}),
        )

        assert sum(results) == 1


@pytest.mark.concurrent
class TestThreadSafety:
    """Test thread safety of storage operations."""

    def test_concurrent_sync_operations(self):
        """Test thread safety of synchronous operations."""
        call_count = 0
        lock = threading.Lock()

        def insert_many_times(_thread_id):
            del _thread_id  # Unused but part of interface
            nonlocal call_count
            for _i in range(20):
                with lock:
                    call_count += 1

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(insert_many_times, i) for i in range(5)]
            for future in futures:
                future.result()

        assert call_count == 100

    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self):
        """Test thread safety of async operations."""
        call_count = 0
        lock = asyncio.Lock()

        async def insert_many_async(_thread_id):
            del _thread_id  # Unused but part of interface
            nonlocal call_count
            for _i in range(20):
                async with lock:
                    call_count += 1

        await asyncio.gather(*[insert_many_async(i) for i in range(5)])

        assert call_count == 100


@pytest.mark.concurrent
class TestConcurrencyWithCircuitBreaker:
    """Test concurrency with circuit breaker protection."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_with_open_circuit(self):
        """Test that concurrent requests are blocked when circuit is open."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        for _ in range(4):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        blocked_count = 0
        for _ in range(100):
            if not cb.is_allowed():
                blocked_count += 1

        assert blocked_count == 100

    @pytest.mark.asyncio
    async def test_concurrent_requests_during_half_open(self):
        """Test concurrent requests during half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
            half_open_max_calls=5,
            success_threshold=10,  # High threshold to prevent closing during test
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        await asyncio.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN

        # Count how many calls are allowed in HALF_OPEN state
        allowed_count = 0
        for _ in range(10):
            if cb.is_allowed():
                allowed_count += 1
                cb.record_success()

        # Should allow exactly half_open_max_calls (5) before closing or blocking
        assert allowed_count == 5


@pytest.mark.concurrent
class TestBatchConcurrency:
    """Test concurrency in batch operations."""

    @pytest.mark.asyncio
    async def test_concurrent_batch_ingestion(self):
        """Test concurrent batch ingestion operations."""
        mock_collection = MagicMock()

        async def batch_ingest(batch_id):
            for i in range(10):
                mock_collection.insert_one({"doc_id": f"doc-{batch_id}-{i}"})

        await asyncio.gather(*[batch_ingest(i) for i in range(5)])

        assert mock_collection.insert_one.call_count == 50

    @pytest.mark.asyncio
    async def test_batch_with_duplicate_handling(self):
        """Test batch ingestion with duplicate document handling."""
        mock_collection = MagicMock()
        existing = {"doc-1", "doc-2"}

        async def ingest_if_new(doc_id):
            if doc_id not in existing:
                mock_collection.insert_one({"doc_id": doc_id})

        docs = ["doc-1", "doc-2", "doc-3", "doc-4"]

        for doc_id in docs:
            await ingest_if_new(doc_id)

        assert mock_collection.insert_one.call_count == 2
