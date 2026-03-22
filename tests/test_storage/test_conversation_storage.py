"""Unit tests for ConversationStorage module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.conversation.storage import ConversationStorage
from secondbrain.exceptions import StorageConnectionError


@pytest.fixture
def mock_collection():
    """Mock MongoDB collection for tests."""
    return MagicMock()


@pytest.fixture
def mock_db(mock_collection):
    """Mock MongoDB database that returns mock collection."""
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db


@pytest.fixture
def mock_client(mock_db):
    """Mock MongoDB client that returns mock database."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1}
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    return mock_client


@pytest.fixture
def storage_with_mocks(mock_client, mock_collection):
    """Provide ConversationStorage with mocked MongoDB connections."""
    with patch(
        "secondbrain.conversation.storage.MongoClient", return_value=mock_client
    ) as mock_client_class:
        storage = ConversationStorage(
            mongo_uri="mongodb://localhost:27017",
            db_name="test_db",
            collection_name="test_conversations",
        )
        # Force initialization of properties
        _ = storage.collection
        yield storage, mock_collection, mock_client_class


class TestConversationStorageCreateSession:
    """Tests for ConversationStorage.create_session method."""

    def test_create_session_success(self, storage_with_mocks):
        """Test successful session creation."""
        storage, mock_collection, _ = storage_with_mocks

        session_id = storage.create_session("test-session-123")

        assert session_id == "test-session-123"
        mock_collection.insert_one.assert_called_once()
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args["session_id"] == "test-session-123"
        assert call_args["messages"] == []
        assert "created_at" in call_args
        assert "updated_at" in call_args

    def test_create_session_with_special_characters(self, storage_with_mocks):
        """Test session creation with special characters in ID."""
        storage, mock_collection, _ = storage_with_mocks

        session_id = storage.create_session("session-with-dashes_and_underscores123")

        assert session_id == "session-with-dashes_and_underscores123"
        mock_collection.insert_one.assert_called_once()

    def test_create_session_connection_error(self, storage_with_mocks):
        """Test session creation fails when MongoDB is unavailable."""
        storage, _, _ = storage_with_mocks
        storage._client = None
        storage._do_validate = lambda: False

        with pytest.raises(StorageConnectionError, match="Cannot connect to MongoDB"):
            storage.create_session("test-session")


class TestConversationStorageGetHistory:
    """Tests for ConversationStorage.get_history method."""

    def test_get_history_empty_session(self, storage_with_mocks):
        """Test getting history from session with no messages."""
        storage, mock_collection, _ = storage_with_mocks
        mock_collection.find_one.return_value = {"messages": []}

        history = storage.get_history("test-session")

        assert history == []
        mock_collection.find_one.assert_called_once_with(
            {"session_id": "test-session"}, {"messages": 1, "_id": 0}
        )

    def test_get_history_with_messages(self, storage_with_mocks):
        """Test getting history from session with messages."""
        storage, mock_collection, _ = storage_with_mocks
        mock_messages = [
            {"role": "user", "content": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
            {
                "role": "assistant",
                "content": "Hi!",
                "timestamp": "2024-01-01T00:00:01Z",
            },
        ]
        mock_collection.find_one.return_value = {"messages": mock_messages}

        history = storage.get_history("test-session")

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_get_history_with_limit(self, storage_with_mocks):
        """Test getting limited history returns most recent messages."""
        storage, mock_collection, _ = storage_with_mocks
        mock_messages = [
            {"role": "user", "content": "First", "timestamp": "2024-01-01T00:00:00Z"},
            {
                "role": "assistant",
                "content": "Second",
                "timestamp": "2024-01-01T00:00:01Z",
            },
            {"role": "user", "content": "Third", "timestamp": "2024-01-01T00:00:02Z"},
        ]
        mock_collection.find_one.return_value = {"messages": mock_messages}

        history = storage.get_history("test-session", limit=2)

        assert len(history) == 2
        assert history[0]["content"] == "Second"
        assert history[1]["content"] == "Third"

    def test_get_history_session_not_found(self, storage_with_mocks):
        """Test getting history from non-existent session returns empty list."""
        storage, mock_collection, _ = storage_with_mocks
        mock_collection.find_one.return_value = None

        history = storage.get_history("non-existent-session")

        assert history == []


class TestConversationStorageSaveMessage:
    """Tests for ConversationStorage.save_message method."""

    def test_save_message_success(self, storage_with_mocks):
        """Test successful message saving."""
        storage, mock_collection, _ = storage_with_mocks

        storage.save_message("test-session", "user", "Hello, world!")

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"session_id": "test-session"}
        assert "$push" in call_args[0][1]
        assert "$set" in call_args[0][1]
        pushed_message = call_args[0][1]["$push"]["messages"]
        assert pushed_message["role"] == "user"
        assert pushed_message["content"] == "Hello, world!"
        assert "timestamp" in pushed_message

    def test_save_message_with_system_role(self, storage_with_mocks):
        """Test saving message with system role."""
        storage, mock_collection, _ = storage_with_mocks

        storage.save_message("test-session", "system", "You are a helpful assistant.")

        mock_collection.update_one.assert_called_once()
        pushed_message = mock_collection.update_one.call_args[0][1]["$push"]["messages"]
        assert pushed_message["role"] == "system"

    def test_save_message_updates_timestamp(self, storage_with_mocks):
        """Test that save_message updates the updated_at field."""
        storage, mock_collection, _ = storage_with_mocks

        storage.save_message("test-session", "user", "Test")

        update_doc = mock_collection.update_one.call_args[0][1]
        assert "$set" in update_doc
        assert "updated_at" in update_doc["$set"]


class TestConversationStorageUpdateMessages:
    """Tests for ConversationStorage.update_messages method."""

    def test_update_messages_replaces_all(self, storage_with_mocks):
        """Test that update_messages replaces entire message array."""
        storage, mock_collection, _ = storage_with_mocks
        messages = [
            {"role": "user", "content": "First", "timestamp": "2024-01-01T00:00:00Z"},
            {
                "role": "assistant",
                "content": "Second",
                "timestamp": "2024-01-01T00:00:01Z",
            },
        ]

        storage.update_messages("test-session", messages)

        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"session_id": "test-session"}
        assert "$set" in call_args[0][1]
        assert call_args[0][1]["$set"]["messages"] == messages

    def test_update_messages_empty_list(self, storage_with_mocks):
        """Test updating with empty message list."""
        storage, mock_collection, _ = storage_with_mocks

        storage.update_messages("test-session", [])

        mock_collection.update_one.assert_called_once()
        updated_messages = mock_collection.update_one.call_args[0][1]["$set"][
            "messages"
        ]
        assert updated_messages == []


class TestConversationStorageDeleteSession:
    """Tests for ConversationStorage.delete_session method."""

    def test_delete_session_success(self, storage_with_mocks):
        """Test successful session deletion."""
        storage, mock_collection, _ = storage_with_mocks
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result

        result = storage.delete_session("test-session")

        assert result is True
        mock_collection.delete_one.assert_called_once_with(
            {"session_id": "test-session"}
        )

    def test_delete_session_not_found(self, storage_with_mocks):
        """Test deletion of non-existent session returns False."""
        storage, mock_collection, _ = storage_with_mocks
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_collection.delete_one.return_value = mock_result

        result = storage.delete_session("non-existent")

        assert result is False

    def test_delete_session_connection_error(self, storage_with_mocks):
        """Test deletion fails when MongoDB is unavailable."""
        storage, _, _ = storage_with_mocks
        storage._do_validate = lambda: False

        with pytest.raises(StorageConnectionError, match="Cannot connect to MongoDB"):
            storage.delete_session("test-session")


class TestConversationStorageListSessions:
    """Tests for ConversationStorage.list_sessions method."""

    @pytest.fixture
    def mock_cursor(self):
        """Create a mock MongoDB cursor."""
        cursor = MagicMock()
        cursor.limit = MagicMock(return_value=cursor)
        return cursor

    def test_list_sessions_empty(self, storage_with_mocks, mock_cursor):
        """Test listing sessions when none exist."""
        storage, mock_collection, _ = storage_with_mocks
        mock_collection.find.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])

        sessions = storage.list_sessions()

        assert sessions == []

    def test_list_sessions_with_data(self, storage_with_mocks, mock_cursor):
        """Test listing sessions returns metadata."""
        storage, mock_collection, _ = storage_with_mocks
        mock_sessions = [
            {
                "session_id": "session-1",
                "created_at": "2024-01-01T00:00:00Z",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                ],
            },
            {
                "session_id": "session-2",
                "created_at": "2024-01-02T00:00:00Z",
                "messages": [],
            },
        ]
        mock_collection.find.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter(mock_sessions)

        sessions = storage.list_sessions()

        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "session-1"
        assert sessions[0]["message_count"] == 1
        assert sessions[0]["created_at"] == "2024-01-01T00:00:00Z"
        assert sessions[1]["session_id"] == "session-2"
        assert sessions[1]["message_count"] == 0

    def test_list_sessions_with_limit(self, storage_with_mocks, mock_cursor):
        """Test listing sessions respects limit parameter."""
        storage, mock_collection, _ = storage_with_mocks
        mock_sessions = [
            {
                "session_id": f"session-{i}",
                "created_at": "2024-01-01T00:00:00Z",
                "messages": [],
            }
            for i in range(5)
        ]
        mock_collection.find.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter(mock_sessions)

        sessions = storage.list_sessions(limit=5)

        assert len(sessions) == 5
        mock_collection.find.return_value.limit.assert_called_once_with(5)


class TestConversationStorageContextManager:
    """Tests for ConversationStorage context manager."""

    def test_context_manager_closes_connection(self):
        """Test that context manager properly closes connections."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch(
            "secondbrain.conversation.storage.MongoClient", return_value=mock_client
        ):
            storage = ConversationStorage()
            # Force client initialization by accessing the property
            _ = storage.client
            with storage:
                pass

        mock_client.close.assert_called_once()


class TestConversationStorageClose:
    """Tests for ConversationStorage.close method."""

    def test_close_sets_attributes_to_none(self, storage_with_mocks):
        """Test that close properly sets internal attributes to None."""
        storage, _, _ = storage_with_mocks

        storage.close()

        assert storage._client is None
        assert storage._db is None
        assert storage._collection is None
