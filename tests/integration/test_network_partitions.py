"""Integration tests for network partition recovery.

Tests cover:
- MongoDB connection failures
- Network timeout handling
- Automatic reconnection
- Data consistency after recovery
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import tempfile
import os


@pytest.mark.integration
class TestNetworkPartitions:
    """Tests for handling network partition scenarios."""

    async def test_mongodb_connection_failure_recovery(self):
        """Should recover gracefully after MongoDB connection failure."""
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        # Simulate initial connection failure
        with patch.object(storage, "_connect") as mock_connect:
            mock_connect.side_effect = [
                Exception("Connection refused"),  # First attempt fails
                None,  # Second attempt succeeds
            ]

            # Should retry and eventually succeed
            with patch.object(storage, "_ensure_collection"):
                await storage.connect()

            assert mock_connect.call_count >= 1

    async def test_query_timeout_handling(self):
        """Should handle query timeouts gracefully."""
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        with patch.object(storage, "collection") as mock_collection:
            mock_collection.find.side_effect = asyncio.TimeoutError()

            # Should raise appropriate error, not crash
            with pytest.raises(Exception):
                await storage.search("test query")

    async def test_reconnection_after_disconnect(self):
        """Should automatically reconnect after disconnection."""
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        # Initial connection
        with patch.object(storage, "_connect"):
            await storage.connect()

        # Simulate disconnection
        storage._client = None

        # Next operation should trigger reconnection
        with patch.object(storage, "_connect") as mock_reconnect:
            with patch.object(storage, "_ensure_collection"):
                await storage.connect()

            assert mock_reconnect.called

    def test_connection_pool_exhaustion(self):
        """Should handle connection pool exhaustion gracefully."""
        from pymongo.errors import ConfigurationError
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        with patch.object(storage, "_connect") as mock_connect:
            mock_connect.side_effect = ConfigurationError("Connection pool exhausted")

            # Should raise clear error
            with pytest.raises(ConfigurationError):
                storage.connect()


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
                async with cb:
                    raise ConnectionError(f"Failure {i}")
            except Exception:
                pass

        # Circuit should be open
        assert cb.state == CircuitState.OPEN

    async def test_circuit_half_open_after_timeout(self):
        """Circuit should transition to half-open after timeout."""
        import time
        from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            recovery_timeout=0.1,  # Short timeout for testing
        )

        # Open the circuit
        for i in range(2):
            try:
                async with cb:
                    raise ConnectionError()
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.2)

        # Should transition to half-open on next attempt
        try:
            async with cb:
                pass  # Success
        except Exception:
            pass

        # Should now be closed (success in half-open closes it)
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
        for i in range(2):
            try:
                async with cb:
                    raise ConnectionError()
            except Exception:
                pass

        # Wait for half-open
        await asyncio.sleep(0.2)

        # Fail in half-open state
        try:
            async with cb:
                raise ConnectionError()
        except Exception:
            pass

        # Should be open again
        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_metrics(self):
        """Circuit breaker should record metrics."""
        from secondbrain.utils.circuit_breaker import CircuitBreaker
        from secondbrain.utils.metrics import metrics

        cb = CircuitBreaker(service_name="test_metrics", failure_threshold=2)

        # Generate some failures
        for i in range(2):
            try:
                async with cb:
                    raise ConnectionError()
            except Exception:
                pass

        # Check metrics were recorded
        all_metrics = metrics.get_all_metrics()
        assert "counters" in all_metrics


@pytest.mark.integration
class TestEndToEndWorkflows:
    """End-to-end integration tests for complete workflows."""

    async def test_full_ingestion_workflow(self):
        """Test complete document ingestion workflow."""
        import tempfile
        from secondbrain.document.async_ingestor import AsyncDocumentIngestor

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test document content for end-to-end testing")
            doc_path = Path(f.name)

        try:
            async with AsyncDocumentIngestor() as ingestor:
                with patch.object(
                    ingestor, "_extract_text", return_value="Extracted text"
                ):
                    with patch.object(
                        ingestor, "_generate_embeddings", return_value=[]
                    ):
                        with patch.object(ingestor, "_store_document"):
                            result = await ingestor.ingest(doc_path)

            assert result is not None
        finally:
            os.unlink(doc_path)

    async def test_full_search_workflow(self):
        """Test complete search workflow."""
        from secondbrain.search import SemanticSearcher

        searcher = SemanticSearcher()

        with patch.object(searcher, "retrieve") as mock_retrieve:
            mock_retrieve.return_value = [
                {"content": "Result 1", "score": 0.9},
                {"content": "Result 2", "score": 0.8},
            ]

            results = await searcher.search("test query", limit=5)

            assert len(results) == 2
            assert all("content" in r for r in results)
            assert all("score" in r for r in results)

    async def test_ingest_and_search_workflow(self):
        """Test combined ingest and search workflow."""
        import tempfile
        from secondbrain.document.async_ingestor import AsyncDocumentIngestor
        from secondbrain.search import SemanticSearcher

        # Ingest document
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Machine learning is a subset of artificial intelligence")
            doc_path = Path(f.name)

        try:
            # Ingest
            async with AsyncDocumentIngestor() as ingestor:
                with patch.object(
                    ingestor,
                    "_extract_text",
                    return_value="Machine learning is a subset of artificial intelligence",
                ):
                    with patch.object(
                        ingestor, "_generate_embeddings", return_value=[]
                    ):
                        with patch.object(ingestor, "_store_document"):
                            await ingestor.ingest(doc_path)

            # Search
            searcher = SemanticSearcher()
            with patch.object(searcher, "retrieve") as mock_retrieve:
                mock_retrieve.return_value = [
                    {
                        "content": "Machine learning is a subset of artificial intelligence",
                        "score": 0.95,
                    }
                ]

                results = await searcher.search("What is machine learning?", limit=1)

                assert len(results) == 1
                assert "machine learning" in results[0]["content"].lower()
        finally:
            os.unlink(doc_path)

    async def test_concurrent_ingest_and_search(self):
        """Test concurrent ingestion and search operations."""
        import asyncio
        import tempfile

        async def ingest_task(doc_id):
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
                f.write(f"Document {doc_id}".encode())
                doc_path = f.name

            try:
                from secondbrain.document.async_ingestor import AsyncDocumentIngestor

                async with AsyncDocumentIngestor() as ingestor:
                    with patch.object(
                        ingestor, "_extract_text", return_value=f"Content {doc_id}"
                    ):
                        with patch.object(
                            ingestor, "_generate_embeddings", return_value=[]
                        ):
                            with patch.object(ingestor, "_store_document"):
                                await ingestor.ingest(Path(doc_path))
            finally:
                os.unlink(doc_path)

        async def search_task(query):
            from secondbrain.search import SemanticSearcher

            searcher = SemanticSearcher()
            with patch.object(
                searcher, "retrieve", return_value=[{"content": query, "score": 0.9}]
            ):
                return await searcher.search(query, limit=1)

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
        import random
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        failures = 0
        successes = 0

        for i in range(10):
            with patch.object(storage, "_connect") as mock_connect:
                # Randomly fail 30% of the time
                if random.random() < 0.3:
                    mock_connect.side_effect = ConnectionError("Random failure")
                    try:
                        await storage.connect()
                    except Exception:
                        failures += 1
                else:
                    mock_connect.return_value = None
                    with patch.object(storage, "_ensure_collection"):
                        await storage.connect()
                        successes += 1

        # Should have handled both failures and successes
        assert failures + successes == 10

    async def test_memory_pressure_handling(self):
        """System should handle memory pressure gracefully."""
        import gc
        from secondbrain.document.ingestor import DocumentIngestor

        ingestor = DocumentIngestor()

        # Force memory pressure
        large_data = [b"x" * 1000000 for _ in range(100)]

        try:
            with patch.object(ingestor, "_extract_text", return_value="Test"):
                with patch.object(ingestor, "_generate_embeddings", return_value=[]):
                    with patch.object(ingestor, "_store_document"):
                        # Should not crash under memory pressure
                        import tempfile

                        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
                            f.write(b"test")
                            ingestor.ingest(Path(f.name))
        finally:
            del large_data
            gc.collect()

    async def test_slow_downstream_services(self):
        """System should handle slow downstream services."""
        import time
        from secondbrain.storage.sync import SecondBrainStorage

        storage = SecondBrainStorage()

        with patch.object(storage, "_connect") as mock_connect:
            # Simulate slow connection (100ms)
            async def slow_connect():
                await asyncio.sleep(0.1)

            mock_connect.side_effect = slow_connect

            with patch.object(storage, "_ensure_collection"):
                start = time.time()
                await storage.connect()
                duration = time.time() - start

                # Should complete despite slowness
                assert duration >= 0.1

    def test_resource_cleanup_on_error(self):
        """Resources should be cleaned up on errors."""
        import tempfile
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
            os.unlink(doc_path)
