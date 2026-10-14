"""Async variant tests for the SQLite ConversationStorage.

Covers the ``*_async`` twins added for async session persistence:
- round-trip equivalence with the sync API (save -> load -> history),
- concurrent async access via ``asyncio.gather``,
- guarantee that the sync API surface is unchanged.
"""

from __future__ import annotations

import asyncio
import inspect
import threading

import pytest

from secondbrain.conversation.storage_sqlite import ConversationStorage

ASYNC_STORAGE_METHODS = (
    "create_session_async",
    "save_message_async",
    "update_messages_async",
    "get_history_async",
    "session_exists_async",
    "delete_session_async",
    "list_sessions_async",
    "close_async",
)

SYNC_STORAGE_METHODS = (
    "create_session",
    "save_message",
    "update_messages",
    "get_history",
    "session_exists",
    "delete_session",
    "list_sessions",
    "close",
)


@pytest.fixture
def storage(tmp_path):
    """Create a ConversationStorage backed by a temp-file SQLite database."""
    db_path = str(tmp_path / "conversations.db")
    s = ConversationStorage(db_path=db_path)
    yield s
    s.close()


def _without_timestamps(history):
    """Strip timestamps so sync/async histories compare equal."""
    return [{"role": m["role"], "content": m["content"]} for m in history]


class TestAsyncEquivalence:
    """Async twins must behave identically to their sync counterparts."""

    async def test_save_and_history_round_trip_matches_sync(self, storage):
        """save_message_async -> get_history_async equals the sync flow."""
        storage.create_session("sync-s")
        storage.save_message("sync-s", "user", "Hello")
        storage.save_message("sync-s", "assistant", "Hi!")

        await storage.create_session_async("async-s")
        await storage.save_message_async("async-s", "user", "Hello")
        await storage.save_message_async("async-s", "assistant", "Hi!")

        sync_history = _without_timestamps(storage.get_history("sync-s"))
        async_history = _without_timestamps(await storage.get_history_async("async-s"))
        assert async_history == sync_history

    async def test_get_history_async_limit_matches_sync(self, storage):
        """get_history_async applies the most-recent-N limit like the sync API."""
        await storage.create_session_async("s")
        for i in range(4):
            await storage.save_message_async("s", "user", f"m{i}")

        limited = await storage.get_history_async("s", limit=2)
        assert [m["content"] for m in limited] == ["m2", "m3"]
        assert await storage.get_history_async("missing") == []

    async def test_update_messages_async_matches_sync(self, storage):
        """update_messages_async replaces the message array like the sync API."""
        await storage.create_session_async("s")
        await storage.save_message_async("s", "user", "old")

        await storage.update_messages_async(
            "s",
            [
                {
                    "role": "user",
                    "content": "new-a",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
                {
                    "role": "assistant",
                    "content": "new-b",
                    "timestamp": "2024-01-01T00:00:01+00:00",
                },
            ],
        )

        history = await storage.get_history_async("s")
        assert [m["content"] for m in history] == ["new-a", "new-b"]
        assert history[0]["timestamp"] == "2024-01-01T00:00:00+00:00"

    async def test_session_exists_and_delete_async_match_sync(self, storage):
        """session_exists_async / delete_session_async mirror the sync results."""
        assert await storage.session_exists_async("s") is False
        await storage.create_session_async("s")
        await storage.save_message_async("s", "user", "a")
        assert await storage.session_exists_async("s") is True

        assert await storage.delete_session_async("s") is True
        assert await storage.session_exists_async("s") is False
        assert await storage.get_history_async("s") == []
        assert await storage.delete_session_async("missing") is False

    async def test_list_sessions_async_matches_sync(self, storage):
        """list_sessions_async reports the same metadata as the sync API."""
        await storage.create_session_async("s1")
        await storage.save_message_async("s1", "user", "a")
        await storage.save_message_async("s1", "user", "b")
        await storage.create_session_async("s2")

        sessions = {s["session_id"]: s for s in await storage.list_sessions_async()}
        assert sessions["s1"]["message_count"] == 2
        assert sessions["s1"]["created_at"]
        assert sessions["s2"]["message_count"] == 0
        assert len(await storage.list_sessions_async(limit=1)) == 1


class TestAsyncInterop:
    """Async and sync APIs interoperate on the same database."""

    async def test_async_write_visible_to_sync_read(self, storage):
        """Messages saved through the async API are read back via the sync API."""
        await storage.create_session_async("s")
        await storage.save_message_async("s", "user", "via-async")

        sync_history = storage.get_history("s")
        assert [m["content"] for m in sync_history] == ["via-async"]

        storage.save_message("s", "assistant", "via-sync")
        async_history = await storage.get_history_async("s")
        assert [m["content"] for m in async_history] == ["via-async", "via-sync"]

    async def test_sync_write_visible_to_async_read(self, storage):
        """Messages saved through the sync API are read back via the async API."""
        storage.create_session("s")
        storage.save_message("s", "user", "via-sync")

        async_history = await storage.get_history_async("s")
        assert [m["content"] for m in async_history] == ["via-sync"]

    async def test_async_ops_run_off_event_loop_thread(self, storage, monkeypatch):
        """save_message_async executes the blocking call on a worker thread."""
        loop_thread = threading.get_ident()
        seen_threads = []
        original = storage.save_message

        def spy(session_id, role, content):
            seen_threads.append(threading.get_ident())
            return original(session_id, role, content)

        monkeypatch.setattr(storage, "save_message", spy)
        await storage.create_session_async("s")
        await storage.save_message_async("s", "user", "hello")

        assert seen_threads == [t for t in seen_threads if t != loop_thread]
        assert seen_threads, "spy was never invoked"


class TestConcurrentAsyncAccess:
    """Concurrent async operations must be safe on the shared connection."""

    async def test_concurrent_saves_serialize_positions(self, storage):
        """Gathered saves produce one message per position, none lost."""
        await storage.create_session_async("s")
        count = 20
        await asyncio.gather(
            *(storage.save_message_async("s", "user", f"m{i}") for i in range(count))
        )

        history = await storage.get_history_async("s")
        assert len(history) == count
        assert sorted(m["content"] for m in history) == sorted(
            f"m{i}" for i in range(count)
        )

        positions = [
            row["position"]
            for row in storage.conn.execute(
                "SELECT position FROM messages WHERE session_id = ? "
                "ORDER BY position ASC",
                ("s",),
            )
        ]
        assert positions == list(range(count))

    async def test_concurrent_reads_during_writes(self, storage):
        """Mixed concurrent reads and writes are all served without error."""
        await storage.create_session_async("s")
        writers = [storage.save_message_async("s", "user", f"w{i}") for i in range(10)]
        readers = [storage.get_history_async("s") for _ in range(5)]
        checkers = [storage.session_exists_async("s") for _ in range(5)]
        await asyncio.gather(*writers, *readers, *checkers)

        history = await storage.get_history_async("s")
        assert len({m["content"] for m in history}) == 10

    async def test_concurrent_first_touch_shares_one_connection(self, storage):
        """First concurrent access initializes exactly one shared connection."""
        await asyncio.gather(*(storage.create_session_async(f"s{i}") for i in range(8)))
        assert storage._conn is not None

        sessions = await storage.list_sessions_async()
        assert {s["session_id"] for s in sessions} == {f"s{i}" for i in range(8)}

    async def test_concurrent_saves_across_sessions(self, storage):
        """Concurrent writes to different sessions stay isolated."""
        for i in range(5):
            await storage.create_session_async(f"s{i}")
        await asyncio.gather(
            *(
                storage.save_message_async(f"s{i}", "user", f"msg-{i}-{j}")
                for i in range(5)
                for j in range(4)
            )
        )

        for i in range(5):
            history = await storage.get_history_async(f"s{i}")
            # Concurrent append order is nondeterministic; assert
            # completeness and isolation instead of ordering.
            assert sorted(m["content"] for m in history) == sorted(
                f"msg-{i}-{j}" for j in range(4)
            )


class TestSyncApiUnchanged:
    """The pre-existing sync surface must be intact."""

    def test_sync_methods_remain_plain_functions(self):
        """Every pre-existing sync method is still a plain function."""
        for name in SYNC_STORAGE_METHODS:
            method = getattr(ConversationStorage, name)
            assert not inspect.iscoroutinefunction(method), name

    def test_async_methods_are_coroutine_functions(self):
        """Every added async twin is a coroutine function."""
        for name in ASYNC_STORAGE_METHODS:
            method = getattr(ConversationStorage, name)
            assert inspect.iscoroutinefunction(method), name

    def test_sync_round_trip_unchanged(self, storage):
        """The documented sync flow behaves exactly as before."""
        assert storage.create_session("s") == "s"
        storage.save_message("s", "user", "Hello")
        storage.save_message("s", "assistant", "Hi!")
        history = storage.get_history("s")
        assert [m["content"] for m in history] == ["Hello", "Hi!"]
        assert [m["content"] for m in storage.get_history("s", limit=1)] == ["Hi!"]
        assert storage.session_exists("s") is True
        assert storage.delete_session("s") is True
        assert storage.session_exists("s") is False

    def test_write_while_db_lock_held_does_not_deadlock(self, storage):
        """Write methods may be called while the storage db lock is held.

        The lazy connection init runs under the same reentrant lock used by
        write methods, so the lock must be reentrant (a plain Lock would
        deadlock here).
        """
        done = threading.Event()

        def _write():
            with storage._db_lock:
                storage.create_session("reentrant")
            done.set()

        thread = threading.Thread(target=_write, daemon=True)
        thread.start()
        assert done.wait(timeout=10)
        assert storage.session_exists("reentrant")

    def test_conn_lazy_init_thread_safe(self, storage):
        """Concurrent threads sharing first touch get one connection."""
        barrier = threading.Barrier(8)
        conns = []

        def touch():
            barrier.wait()
            conns.append(id(storage.conn))

        threads = [threading.Thread(target=touch) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(conns) == 8
        assert len(set(conns)) == 1
