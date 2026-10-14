"""Async variant tests for ConversationSession (facade-level async API).

Covers ``ConversationSession.create_async`` / ``load_async`` /
``add_message_async`` / ``clear_history_async`` against a real SQLite
storage, verifying round-trip equivalence with the sync API, concurrent
async access, and that the sync surface is untouched.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from secondbrain.conversation.session import ConversationSession
from secondbrain.conversation.storage_sqlite import ConversationStorage

SESSION_ASYNC_METHODS = (
    "create_async",
    "load_async",
    "add_message_async",
    "clear_history_async",
)
SESSION_SYNC_METHODS = (
    "create",
    "load",
    "add_message",
    "get_history",
    "get_context_messages",
    "trim_context",
    "clear_history",
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


class TestSessionAsyncRoundTrip:
    """Async session lifecycle must match the sync lifecycle."""

    async def test_create_async_then_add_and_history_matches_sync(
        self, storage, tmp_path
    ):
        """create_async -> add_message_async -> history equals the sync flow."""
        sync_session = ConversationSession.create("sync-s", storage)
        sync_session.add_message("user", "Hello")
        sync_session.add_message("assistant", "Hi!")

        async_session = await ConversationSession.create_async("async-s", storage)
        await async_session.add_message_async("user", "Hello")
        await async_session.add_message_async("assistant", "Hi!")

        assert _without_timestamps(async_session.get_history()) == _without_timestamps(
            sync_session.get_history()
        )
        # The async path persisted to the same SQLite tables.
        assert [m["content"] for m in storage.get_history("async-s")] == [
            "Hello",
            "Hi!",
        ]

    async def test_load_async_returns_session_with_history(self, storage):
        """load_async restores the persisted history like load."""
        session = await ConversationSession.create_async("s", storage)
        await session.add_message_async("user", "q1")
        await session.add_message_async("assistant", "a1")

        loaded = await ConversationSession.load_async("s", storage)
        assert loaded is not None
        assert loaded.session_id == "s"
        assert _without_timestamps(loaded.get_history()) == [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        # Equivalence vs sync load on a second identical session.
        session2 = await ConversationSession.create_async("s2", storage)
        await session2.add_message_async("user", "q1")
        await session2.add_message_async("assistant", "a1")
        sync_loaded = ConversationSession.load("s2", storage)
        assert _without_timestamps(loaded.get_history()) == _without_timestamps(
            sync_loaded.get_history()
        )

    async def test_load_async_missing_session_returns_none(self, storage):
        """load_async returns None for an unknown session, like load."""
        assert await ConversationSession.load_async("nope", storage) is None
        assert ConversationSession.load("nope", storage) is None

    async def test_create_async_generates_uuid_when_no_id(self, storage):
        """create_async auto-generates a UUID session id like create."""
        session = await ConversationSession.create_async(storage=storage)
        assert session.session_id
        assert len(session.session_id) == 36
        assert storage.session_exists(session.session_id)

    async def test_create_async_without_storage_raises(self, storage):
        """create_async requires storage, like create."""
        with pytest.raises(ValueError, match="storage must be provided"):
            await ConversationSession.create_async()

    async def test_clear_history_async_persists(self, storage):
        """clear_history_async empties memory and storage like clear_history."""
        session = await ConversationSession.create_async("s", storage)
        await session.add_message_async("user", "a")
        await session.add_message_async("user", "b")
        assert session.is_empty is False

        await session.clear_history_async()
        assert session.is_empty is True
        assert session.message_count == 0
        assert await storage.get_history_async("s") == []

    async def test_context_window_applies_after_async_adds(self, storage):
        """add_message_async trims in-memory history to the context window."""
        session = await ConversationSession.create_async("s", storage, context_window=3)
        for i in range(6):
            await session.add_message_async("user", f"m{i}")

        assert [m["content"] for m in session.get_history()] == ["m3", "m4", "m5"]
        # Persisted history stays intact beyond the window.
        assert len(await storage.get_history_async("s")) == 6
        assert [m["content"] for m in session.get_context_messages()] == [
            "m3",
            "m4",
            "m5",
        ]


class TestSessionAsyncInterop:
    """Async facade operations interoperate with sync ones."""

    async def test_sync_and_async_views_of_same_session_agree(self, storage):
        """Async-written session read back through the sync facade agrees."""
        async_session = await ConversationSession.create_async("s", storage)
        await async_session.add_message_async("user", "q")
        await async_session.add_message_async("assistant", "a")

        sync_view = ConversationSession.load("s", storage)
        assert _without_timestamps(sync_view.get_history()) == _without_timestamps(
            async_session.get_history()
        )

    async def test_add_message_async_delegates_to_storage_async(self, storage):
        """add_message_async persists via save_message_async, not the sync path."""
        calls = []
        original = storage.save_message_async

        async def spy(session_id, role, content):
            calls.append((session_id, role, content))
            await original(session_id, role, content)

        storage.save_message_async = spy  # type: ignore[method-assign]
        session = await ConversationSession.create_async("s", storage)
        await session.add_message_async("user", "hello")

        assert calls == [("s", "user", "hello")]


class TestSessionConcurrentAsync:
    """Concurrent async facade operations are safe."""

    async def test_concurrent_add_message_async_preserves_all_messages(self, storage):
        """Gathered add_message_async persists every message to storage."""
        session = await ConversationSession.create_async("s", storage)
        count = 15
        await asyncio.gather(
            *(session.add_message_async("user", f"m{i}") for i in range(count))
        )

        # Every message persisted (storage history is complete).
        persisted = await storage.get_history_async("s")
        assert sorted(m["content"] for m in persisted) == sorted(
            f"m{i}" for i in range(count)
        )
        # In-memory buffer trims to the context window.
        assert len(session.get_history()) == 5

    async def test_concurrent_create_and_load(self, storage):
        """Concurrent create_async + load_async of distinct sessions works."""
        created = await asyncio.gather(
            *(ConversationSession.create_async(f"s{i}", storage) for i in range(6))
        )
        loaded = await asyncio.gather(
            *(ConversationSession.load_async(f"s{i}", storage) for i in range(6))
        )
        assert [s.session_id for s in created] == [f"s{i}" for i in range(6)]
        assert all(s is not None for s in loaded)


class TestSessionSyncApiUnchanged:
    """The pre-existing sync surface must be intact."""

    def test_sync_methods_remain_plain_functions(self):
        """Every pre-existing sync session method is still a plain function."""
        for name in SESSION_SYNC_METHODS:
            method = getattr(ConversationSession, name)
            assert not inspect.iscoroutinefunction(method), name

    def test_async_methods_are_coroutine_functions(self):
        """Every added async twin is a coroutine function."""
        for name in SESSION_ASYNC_METHODS:
            method = getattr(ConversationSession, name)
            assert inspect.iscoroutinefunction(method), name

    def test_sync_round_trip_unchanged(self, storage):
        """The documented sync session flow behaves exactly as before."""
        session = ConversationSession.create("s", storage)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        assert [m["content"] for m in session.get_history()] == ["Hello", "Hi!"]
        loaded = ConversationSession.load("s", storage)
        assert loaded is not None
        assert [m["content"] for m in loaded.get_history()] == ["Hello", "Hi!"]
        session.clear_history()
        assert session.is_empty is True
        assert storage.get_history("s") == []

    def test_mock_based_sync_flow_still_works(self):
        """Session works with a spec'd MagicMock storage (regression guard)."""
        storage = MagicMock(spec=ConversationStorage)
        storage.get_history.return_value = []
        storage.create_session.return_value = "test-session"
        session = ConversationSession.create("test-session", storage)
        session.add_message("user", "hi")
        storage.save_message.assert_called_once_with("test-session", "user", "hi")
        assert session.get_history() == [{"role": "user", "content": "hi"}]
