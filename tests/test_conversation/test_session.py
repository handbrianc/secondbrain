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
        assert session._context_window == 10
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
        mock_storage.get_history.return_value = []

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
