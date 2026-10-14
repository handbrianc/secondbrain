"""Concurrent search tests against REAL shared components.

The former versions of these tests spun threads around local closures (own
locks, own result lists) — races that could never fail. Every test here drives
a real ``src/secondbrain`` component concurrently and asserts on its
post-state:

- :class:`secondbrain.storage.mock.MockVectorStorage` — real similarity search
  over a shared chunk dict, exercised while writers mutate it concurrently;
- :class:`secondbrain.utils.circuit_breaker.CircuitBreaker` — lock-protected
  state machine (these tests already targeted real code and are preserved).

Runtime is kept bounded: few workers, small vector dimensions, no sleeps.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from secondbrain.storage.mock import MockVectorStorage
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


def _chunk(chunk_id: str, embedding: list[float]) -> dict:
    """Minimal chunk dict accepted by MockVectorStorage.store."""
    return {
        "chunk_id": chunk_id,
        "chunk_text": f"text for {chunk_id}",
        "embedding": embedding,
        "source_file": f"{chunk_id}.md",
        "page_number": 1,
    }


def _seeded_storage(workers: int = 4, per_worker: int = 10) -> MockVectorStorage:
    """Storage with per-worker vector groups plus one decoy far away.

    Chunk ids are ``t{worker}-c{i}`` so tests can delete by per-worker prefix.
    """
    storage = MockVectorStorage()
    storage.initialize()
    for worker in range(workers):
        storage.store_batch(
            [_chunk(f"t{worker}-c{i}", [0.99, 0.1, 0.0]) for i in range(per_worker)]
        )
    storage.store(_chunk("decoy", [0.0, 0.0, 1.0]))
    return storage


_QUERY = [1.0, 0.0, 0.0]


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")  # Isolate concurrent tests on same worker
class TestConcurrentSearch:
    """Concurrent searches on the real MockVectorStorage."""

    def test_concurrent_queries_return_identical_results(self):
        """20 threads running the same query get the same deterministic hits."""
        storage = _seeded_storage()
        barrier = threading.Barrier(20)
        results: list[list[str]] = []
        results_lock = threading.Lock()

        def search() -> None:
            barrier.wait()
            hits = storage.search(_QUERY, top_k=5)
            ids = [hit["chunk_id"] for hit in hits]
            with results_lock:
                results.append(ids)

        threads = [threading.Thread(target=search) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 20
        # Same query, same data -> identical result ranking for every thread.
        assert all(ids == results[0] for ids in results)
        assert "decoy" not in results[0]
        assert len(results[0]) == 5

    def test_search_results_sorted_by_similarity(self):
        """Concurrent searches always return similarity-sorted results."""
        storage = _seeded_storage()

        def search(_worker_id: int) -> list[dict]:
            return storage.search(_QUERY, top_k=10)

        with ThreadPoolExecutor(max_workers=8) as executor:
            batches = [
                future.result()
                for future in [executor.submit(search, w) for w in range(40)]
            ]

        for hits in batches:
            scores = [hit["similarity"] for hit in hits]
            assert scores == sorted(scores, reverse=True)
            assert len(hits) == 10

    def test_search_while_ingesting_never_loses_queries(self):
        """Searches succeed (and stay well-formed) while chunks stream in."""

        def write_batch(writer_id: int) -> None:
            for i in range(10):
                storage.store(_chunk(f"new-{writer_id}-{i}", [0.98, 0.15, 0.0]))

        def search(_worker_id: int) -> list[dict]:
            return storage.search(_QUERY, top_k=5)

        storage = _seeded_storage()
        with ThreadPoolExecutor(max_workers=8) as executor:
            writer_futures = [
                executor.submit(write_batch, writer) for writer in range(2)
            ]
            reader_futures = [executor.submit(search, worker) for worker in range(30)]
            for future in writer_futures + reader_futures:
                future.result()

        # Every query got a full, well-formed result page.
        for future in reader_futures:
            hits = future.result()
            assert len(hits) == 5
            for hit in hits:
                assert hit["chunk_id"]
                assert -1.0 <= hit["similarity"] <= 1.0

        # All 20 concurrent writes landed on top of the 41 seeded chunks.
        assert storage.count() == 41 + 20

    def test_concurrent_deletes_leave_consistent_counts(self):
        """Disjoint concurrent deletions remove exactly their own chunks."""
        storage = _seeded_storage(workers=4, per_worker=10)

        def delete_slice(worker_id: int) -> int:
            return storage.delete_by_prefix(f"t{worker_id}-")

        with ThreadPoolExecutor(max_workers=4) as executor:
            deleted = [
                future.result()
                for future in [
                    executor.submit(delete_slice, worker) for worker in range(4)
                ]
            ]

        assert deleted == [10, 10, 10, 10]
        assert storage.count() == 1  # only the decoy remains


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")
class TestAsyncSearchOperations:
    """Async twins of the storage API driven concurrently."""

    def test_concurrent_async_validation(self):
        """Concurrent validate_connection_async calls all report healthy."""

        async def run() -> None:
            storage = _seeded_storage()
            results = await asyncio.gather(
                *[storage.validate_connection_async() for _ in range(10)]
            )
            assert results == [True] * 10

        asyncio.run(run())

    def test_async_search_batch_consistency(self):
        """A single asyncio batch of searches matches the serial result."""

        async def run() -> None:
            storage = _seeded_storage()
            expected = [hit["chunk_id"] for hit in storage.search(_QUERY, top_k=5)]
            results = await asyncio.gather(
                *[asyncio.to_thread(storage.search, _QUERY, 5) for _ in range(10)]
            )
            for hits in results:
                assert [hit["chunk_id"] for hit in hits] == expected

        asyncio.run(run())


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")
class TestSearchWithCircuitBreaker:
    """Circuit-breaker gating of search under concurrency (real component)."""

    def test_search_blocked_when_circuit_open(self):
        """A tripped breaker blocks the search call and counts the failure."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=2),
            service_name="search",
        )

        for _ in range(2):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        with pytest.raises(Exception) as exc_info:
            cb.call(lambda: True)  # any call while open must fail fast

        assert "Circuit breaker is open" in str(exc_info.value)

    def test_search_allowed_when_circuit_closed(self):
        """A healthy breaker admits searches and records successes."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=2),
            service_name="search",
        )

        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

        result = cb.call(lambda: True)

        assert result is True
        assert cb.success_count == 0  # CLOSED successes reset the counter

    def test_concurrent_search_during_circuit_recovery(self, fake_clock):
        """Successes during HALF_OPEN close the circuit (real transitions)."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
            success_threshold=2,
        )
        cb = CircuitBreaker(config, service_name="search")

        for _ in range(3):
            cb.record_failure()

        fake_clock.advance(0.15)

        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED
