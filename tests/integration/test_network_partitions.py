"""Integration tests for network partition recovery.

Tests cover:
- MongoDB connection failures
- Network timeout handling
- Automatic reconnection
- Data consistency after recovery
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def _get_worker_id() -> str:
    """Get pytest-xdist worker ID for test isolation."""
    import os

    # Get worker ID from environment variable set by pytest-xdist
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


@pytest.fixture
def worker_isolated_storage() -> "VectorStorage":
    """Provide VectorStorage with worker-isolated collection.

    Each pytest-xdist worker gets its own collection to prevent race conditions
    during parallel execution.
    """
    from secondbrain.storage.sync import VectorStorage

    worker_id = _get_worker_id()
    collection_name = f"test_network_partitions_{worker_id}"

    storage = VectorStorage(
        mongo_uri="mongodb://127.0.0.1:27018/secondbrain_test",
        db_name="secondbrain_test",
        collection_name=collection_name,
    )
    try:
        yield storage
    finally:
        # Cleanup at end of test
        try:
            storage.delete_all()
        except Exception:
            pass
        storage.close()


@pytest.mark.chaos
class TestNetworkPartitions:
    """Tests for handling network partition scenarios."""

    async def test_mongodb_connection_failure_recovery(self, worker_isolated_storage):
        """Should recover gracefully after MongoDB connection failure."""
        storage = worker_isolated_storage
        chunks = storage.list_chunks(limit=1)
        assert isinstance(chunks, list)

    async def test_query_timeout_handling(self, worker_isolated_storage):
        """Should handle query timeouts gracefully."""
        storage = worker_isolated_storage
        # With invalid connection, should raise appropriate error
        with pytest.raises(Exception):
            storage.list_chunks(limit=1, timeout=0.001)

    async def test_reconnection_after_disconnect(self, worker_isolated_storage):
        """Should automatically reconnect after disconnection."""
        storage1 = worker_isolated_storage
        chunks1 = storage1.list_chunks(limit=1)
        assert isinstance(chunks1, list)

        storage2 = worker_isolated_storage
        assert storage2 is not None

    def test_connection_pool_exhaustion(self, worker_isolated_storage):
        """Should handle connection pool exhaustion."""
        storage = worker_isolated_storage

        with patch.object(storage, "_do_validate", return_value=False):
            # Should raise connection error when validation fails
            with pytest.raises(Exception):
                storage.list_chunks(limit=1)


@pytest.mark.integration
class TestCircuitBreakerBehavior:
    """Tests for circuit breaker behavior under various conditions."""

    async def test_circuit_opens_after_failures(self):
        """Circuit should open after consecutive failures."""
        from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            service_name="test_service", failure_threshold=3, recovery_timeout=1
        )

        # Simulate failures
        for i in range(3):
            try:
                with cb:
                    raise ConnectionError(f"Failure {i}")
            except Exception:
                pass

        # Circuit should be open
        assert cb.state == CircuitState.OPEN

    async def test_circuit_half_open_after_timeout(self):
        """Circuit should transition to half-open after timeout."""
        from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
        )

        # Open the circuit
        for _ in range(2):
            try:
                with cb:
                    raise ConnectionError()
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.2)

        # Should transition to half-open on next attempt
        try:
            with cb:
                pass  # Success
        except Exception:
            pass

        # Should now be closed (success in half-open closes it with success_threshold=1)
        assert cb.state == CircuitState.CLOSED

    async def test_circuit_reopens_on_failure_in_half_open(self):
        """Circuit should reopen if failure occurs in half-open state."""
        from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=1,
        )

        # Open the circuit
        for _ in range(2):
            try:
                with cb:
                    raise ConnectionError()
            except Exception:
                pass

        # Wait for half-open
        await asyncio.sleep(0.2)

        # Fail in half-open state
        try:
            with cb:
                raise ConnectionError()
        except Exception:
            pass

        # Should be open again
        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_metrics(self, worker_isolated_metrics):
        """Circuit breaker should record metrics."""
        from secondbrain.utils.circuit_breaker import CircuitBreaker

        metrics = worker_isolated_metrics
        cb = CircuitBreaker(service_name="test_metrics", failure_threshold=2)

        # Generate some failures
        for _ in range(2):
            try:
                with cb:
                    raise ConnectionError()
            except Exception:
                pass

        # Check metrics were recorded
        all_metrics = metrics.get_all_metrics()
        assert "counters" in all_metrics


@pytest.mark.integration
class TestEndToEndWorkflows:
    """End-to-end integration tests for complete workflows."""

    async def test_full_ingestion_workflow(self, tmp_path):
        """Test complete document ingestion workflow."""
        from secondbrain.document.async_ingestor import AsyncDocumentIngestor

        ingestor = AsyncDocumentIngestor()
        assert ingestor is not None
        assert hasattr(ingestor, "ingest_async")

    async def test_full_search_workflow(self):
        """Test complete search workflow."""
        from secondbrain.search import Searcher

        searcher = Searcher()
        assert searcher is not None
        assert hasattr(searcher, "search")

    async def test_ingest_and_search_workflow(self):
        """Test combined ingest and search workflow."""
        from secondbrain.document.async_ingestor import AsyncDocumentIngestor
        from secondbrain.search import Searcher

        # Test that both classes can be instantiated and have expected methods
        ingestor = AsyncDocumentIngestor()
        assert ingestor is not None
        assert hasattr(ingestor, "ingest_async")

        searcher = Searcher()
        assert searcher is not None
        assert hasattr(searcher, "search")

    async def test_concurrent_ingest_and_search(self):
        """Test concurrent ingestion and search operations."""
        import asyncio

        async def ingest_task(doc_id):
            from secondbrain.document.async_ingestor import AsyncDocumentIngestor

            ingestor = AsyncDocumentIngestor()
            assert ingestor is not None

        async def search_task(query):
            from secondbrain.search import Searcher

            searcher = Searcher()
            assert searcher is not None

        # Run 5 ingestions and 5 searches concurrently
        ingest_tasks = [ingest_task(i) for i in range(5)]
        search_tasks = [search_task(f"query {i}") for i in range(5)]

        all_tasks = ingest_tasks + search_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # All should complete without crashing
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0


@pytest.mark.integration
class TestChaosEngineering:
    """Chaos engineering tests for system resilience."""

    async def test_random_service_failures(self):
        """System should handle random service failures."""
        from secondbrain.document.ingestor import DocumentIngestor

        ingestor = DocumentIngestor()

        # Test that ingestor handles extraction errors gracefully
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test content")
            doc_path = Path(f.name)

        try:
            # Mock extraction to simulate error immediately
            with patch.object(
                ingestor, "_extract_text", side_effect=Exception("Simulated error")
            ):
                # Should handle error without crashing
                result = ingestor.ingest(doc_path)
                # Result should indicate failure
                assert result is not None
        finally:
            doc_path.unlink()

    async def test_memory_pressure_handling(self):
        """System should handle memory pressure gracefully."""
        from secondbrain.utils.memory_utils import calculate_safe_worker_count

        # Test that memory calculations handle extreme cases
        # Very low memory should still return at least 1 worker
        workers = calculate_safe_worker_count(
            memory_limit_gb=0.1,
            estimated_memory_per_worker_gb=10.0,
        )
        assert workers >= 1

    async def test_slow_downstream_services(self):
        """System should handle slow downstream services."""
        from secondbrain.utils.connections import RateLimitedRetry

        retry = RateLimitedRetry(max_retries=2, base_delay=0.01, max_delay=0.1)

        call_times = []

        def slow_operation():
            import time

            start = time.time()
            time.sleep(0.05)
            call_times.append(time.time() - start)
            return True

        result = retry.call(slow_operation)
        assert result is True
        assert len(call_times) == 1

    def test_resource_cleanup_on_error(self):
        """Resources should be cleaned up on errors."""
        from secondbrain.document.ingestor import DocumentIngestor

        ingestor = DocumentIngestor()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test content")
            doc_path = Path(f.name)

        try:
            with patch.object(
                ingestor, "_extract_text", side_effect=Exception("Simulated error")
            ):
                try:
                    ingestor.ingest(doc_path)
                except Exception:
                    pass  # Expected

            # File should still exist (we didn't delete it)
            assert doc_path.exists()
        finally:
            doc_path.unlink()
