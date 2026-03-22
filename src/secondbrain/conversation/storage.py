"""Conversation storage implementation for MongoDB."""

import logging
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
)

from secondbrain.config import Config, get_config
from secondbrain.exceptions import StorageConnectionError
from secondbrain.utils.connections import ValidatableService

logger = logging.getLogger(__name__)

__all__ = ["ConversationStorage"]


class ConversationStorage(ValidatableService):
    """MongoDB storage for conversation sessions.

    Provides CRUD operations for managing conversation sessions with message
    history. Uses ValidatableService base class for connection validation
    with TTL-based caching.

    Document Structure:
    -------------------
    {
        "_id": ObjectId,
        "session_id": str,
        "messages": [
            {
                "role": str,
                "content": str,
                "timestamp": str (ISO 8601)
            }
        ],
        "created_at": str (ISO 8601),
        "updated_at": str (ISO 8601)
    }

    Example:
    --------
        >>> storage = ConversationStorage()
        >>> session_id = storage.create_session("session-123")
        >>> storage.save_message(session_id, "user", "Hello")
        >>> storage.save_message(session_id, "assistant", "Hi there!")
        >>> history = storage.get_history(session_id)
        >>> storage.delete_session(session_id)
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize conversation storage with MongoDB connection.

        Args:
            mongo_uri: MongoDB connection URI. If None, uses config value.
            db_name: Database name. If None, uses config value (default: "secondbrain").
            collection_name: Collection name. If None, uses config value (default: "conversations").

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> storage = ConversationStorage(
            ...     mongo_uri="mongodb://localhost:27017",
            ...     db_name="chat_db",
            ...     collection_name="sessions"
            ... )
        """
        config = get_config()
        self.mongo_uri: str = mongo_uri or config.mongo_uri
        self.db_name: str = db_name or config.mongo_db
        self.collection_name: str = collection_name or "conversations"
        self._config: Config = config
        self._client: MongoClient[Any] | None = None
        self._db: Database[Any] | None = None
        self._collection: Collection[Any] | None = None
        super().__init__(cache_ttl=config.connection_cache_ttl)

    def _require_connection(self, operation: str = "conversation operation") -> None:
        """Validate MongoDB connection and raise StorageConnectionError if unavailable.

        Args:
            operation: Description of the operation being attempted.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> self._require_connection("create session")
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}. "
                f"Database: {self.db_name}, Collection: {self.collection_name}. "
                f"Operation: {operation}."
            )

    @property
    def client(self) -> MongoClient[Any]:
        """Get or create MongoDB client instance.

        Configured with connection pooling for optimal performance:
        - maxPoolSize: Maximum number of connections in the pool
        - minPoolSize: Minimum number of connections to maintain
        - maxIdleTimeMS: Maximum time a connection can idle
        - serverSelectionTimeoutMS: Timeout for connection selection

        Returns
        -------
            MongoClient instance for MongoDB operations.

        Example:
        --------
            >>> client = self.client
            >>> db = client[self.db_name]
        """
        if self._client is None:
            self._client = MongoClient(
                self.mongo_uri,
                directConnection=True,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=300000,
            )
        return self._client

    @property
    def db(self) -> Database[Any]:
        """Get or create database instance.

        Returns
        -------
            Database instance for the configured database.

        Example:
        --------
            >>> db = self.db
            >>> collection = db[self.collection_name]
        """
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db

    @property
    def collection(self) -> Collection[Any]:
        """Get or create collection instance.

        Returns
        -------
            Collection instance for conversations.

        Example:
        --------
            >>> coll = self.collection
            >>> result = coll.find_one({"session_id": "test-123"})
        """
        if self._collection is None:
            self._collection = self.db[self.collection_name]
        return self._collection

    def _do_validate(self) -> bool:
        """Validate MongoDB connection.

        Performs a ping command to verify the connection is alive.

        Returns
        -------
            True if connection is valid, False otherwise.

        Example:
        --------
            >>> is_valid = self._do_validate()
            >>> assert is_valid is True
        """
        try:
            _ = self.client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError):
            return False

    def create_session(self, session_id: str) -> str:
        """Create a new conversation session.

        Creates a new session document with empty message array and
        timestamps. Session ID is used as the unique identifier.

        Args:
            session_id: Unique identifier for the session.

        Returns
        -------
            The session_id of the created session.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> session_id = storage.create_session("user-session-123")
            >>> assert session_id == "user-session-123"
        """
        self._require_connection("create session")

        now = datetime.now(UTC).isoformat()
        session_doc = {
            "session_id": session_id,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

        self.collection.insert_one(session_doc)
        return session_id

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session.

        Appends a message to the session's message array with role,
        content, and timestamp. Updates the session's updated_at
        timestamp.

        Args:
            session_id: Session identifier.
            role: Message role (e.g., "user", "assistant", "system").
            content: Message content.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> storage.save_message("session-123", "user", "Hello")
            >>> storage.save_message("session-123", "assistant", "Hi!")
        """
        self._require_connection("save message")

        message_doc = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        self.collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message_doc},
                "$set": {"updated_at": datetime.now(UTC).isoformat()},
            },
        )

    def update_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """Replace all messages in a session.

        Replaces the entire messages array for a session. Used for
        operations like context trimming where the message array
        needs to be updated wholesale.

        Args:
            session_id: Session identifier.
            messages: Complete list of message dictionaries to store.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> messages = [
            ...     {"role": "user", "content": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
            ...     {"role": "assistant", "content": "Hi!", "timestamp": "2024-01-01T00:00:01Z"},
            ... ]
            >>> storage.update_messages("session-123", messages)
        """
        self._require_connection("update messages")

        self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "messages": messages,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )

    def get_history(
        self, session_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session.

        Returns the messages array from the session document.
        If limit is specified, returns only the most recent N messages.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return. If None, returns all.

        Returns
        -------
            List of message dictionaries with role, content, and timestamp.
            Returns empty list if session not found or has no messages.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> storage.save_message("session-123", "user", "Hello")
            >>> storage.save_message("session-123", "assistant", "Hi!")
            >>> history = storage.get_history("session-123")
            >>> len(history)
            2
            >>> recent = storage.get_history("session-123", limit=1)
            >>> len(recent)
            1
        """
        self._require_connection("get history")

        session = self.collection.find_one(
            {"session_id": session_id}, {"messages": 1, "_id": 0}
        )

        if session is None:
            return []

        messages = session.get("messages", []) or []

        if limit is not None and limit > 0:
            result: list[dict[str, Any]] = messages[-limit:]
            return result

        return messages

    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session.

        Removes the session document from the collection.

        Args:
            session_id: Session identifier to delete.

        Returns
        -------
            True if session was deleted, False if session not found.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> storage.create_session("session-123")
            >>> deleted = storage.delete_session("session-123")
            >>> deleted
            True
            >>> storage.delete_session("nonexistent")
            False
        """
        self._require_connection("delete session")

        result = self.collection.delete_one({"session_id": session_id})
        return bool(result.deleted_count > 0)

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all conversation sessions.

        Returns metadata for all sessions, including session_id,
        created_at, and message count.

        Args:
            limit: Maximum number of sessions to return (default: 100).

        Returns
        -------
            List of session metadata dictionaries with session_id,
            created_at, and message_count fields.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> storage.create_session("session-1")
            >>> storage.create_session("session-2")
            >>> sessions = storage.list_sessions()
            >>> len(sessions)
            2
            >>> sessions[0]["session_id"]
            "session-1"
            >>> sessions[0]["message_count"]
            0
        """
        self._require_connection("list sessions")

        cursor = self.collection.find(
            {},
            {
                "session_id": 1,
                "created_at": 1,
                "messages": 1,
                "_id": 0,
            },
        ).limit(limit)

        sessions: list[dict[str, Any]] = []
        for session in cursor:
            session_dict = dict(session)
            sessions.append(
                {
                    "session_id": str(session_dict.get("session_id") or ""),
                    "created_at": session_dict.get("created_at"),
                    "message_count": len(session_dict.get("messages", []) or []),
                }
            )

        return sessions

    def close(self) -> None:
        """Close MongoDB connection and release resources.

        Closes the MongoDB client connection to prevent resource leaks.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> # ... use storage ...
            >>> storage.close()
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._db is not None:
            self._db = None
        if self._collection is not None:
            self._collection = None

    def __enter__(self) -> "ConversationStorage":
        """Enter runtime context manager.

        Returns
        -------
            Self instance for use in with statement.

        Example:
        --------
            >>> with ConversationStorage() as storage:
            ...     storage.create_session("session-123")
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit runtime context manager.

        Ensures connection is closed when exiting context.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception instance if an exception was raised.
            exc_tb: Traceback if an exception was raised.

        Example:
        --------
            >>> with ConversationStorage() as storage:
            ...     storage.save_message("session-123", "user", "Hello")
        """
        self.close()
