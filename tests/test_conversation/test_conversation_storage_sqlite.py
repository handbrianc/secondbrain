"""Unit tests for the SQLite ConversationStorage implementation."""

from __future__ import annotations

import sqlite3

import pytest

from secondbrain.conversation.storage_sqlite import ConversationStorage


@pytest.fixture
def storage(tmp_path):
    """Create a ConversationStorage backed by a temp-file SQLite database."""
    db_path = str(tmp_path / "conversations.db")
    s = ConversationStorage(db_path=db_path)
    yield s
    s.close()


class TestCreateSession:
    """Tests for create_session."""

    def test_create_returns_id(self, storage):
        """create_session returns the session id."""
        assert storage.create_session("session-1") == "session-1"

    def test_creates_row(self, storage):
        """create_session inserts a sessions row."""
        storage.create_session("session-1")
        row = storage.conn.execute(
            "SELECT session_id, created_at, updated_at FROM sessions "
            "WHERE session_id = ?",
            ("session-1",),
        ).fetchone()
        assert row is not None
        assert row["session_id"] == "session-1"
        assert row["created_at"]
        assert row["updated_at"]


class TestSaveMessage:
    """Tests for save_message ordering and position."""

    def test_appends_in_order(self, storage):
        """save_message persists messages with increasing position."""
        storage.create_session("s")
        storage.save_message("s", "user", "Hello")
        storage.save_message("s", "assistant", "Hi!")
        storage.save_message("s", "user", "Again")

        history = storage.get_history("s")
        assert [m["role"] for m in history] == ["user", "assistant", "user"]
        assert [m["content"] for m in history] == ["Hello", "Hi!", "Again"]
        for m in history:
            assert "timestamp" in m

    def test_position_values_are_sequential(self, storage):
        """save_message assigns sequential position values starting at 0."""
        storage.create_session("s")
        for i in range(3):
            storage.save_message("s", "user", f"msg-{i}")
        positions = [
            r["position"]
            for r in storage.conn.execute(
                "SELECT position FROM messages WHERE session_id = ? "
                "ORDER BY position ASC",
                ("s",),
            )
        ]
        assert positions == [0, 1, 2]


class TestGetHistory:
    """Tests for get_history."""

    def test_missing_session_returns_empty(self, storage):
        """get_history on a missing session returns []."""
        assert storage.get_history("does-not-exist") == []

    def test_returns_all_when_no_limit(self, storage):
        """get_history returns all messages in order with no limit."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.save_message("s", "user", "b")
        storage.save_message("s", "user", "c")
        assert [m["content"] for m in storage.get_history("s")] == ["a", "b", "c"]

    def test_limit_returns_most_recent_n(self, storage):
        """get_history with limit returns the last N messages in order."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.save_message("s", "user", "b")
        storage.save_message("s", "user", "c")
        history = storage.get_history("s", limit=2)
        assert [m["content"] for m in history] == ["b", "c"]
        for m in history:
            assert "timestamp" in m

    def test_limit_of_one_returns_last_message(self, storage):
        """get_history with limit=1 returns only the last message."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.save_message("s", "user", "b")
        history = storage.get_history("s", limit=1)
        assert [m["content"] for m in history] == ["b"]

    def test_non_positive_limit_returns_all(self, storage):
        """get_history with limit<=0 returns all messages."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.save_message("s", "user", "b")
        assert [m["content"] for m in storage.get_history("s", limit=0)] == ["a", "b"]


class TestUpdateMessages:
    """Tests for update_messages whole-array replace."""

    def test_replaces_all_messages(self, storage):
        """update_messages replaces the entire message array."""
        storage.create_session("s")
        storage.save_message("s", "user", "old-a")
        storage.save_message("s", "user", "old-b")

        storage.update_messages(
            "s",
            [
                {"role": "user", "content": "new-a", "timestamp": "2024-01-01T00:00:00+00:00"},
                {"role": "assistant", "content": "new-b", "timestamp": "2024-01-01T00:00:01+00:00"},
            ],
        )

        history = storage.get_history("s")
        assert [m["content"] for m in history] == ["new-a", "new-b"]
        assert history[0]["timestamp"] == "2024-01-01T00:00:00+00:00"

    def test_replaces_with_empty_list(self, storage):
        """update_messages with an empty list clears all messages."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.update_messages("s", [])
        assert storage.get_history("s") == []


class TestSessionExists:
    """Tests for session_exists."""

    def test_true_after_create(self, storage):
        """session_exists is True after create_session."""
        storage.create_session("s")
        assert storage.session_exists("s") is True

    def test_false_for_missing(self, storage):
        """session_exists is False for a missing session."""
        assert storage.session_exists("nope") is False


class TestDeleteSession:
    """Tests for delete_session."""

    def test_delete_returns_true(self, storage):
        """delete_session returns True and removes the session."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        assert storage.delete_session("s") is True
        assert storage.session_exists("s") is False
        assert storage.get_history("s") == []

    def test_delete_missing_returns_false(self, storage):
        """delete_session on a missing session returns False."""
        assert storage.delete_session("nope") is False

    def test_delete_cascades_messages(self, storage):
        """Deleting a session removes its messages via cascade."""
        storage.create_session("s")
        storage.save_message("s", "user", "a")
        storage.delete_session("s")
        count = storage.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", ("s",)
        ).fetchone()[0]
        assert count == 0


class TestListSessions:
    """Tests for list_sessions."""

    def test_message_count(self, storage):
        """list_sessions reports the correct message_count per session."""
        storage.create_session("s1")
        storage.save_message("s1", "user", "a")
        storage.save_message("s1", "user", "b")
        storage.create_session("s2")

        sessions = {s["session_id"]: s for s in storage.list_sessions()}
        assert sessions["s1"]["message_count"] == 2
        assert sessions["s1"]["created_at"]
        assert sessions["s2"]["message_count"] == 0

    def test_empty_storage(self, storage):
        """list_sessions returns [] for no sessions."""
        assert storage.list_sessions() == []

    def test_limit(self, storage):
        """list_sessions respects the limit."""
        for i in range(5):
            storage.create_session(f"s{i}")
        assert len(storage.list_sessions(limit=3)) == 3


class TestValidateAndLifecycle:
    """Tests for validation and connection lifecycle."""

    def test_do_validate_true(self, storage):
        """_do_validate returns True on a healthy connection."""
        assert storage._do_validate() is True

    def test_validate_connection_true(self, storage):
        """validate_connection returns True via the ValidatableService base."""
        assert storage.validate_connection(force=True) is True

    def test_do_validate_false_for_bad_path(self, tmp_path):
        """_do_validate returns False when the DB cannot be opened."""
        s = ConversationStorage(
            db_path=str(tmp_path / "nonexistent" / "cd" / "x.db")
        )
        # Force a broken state by replacing the connection with a closed one.
        s._conn = sqlite3.connect(":memory:")
        s._conn.close()
        try:
            assert s._do_validate() is False
        finally:
            # Drop the broken connection reference so close() can't fail.
            s._conn = None

    def test_close(self, storage):
        """Verify close commits and closes the connection."""
        storage.create_session("s")
        storage.close()
        assert storage._conn is None

    def test_context_manager(self, tmp_path):
        """ConversationStorage works as a context manager."""
        db_path = str(tmp_path / "cm.db")
        with ConversationStorage(db_path=db_path) as s:
            s.create_session("s")
            assert s.session_exists("s")
        # Connection closed after exiting the with block.
        assert s._conn is None
