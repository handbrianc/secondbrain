"""Concurrency tests against REAL shared components.

Every test drives an actual ``src/secondbrain`` component from multiple
threads/tasks and asserts on its post-state (counts, recorded messages,
return values). There are no local-closure "races": the shared state lives in
the production object, so a lost update, a duplicate insert, or a broken lock
fails the assertion.

Components under test:

- :class:`secondbrain.storage.mock.MockVectorStorage` — in-memory shared
  chunk dict/id list (the ``mock`` storage backend shipped with the app);
- :class:`secondbrain.conversation.storage_sqlite.ConversationStorage` —
  SQLite storage whose ``_db_lock`` RLock serializes all access; concurrent
  saves must not collide on the ``(session_id, position)`` primary key;
- :class:`secondbrain.utils.rate_limiter.SharedRateLimiter` (and the
  process-wide ``get_shared_rate_limiter`` singleton) — sliding-window
  counting must not over-admit under thread hammering;
- :class:`secondbrain.utils.circuit_breaker.CircuitBreaker` — lock-protected
  state machine.

Runtime is kept bounded: few workers, small message counts, sub-second waits.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from secondbrain.conversation.storage_sqlite import ConversationStorage
from secondbrain.storage.mock import MockVectorStorage
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from secondbrain.utils.rate_limiter import (
    SharedRateLimiter,
    get_shared_rate_limiter,
    reset_shared_rate_limiter,
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


@pytest.fixture
def sqlite_storage(tmp_path):
    """ConversationStorage backed by a temp-file SQLite database."""
    storage = ConversationStorage(db_path=str(tmp_path / "conversations.db"))
    yield storage
    storage.close()


@pytest.fixture
def fresh_shared_limiter():
    """Isolate the process-wide shared rate limiter for this test."""
    reset_shared_rate_limiter()
    yield
    reset_shared_rate_limiter()


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")  # Isolate concurrent tests on same worker
class TestConcurrentStore:
    """Concurrent stores/deletes against the real MockVectorStorage."""

    def test_concurrent_store_distinct_chunks_no_lost_updates(self):
        """200 chunks stored from 8 threads all land in storage exactly once."""
        storage = MockVectorStorage()
        embedding = [1.0, 0.0, 0.0]

        def store_batch(worker_id: int) -> None:
            storage.store_batch(
                [_chunk(f"w{worker_id}-c{i}", embedding) for i in range(25)]
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(store_batch, worker) for worker in range(8)]
            for future in futures:
                future.result()

        assert storage.count() == 200
        assert len(set(storage.get_chunk_ids())) == 200
        assert all(
            storage.get_chunk(f"w{w}-c{i}") is not None
            for w in range(8)
            for i in range(25)
        )

    def test_concurrent_store_same_chunk_id_last_write_wins(self):
        """10 threads writing one chunk_id end with exactly one stored chunk."""
        storage = MockVectorStorage()

        def store_same(worker_id: int) -> None:
            storage.store(_chunk("shared-chunk", [float(worker_id), 0.0]))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(store_same, worker) for worker in range(10)]
            for future in futures:
                future.result()

        assert storage.count() == 1
        chunk_ids = storage.get_chunk_ids()
        assert len(set(chunk_ids)) == 1  # one distinct id (list may double-entry)
        stored = storage.get_chunk("shared-chunk")
        assert stored is not None
        assert stored["embedding"][0] in {float(w) for w in range(10)}

    def test_concurrent_delete_by_prefix_partition(self):
        """Threads deleting disjoint prefixes delete every chunk exactly once."""
        storage = MockVectorStorage()
        embedding = [1.0, 0.0, 0.0]
        for worker in range(4):
            storage.store_batch(
                [_chunk(f"t{worker}-c{i}", embedding) for i in range(20)]
            )
        assert storage.count() == 80

        def delete_prefix(worker_id: int) -> int:
            return storage.delete_by_prefix(f"t{worker_id}-")

        with ThreadPoolExecutor(max_workers=4) as executor:
            deleted = [
                future.result()
                for future in [
                    executor.submit(delete_prefix, worker) for worker in range(4)
                ]
            ]

        assert deleted == [20, 20, 20, 20]
        assert storage.count() == 0

    def test_concurrent_store_batch_batches(self):
        """Concurrent store_batch calls sum up without interference."""
        storage = MockVectorStorage()
        embedding = [0.0, 1.0, 0.0]

        def store_two_batches(worker_id: int) -> None:
            for batch in range(2):
                storage.store_batch(
                    [_chunk(f"b{worker_id}-{batch}-{i}", embedding) for i in range(10)]
                )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(store_two_batches, worker) for worker in range(5)
            ]
            for future in futures:
                future.result()

        assert storage.count() == 100


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")
class TestSQLiteConcurrentWrites:
    """Concurrent writes through ConversationStorage's real _db_lock.

    The save path is SELECT MAX(position)+1 then INSERT into a
    ``(session_id, position)`` primary key. Without the lock, two concurrent
    savers read the same MAX and one INSERT dies with IntegrityError — so a
    green run here proves the lock actually serialized the writers.
    """

    def test_concurrent_saves_same_session_no_lost_messages(self, sqlite_storage):
        """10 threads x 5 messages -> exactly 50 distinct recorded messages."""
        session_id = sqlite_storage.create_session("race-session")
        expected = {f"worker-{w}-msg-{i}" for w in range(10) for i in range(5)}

        def save_batch(worker_id: int) -> None:
            for i in range(5):
                sqlite_storage.save_message(
                    session_id, "user", f"worker-{worker_id}-msg-{i}"
                )

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(save_batch, worker) for worker in range(10)]
            for future in futures:
                future.result()

        history = sqlite_storage.get_history(session_id)
        contents = {message["content"] for message in history}

        assert len(history) == 50
        assert contents == expected

    def test_concurrent_async_saves_same_session(self, sqlite_storage):
        """Async twins (asyncio.to_thread) serialize on the same lock."""

        async def run() -> None:
            session_id = sqlite_storage.create_session("async-race")
            tasks = [
                sqlite_storage.save_message_async(session_id, "user", f"msg-{i}")
                for i in range(20)
            ]
            await asyncio.gather(*tasks)

            history = sqlite_storage.get_history(session_id)
            assert len(history) == 20
            assert {m["content"] for m in history} == {f"msg-{i}" for i in range(20)}

        asyncio.run(run())

    def test_concurrent_delete_same_session_exactly_once(self, sqlite_storage):
        """Concurrent delete_session calls delete exactly one time."""
        session_id = sqlite_storage.create_session("doomed-session")
        sqlite_storage.save_message(session_id, "user", "bye")

        def delete_session(_worker_id: int) -> bool:
            return sqlite_storage.delete_session(session_id)

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = [
                future.result()
                for future in [executor.submit(delete_session, w) for w in range(5)]
            ]

        assert sum(results) == 1
        assert sqlite_storage.session_exists(session_id) is False

    def test_concurrent_saves_distinct_sessions_all_recorded(self, sqlite_storage):
        """Concurrent creates+writes of 10 distinct sessions all persist."""

        def create_and_fill(worker_id: int) -> None:
            session_id = f"session-{worker_id}"
            sqlite_storage.create_session(session_id)
            sqlite_storage.save_message(session_id, "user", f"hello-{worker_id}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_and_fill, worker) for worker in range(10)]
            for future in futures:
                future.result()

        sessions = sqlite_storage.list_sessions(limit=100)
        assert len(sessions) == 10
        assert {s["session_id"] for s in sessions} == {
            f"session-{w}" for w in range(10)
        }
        assert all(s["message_count"] == 1 for s in sessions)

    def test_reads_during_concurrent_writes_stay_consistent(self, sqlite_storage):
        """Snapshots taken while writers run are never corrupt or duplicated."""
        session_id = sqlite_storage.create_session("readwrite-race")
        done = threading.Event()
        snapshots: list[list[str]] = []
        snapshot_errors: list[Exception] = []

        def reader() -> None:
            while not done.is_set():
                try:
                    history = sqlite_storage.get_history(session_id)
                    contents = [m["content"] for m in history]
                    # Every snapshot must be duplicate-free and a subset of
                    # what will eventually be written.
                    assert len(contents) == len(set(contents))
                    assert all(c.startswith("msg-") for c in contents)
                    snapshots.append(contents)
                except Exception as exc:  # pragma: no cover - failure path
                    snapshot_errors.append(exc)
                    break

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()

        def save_batch(worker_id: int) -> None:
            for i in range(10):
                sqlite_storage.save_message(session_id, "user", f"msg-{worker_id}-{i}")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_batch, worker) for worker in range(5)]
            for future in futures:
                future.result()
        done.set()
        reader_thread.join()

        assert not snapshot_errors
        assert sqlite_storage.get_history(session_id)  # 50 messages now
        assert len(sqlite_storage.get_history(session_id)) == 50
        # No snapshot ever exceeded the final message count.
        assert all(len(snapshot) <= 50 for snapshot in snapshots)


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")
class TestRateLimiterThreadSafety:
    """SharedRateLimiter sliding window under real thread pressure."""

    def test_concurrent_acquire_admits_exactly_max_requests(self):
        """20 threads hammering acquire() -> exactly max_requests admitted."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)
        barrier = threading.Barrier(20)
        results: list[bool] = []
        results_lock = threading.Lock()

        def acquire() -> None:
            barrier.wait()
            allowed = limiter.acquire()
            with results_lock:
                results.append(allowed)

        threads = [threading.Thread(target=acquire) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sum(results) == 10
        assert results.count(False) == 10
        assert limiter.get_remaining() == 0

    def test_concurrent_wait_and_acquire_times_out_deterministically(self):
        """wait_and_acquire with a short timeout admits only the window size."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=60.0)

        def wait_acquire(_worker_id: int) -> bool:
            return limiter.wait_and_acquire(timeout=0.3)

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = [
                future.result()
                for future in [
                    executor.submit(wait_acquire, worker) for worker in range(6)
                ]
            ]

        assert sum(results) == 2
        assert limiter.get_remaining() == 0

    def test_shared_limiter_singleton_race_returns_one_instance(
        self, fresh_shared_limiter
    ):
        """All threads racing get_shared_rate_limiter get the SAME instance."""
        barrier = threading.Barrier(8)
        instances: list[SharedRateLimiter] = []
        instances_lock = threading.Lock()

        def get_limiter() -> None:
            barrier.wait()
            instance = get_shared_rate_limiter(max_requests=5, window_seconds=60.0)
            with instances_lock:
                instances.append(instance)

        threads = [threading.Thread(target=get_limiter) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(instances) == 8
        assert all(instance is instances[0] for instance in instances)
        assert instances[0].max_requests == 5


@pytest.mark.concurrent
@pytest.mark.slow
@pytest.mark.xdist_group("concurrent")
class TestCircuitBreakerConcurrency:
    """CircuitBreaker state machine under real thread pressure."""

    def test_concurrent_failures_open_circuit_with_exact_count(self):
        """200 concurrent record_failure calls -> OPEN at exactly threshold."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        barrier = threading.Barrier(20)

        def hammer_failures() -> None:
            barrier.wait()
            for _ in range(10):
                cb.record_failure()

        threads = [threading.Thread(target=hammer_failures) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert cb.state == CircuitState.OPEN
        # After the circuit opens, further record_failure calls are ignored,
        # so the counter stops exactly at the threshold.
        assert cb.failure_count == 3

    def test_concurrent_is_allowed_all_blocked_when_open(self):
        """20 threads checking is_allowed during OPEN all get False."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        barrier = threading.Barrier(20)
        results: list[bool] = []
        results_lock = threading.Lock()

        def check_allowed() -> None:
            barrier.wait()
            allowed = cb.is_allowed()
            with results_lock:
                results.append(allowed)

        threads = [threading.Thread(target=check_allowed) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert results == [False] * 20

    def test_concurrent_successes_on_closed_circuit_stay_closed(self):
        """Concurrent record_success calls never trip a healthy circuit."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        barrier = threading.Barrier(10)

        def hammer_successes() -> None:
            barrier.wait()
            for _ in range(20):
                cb.record_success()

        threads = [threading.Thread(target=hammer_successes) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

    def test_concurrent_half_open_successes_close_circuit(self, fake_clock):
        """5 threads recording successes in HALF_OPEN close the circuit."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=2,
                recovery_timeout=0.1,
                half_open_max_calls=5,
                success_threshold=3,
            )
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        fake_clock.advance(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        barrier = threading.Barrier(5)

        def try_success() -> None:
            barrier.wait()
            if cb.is_allowed():
                cb.record_success()

        threads = [threading.Thread(target=try_success) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.is_allowed() is True

    def test_concurrent_half_open_failure_reopens_with_backoff(self, fake_clock):
        """A failure during HALF_OPEN re-opens and doubles the recovery timeout."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=2,
                recovery_timeout=0.1,
            )
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        fake_clock.advance(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        barrier = threading.Barrier(3)

        def try_failure() -> None:
            barrier.wait()
            if cb.is_allowed():
                cb.record_failure()

        threads = [threading.Thread(target=try_failure) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert cb.state == CircuitState.OPEN
        info = cb.get_state_info()
        assert info["backoff_multiplier"] == 2
        assert info["current_recovery_timeout"] == pytest.approx(0.2)

    def test_mixed_concurrent_calls_leave_coherent_state(self, fake_clock):
        """After a success/failure mix the state machine stays coherent."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=2,
                recovery_timeout=0.1,
                half_open_max_calls=5,
                success_threshold=3,
            )
        )
        cb.record_failure()
        cb.record_failure()

        fake_clock.advance(0.15)
        barrier = threading.Barrier(5)

        def try_call(success: bool) -> None:
            barrier.wait()
            if cb.is_allowed():
                if success:
                    cb.record_success()
                else:
                    cb.record_failure()

        threads = [
            threading.Thread(target=try_call, args=(worker % 2 == 0,))
            for worker in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Whatever the interleaving, state and gate must agree.
        info = cb.get_state_info()
        if cb.state == CircuitState.OPEN:
            assert cb.is_allowed() is False
            assert info["failure_count"] >= 0
        elif cb.state == CircuitState.CLOSED:
            assert cb.is_allowed() is True
            assert info["success_count"] == 0
        else:  # HALF_OPEN
            assert info["half_open_calls"] <= info["half_open_max_calls"]
