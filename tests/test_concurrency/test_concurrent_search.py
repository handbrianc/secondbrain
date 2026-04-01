"""Tests for concurrent search scenarios."""

import asyncio
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


@pytest.mark.concurrent
class TestConcurrentSearch:
    """Test concurrent search operations."""

    @pytest.mark.asyncio
    async def test_concurrent_search_queries(self):
        """Test multiple concurrent search queries."""
        results = []
        lock = asyncio.Lock()

        async def mock_search(query):
            result = [{"doc_id": f"doc-{i}", "score": 0.9 - i * 0.1} for i in range(5)]
            async with lock:
                results.append(result)
            await asyncio.sleep(0.001)

        tasks = [mock_search(f"query-{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_concurrent_search_and_ingest(self):
        """Test concurrent search and ingestion operations."""
        mock_collection = MagicMock()

        async def search_operation():
            await asyncio.sleep(0.01)
            return [{"doc_id": "result", "score": 0.9}]

        async def ingest_operation(doc_id):
            mock_collection.insert_one({"doc_id": doc_id})
            await asyncio.sleep(0.01)

        operations = [
            search_operation(),
            ingest_operation("new-doc-1"),
            search_operation(),
            ingest_operation("new-doc-2"),
            search_operation(),
        ]

        await asyncio.gather(*operations)

        assert mock_collection.insert_one.call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_search_different_collections(self):
        """Test concurrent searches on different collections."""

        async def search_collection(collection_name):
            await asyncio.sleep(0.01)
            return [{"doc_id": "result", "score": 0.9}]

        results = await asyncio.gather(
            *[search_collection(f"collection-{i}") for i in range(5)]
        )

        assert len(results) == 5


@pytest.mark.concurrent
class TestSearchRaceConditions:
    """Test race conditions in search operations."""

    @pytest.mark.asyncio
    async def test_search_during_ingestion(self):
        """Test search behavior during concurrent ingestion."""
        ingestion_complete = asyncio.Event()

        async def simulate_ingestion():
            await asyncio.sleep(0.01)
            ingestion_complete.set()

        async def simulate_search():
            await asyncio.sleep(0.01)
            return [{"doc_id": "result", "score": 0.9}]

        ingest_task = asyncio.create_task(simulate_ingestion())
        search_result = await simulate_search()
        await ingest_task

        assert search_result is not None

    @pytest.mark.asyncio
    async def test_concurrent_index_creation_and_search(self):
        """Test search behavior during index creation."""

        async def create_index():
            await asyncio.sleep(0.01)
            return True

        async def search_with_index():
            await asyncio.sleep(0.01)
            return [{"doc_id": "result", "score": 0.9}]

        results = await asyncio.gather(
            create_index(),
            search_with_index(),
        )

        assert results[0] is True
        assert results[1] is not None


@pytest.mark.concurrent
class TestSearchPerformanceUnderLoad:
    """Test search performance under concurrent load."""

    @pytest.mark.asyncio
    async def test_search_latency_under_concurrency(self):
        """Test search latency with concurrent queries."""
        search_times = []

        async def slow_search():
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(0.01)
            end = asyncio.get_event_loop().time()
            search_times.append(end - start)
            return [{"doc_id": "result", "score": 0.9}]

        await asyncio.gather(*[slow_search() for _ in range(20)])

        for latency in search_times:
            assert latency < 0.1

    @pytest.mark.asyncio
    async def test_search_throughput_under_load(self):
        """Test search throughput under concurrent load."""
        completed = 0

        async def count_search():
            nonlocal completed
            await asyncio.sleep(0.01)
            completed += 1

        await asyncio.gather(*[count_search() for _ in range(50)])

        assert completed == 50


@pytest.mark.concurrent
class TestSearchWithCircuitBreaker:
    """Test search behavior with circuit breaker."""

    @pytest.mark.asyncio
    async def test_search_blocked_when_circuit_open(self):
        """Test that search is blocked when circuit is open."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        for _ in range(4):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.is_allowed() is False

    @pytest.mark.asyncio
    async def test_search_allowed_when_circuit_closed(self):
        """Test that search is allowed when circuit is closed."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

    @pytest.mark.asyncio
    async def test_concurrent_search_during_circuit_recovery(self):
        """Test concurrent searches during circuit recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
            success_threshold=2,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        await asyncio.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED


@pytest.mark.concurrent
class TestSearchConsistency:
    """Test search consistency under concurrent modifications."""

    @pytest.mark.asyncio
    async def test_search_sees_consistent_results(self):
        """Test that search returns consistent results."""

        async def mock_search():
            await asyncio.sleep(0.01)
            return [{"doc_id": "doc-1", "score": 0.9}]

        results = await asyncio.gather(*[mock_search() for _ in range(5)])

        for result in results:
            assert len(result) == 1
            assert result[0]["doc_id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_search_after_concurrent_deletion(self):
        """Test search behavior after concurrent deletion."""
        mock_collection = MagicMock()

        async def delete_document(doc_id):
            mock_collection.delete_one({"doc_id": doc_id})
            await asyncio.sleep(0.01)

        await delete_document("doc-1")

        assert mock_collection.delete_one.call_count == 1
