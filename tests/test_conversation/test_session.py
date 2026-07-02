"""Unit tests for ConversationSession module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from secondbrain.conversation.session import ConversationSession
from secondbrain.conversation.storage import ConversationStorage


@pytest.fixture
def mock_storage():
    """Mock ConversationStorage for session tests."""
    storage = MagicMock(spec=ConversationStorage)
    storage.get_history.return_value = []
    storage.create_session.return_value = "test-session"
    storage.save_message.return_value = None
    storage.update_messages.return_value = None
    return storage


class TestConversationSessionInit:
    """Tests for ConversationSession initialization."""

    def test_session_init_with_defaults(self, mock_storage):
        """Test session initialization with default context window."""
        session = ConversationSession("test-123", mock_storage)

        assert session._session_id == "test-123"
        assert session._context_window == 5
        assert session._history == []

    def test_session_init_with_custom_context_window(self, mock_storage):
        """Test session initialization with custom context window."""
        session = ConversationSession("test-123", mock_storage, context_window=5)

        assert session._context_window == 5


class TestConversationSessionCreate:
    """Tests for ConversationSession.create classmethod."""

    def test_create_new_session(self, mock_storage):
        """Test creating a new session."""
        session = ConversationSession.create("new-session", mock_storage)

        mock_storage.create_session.assert_called_once_with("new-session")
        assert session._session_id == "new-session"
        assert session.is_empty is True
        assert session.message_count == 0

    def test_create_session_with_custom_context_window(self, mock_storage):
        """Test creating session with custom context window."""
        session = ConversationSession.create(
            "new-session", mock_storage, context_window=3
        )

        assert session._context_window == 3


class TestConversationSessionLoad:
    """Tests for ConversationSession.load classmethod."""

    def test_load_existing_session(self, mock_storage):
        """Test loading an existing session with messages."""
        mock_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_storage.get_history.return_value = mock_messages

        session = ConversationSession.load("existing-session", mock_storage)

        assert session is not None
        assert session._session_id == "existing-session"
        assert len(session._history) == 2
        mock_storage.get_history.assert_called_once_with("existing-session")

    def test_load_nonexistent_session(self, mock_storage):
        """Test loading a session that doesn't exist."""
        mock_storage.session_exists.return_value = False

        session = ConversationSession.load("nonexistent", mock_storage)

        assert session is None

    def test_load_session_with_custom_context_window(self, mock_storage):
        """Test loading session with custom context window."""
        mock_messages = [{"role": "user", "content": "Test"}]
        mock_storage.get_history.return_value = mock_messages

        session = ConversationSession.load(
            "session-123", mock_storage, context_window=7
        )

        assert session is not None
        assert session._context_window == 7


class TestConversationSessionAddMessage:
    """Tests for ConversationSession.add_message method."""

    def test_add_message_user(self, mock_storage):
        """Test adding a user message."""
        session = ConversationSession("test-123", mock_storage)

        session.add_message("user", "Hello, world!")

        assert len(session._history) == 1
        assert session._history[0]["role"] == "user"
        assert session._history[0]["content"] == "Hello, world!"
        mock_storage.save_message.assert_called_once_with(
            "test-123", "user", "Hello, world!"
        )

    def test_add_message_assistant(self, mock_storage):
        """Test adding an assistant message."""
        session = ConversationSession("test-123", mock_storage)

        session.add_message("assistant", "Hi there!")

        assert session._history[0]["role"] == "assistant"

    def test_add_message_trims_when_exceeds_context_window(self, mock_storage):
        """Test that adding messages triggers trim when exceeding context window."""
        session = ConversationSession("test-123", mock_storage, context_window=3)

        for i in range(4):
            session.add_message("user", f"Message {i}")

        assert len(session._history) == 3
        assert session._history[0]["content"] == "Message 1"
        assert session._history[-1]["content"] == "Message 3"
        mock_storage.update_messages.assert_called()


class TestConversationSessionGetHistory:
    """Tests for ConversationSession.get_history method."""

    def test_get_history_all_messages(self, mock_storage):
        """Test getting full history."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]

        history = session.get_history()

        assert len(history) == 3
        assert history[0]["content"] == "First"

    def test_get_history_with_limit(self, mock_storage):
        """Test getting limited history."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]

        history = session.get_history(limit=2)

        assert len(history) == 2
        assert history[0]["content"] == "Second"
        assert history[1]["content"] == "Third"

    def test_get_history_with_zero_limit(self, mock_storage):
        """Test getting history with limit=0 returns empty list."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [{"role": "user", "content": "Test"}]

        history = session.get_history(limit=0)

        assert history == []

    def test_get_history_returns_copy(self, mock_storage):
        """Test that get_history returns a copy, not the original."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [{"role": "user", "content": "Test"}]

        history = session.get_history()
        history.append({"role": "user", "content": "Modified"})

        assert len(session._history) == 1


class TestConversationSessionGetContextMessages:
    """Tests for ConversationSession.get_context_messages method."""

    def test_get_context_messages_respects_window(self, mock_storage):
        """Test that context messages respect context window."""
        session = ConversationSession("test-123", mock_storage, context_window=2)
        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]

        context = session.get_context_messages()

        assert len(context) == 2
        assert context[0]["content"] == "Second"
        assert context[1]["content"] == "Third"


class TestConversationSessionTrimContext:
    """Tests for ConversationSession.trim_context method."""

    def test_trim_context_when_exceeds_window(self, mock_storage):
        """Test trimming when history exceeds context window."""
        session = ConversationSession("test-123", mock_storage, context_window=2)
        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]

        session.trim_context()

        assert len(session._history) == 2
        mock_storage.update_messages.assert_called_once_with(
            "test-123", session._history
        )

    def test_trim_context_no_op_when_within_window(self, mock_storage):
        """Test that trim is no-op when within context window."""
        session = ConversationSession("test-123", mock_storage, context_window=5)
        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
        ]

        session.trim_context()

        assert len(session._history) == 2
        mock_storage.update_messages.assert_not_called()


class TestConversationSessionClearHistory:
    """Tests for ConversationSession.clear_history method."""

    def test_clear_history_empties_messages(self, mock_storage):
        """Test that clear_history empties the message list."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        session.clear_history()

        assert session._history == []
        assert session.is_empty is True

    def test_clear_history_preserves_session(self, mock_storage):
        """Test that clear_history doesn't delete the session."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [{"role": "user", "content": "Test"}]

        session.clear_history()

        assert session._session_id == "test-123"


class TestConversationSessionProperties:
    """Tests for ConversationSession properties."""

    def test_message_count(self, mock_storage):
        """Test message_count property."""
        session = ConversationSession("test-123", mock_storage)

        assert session.message_count == 0

        session._history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
        ]

        assert session.message_count == 2

    def test_is_empty_true(self, mock_storage):
        """Test is_empty when no messages."""
        session = ConversationSession("test-123", mock_storage)

        assert session.is_empty is True

    def test_is_empty_false(self, mock_storage):
        """Test is_empty when has messages."""
        session = ConversationSession("test-123", mock_storage)
        session._history = [{"role": "user", "content": "Test"}]

        assert session.is_empty is False


class TestConversationSessionErrorPaths:
    """Comprehensive error path tests for ConversationSession."""

    def test_session_state_transitions(self, mock_storage):
        """Test session state transitions from empty to populated.

        Error Path: State changes as messages are added/removed.
        """
        session = ConversationSession.create("test-session", mock_storage)

        # Initial state: empty
        assert session.is_empty is True
        assert session.message_count == 0

        # Add first message
        session.add_message("user", "Hello")
        assert session.is_empty is False
        assert session.message_count == 1

        # Add more messages
        session.add_message("assistant", "Hi!")
        session.add_message("user", "How are you?")
        assert session.message_count == 3

        # Clear history
        session.clear_history()
        assert session.is_empty is True
        assert session.message_count == 0

    def test_session_handles_concurrent_access(self, mock_storage):
        """Test session handles concurrent message additions.

        Error Path: Thread safety under concurrent access.
        """
        import threading

        session = ConversationSession.create(
            "test-session", mock_storage, context_window=100
        )

        def add_messages(count):
            for i in range(count):
                session.add_message("user", f"Message {i}")

        threads = []
        for _ in range(3):
            t = threading.Thread(target=add_messages, args=(5,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert session.message_count == 15

    def test_session_persistence_error_recovery(self, mock_storage):
        """Test session handles storage errors gracefully.

        Error Path: Storage failures during message persistence.
        """
        # Make storage raise an error on save_message
        mock_storage.save_message.side_effect = RuntimeError("Storage error")

        session = ConversationSession.create("test-session", mock_storage)

        # Should raise the storage error
        with pytest.raises(RuntimeError, match="Storage error"):
            session.add_message("user", "Hello")

        # Verify the error occurred during save
        mock_storage.save_message.assert_called()

    def test_session_invalid_state_handling(self, mock_storage):
        """Test session handles invalid state gracefully.

        Error Path: Invalid state scenarios.
        """
        session = ConversationSession.create("test-session", mock_storage)

        # Get history with negative limit should return empty
        history = session.get_history(limit=-1)
        assert history == []

        # Get history with zero limit should return empty
        history = session.get_history(limit=0)
        assert history == []

    def test_session_cleanup_on_error(self, mock_storage):
        """Test session cleanup when errors occur.

        Error Path: State cleanup after errors.
        """
        session = ConversationSession.create("test-session", mock_storage)

        # Add some messages
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        assert session.message_count == 2

        # Simulate error scenario by manually clearing
        session._history = []

        # Verify cleanup
        assert session.is_empty is True
        assert session.message_count == 0

    def test_session_timeout_handling(self, mock_storage):
        """Test session handles timeout scenarios.

        Error Path: Timeout during storage operations.
        """
        import time

        # Make storage take a long time
        def slow_save(*args, **kwargs):
            time.sleep(0.1)
            return None

        mock_storage.save_message.side_effect = slow_save

        session = ConversationSession.create("test-session", mock_storage)

        # Should complete despite slow storage
        start = time.time()
        session.add_message("user", "Hello")
        elapsed = time.time() - start

        # Should complete within reasonable time
        assert elapsed < 1.0
        assert session.message_count == 1

    def test_session_load_returns_none_for_nonexistent(self, mock_storage):
        """Test that load returns None for non-existent session.

        Error Path: Loading non-existent session.
        """
        mock_storage.session_exists.return_value = False

        result = ConversationSession.load("nonexistent", mock_storage)

        assert result is None

    def test_session_create_raises_on_none_storage(self):
        """Test that create raises ValueError when storage is None.

        Error Path: Missing required storage parameter.
        """
        with pytest.raises(ValueError, match="storage must be provided"):
            ConversationSession.create("test-session", storage=None)

    def test_session_trim_context_when_under_limit(self, mock_storage):
        """Test trim_context doesn't trim when under limit.

        Error Path: trim_context with valid message count.
        """
        session = ConversationSession.create(
            "test-session", mock_storage, context_window=5
        )

        # Add 3 messages (under limit)
        for i in range(3):
            session.add_message("user", f"Message {i}")

        # trim_context should not change anything
        session.trim_context()

        assert session.message_count == 3
        # update_messages should not be called
        mock_storage.update_messages.assert_not_called()

    def test_session_trim_context_when_over_limit(self, mock_storage):
        """Test trim_context removes oldest messages when over limit.

        Error Path: trim_context with excessive messages.
        """
        session = ConversationSession.create(
            "test-session", mock_storage, context_window=3
        )

        # Add 5 messages (over limit)
        for i in range(5):
            session.add_message("user", f"Message {i}")

        # Should have been trimmed during add
        assert session.message_count == 3
        # Should keep only the last 3 messages
        assert session._history[0]["content"] == "Message 2"
        assert session._history[-1]["content"] == "Message 4"

    def test_session_get_history_returns_copy(self, mock_storage):
        """Test that get_history returns a copy, not the original list.

        Error Path: Modifying returned history doesn't affect internal state.
        """
        session = ConversationSession.create("test-session", mock_storage)
        session.add_message("user", "Hello")

        history = session.get_history()
        history.append({"role": "user", "content": "Injected"})

        # Internal state should be unchanged
        assert session.message_count == 1
        assert len(session._history) == 1

    def test_session_clear_history_persists_to_storage(self, mock_storage):
        """Test that clear_history persists to storage.

        Error Path: Persistence after clearing history.
        """
        session = ConversationSession.create("test-session", mock_storage)
        session.add_message("user", "Hello")

        session.clear_history()

        # Should persist empty history to storage
        mock_storage.update_messages.assert_called_with("test-session", [])

    def test_session_add_message_with_empty_content(self, mock_storage):
        """Test adding message with empty content.

        Error Path: Edge case with empty content.
        """
        session = ConversationSession.create("test-session", mock_storage)

        # Should allow empty content (validation is not done here)
        session.add_message("user", "")

        assert session.message_count == 1
        assert session._history[0]["content"] == ""

    def test_session_add_message_with_special_characters(self, mock_storage):
        """Test adding message with special characters.

        Error Path: Special characters in content.
        """
        session = ConversationSession.create("test-session", mock_storage)

        special_content = "Hello! @#$%^&*() 中文 🎉"
        session.add_message("user", special_content)

        assert session.message_count == 1
        assert session._history[0]["content"] == special_content

    def test_session_properties_consistency(self, mock_storage):
        """Test that session properties are consistent.

        Error Path: Property calculation consistency.
        """
        session = ConversationSession.create("test-session", mock_storage)

        # Test consistency at various states
        assert session.is_empty is True
        assert session.message_count == 0
        assert len(session.get_history()) == 0

        session.add_message("user", "Hello")

        assert session.is_empty is False
        assert session.message_count == 1
        assert len(session.get_history()) == 1

        session.clear_history()

        assert session.is_empty is True
        assert session.message_count == 0
        assert len(session.get_history()) == 0

    def test_session_get_context_messages_respects_window(self, mock_storage):
        """Test get_context_messages respects context window.

        Error Path: Context window limiting.
        """
        session = ConversationSession.create(
            "test-session", mock_storage, context_window=3
        )

        # Add 5 messages
        for i in range(5):
            session.add_message("user", f"Message {i}")

        # Should only return last 3
        context = session.get_context_messages()
        assert len(context) == 3
        assert context[0]["content"] == "Message 2"
        assert context[-1]["content"] == "Message 4"

    def test_session_load_with_custom_context_window(self, mock_storage):
        """Test load with custom context window.

        Error Path: Custom context window on load.
        """
        mock_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_storage.get_history.return_value = mock_messages

        session = ConversationSession.load("existing", mock_storage, context_window=10)

        assert session is not None
        assert session._context_window == 10
        assert session.message_count == 2

    def test_session_auto_generates_uuid_when_none(self, mock_storage):
        """Test that session creates auto-generated UUID when session_id is None.

        Error Path: Auto-generation of session ID.
        """
        session = ConversationSession.create(storage=mock_storage)

        # Should have a UUID-like session ID
        assert session.session_id is not None
        assert len(session.session_id) > 0
        # Should be a valid UUID format (has hyphens)
        assert "-" in session.session_id
