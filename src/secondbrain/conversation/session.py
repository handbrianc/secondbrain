"""Conversation session management with in-memory state and persistence."""

from __future__ import annotations

from typing import Any

from secondbrain.conversation.storage import ConversationStorage


class ConversationSession:
    """Manages conversation state and history in memory with persistence.

    Provides an in-memory cache of conversation messages with automatic
    persistence to MongoDB via ConversationStorage. Supports context window
    management to limit the number of messages retained for LLM context.

    Attributes:
        session_id: Unique identifier for this conversation session.
        context_window: Maximum number of recent messages to keep in context.

    Example:
    --------
        >>> storage = ConversationStorage()
        >>> session = ConversationSession.create("session-123", storage)
        >>> session.add_message("user", "Hello")
        >>> session.add_message("assistant", "Hi there!")
        >>> history = session.get_history()
        >>> len(history)
        2
        >>> session.trim_context()
    """

    def __init__(
        self,
        session_id: str,
        storage: ConversationStorage,
        context_window: int = 10,
    ) -> None:
        """Initialize session with storage connection.

        Args:
            session_id: Unique session identifier.
            storage: ConversationStorage instance for persistence.
            context_window: Number of recent messages to keep (default: 10).

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> session = ConversationSession("session-123", storage, context_window=5)
        """
        self._session_id: str = session_id
        self._storage: ConversationStorage = storage
        self._context_window: int = context_window
        self._history: list[dict[str, Any]] = []

    @classmethod
    def create(
        cls, session_id: str, storage: ConversationStorage, context_window: int = 10
    ) -> ConversationSession:
        """Create a new conversation session.

        Creates a new session in storage and returns an initialized
        ConversationSession instance with an empty message history.

        Args:
            session_id: Unique identifier for the new session.
            storage: ConversationStorage instance for persistence.
            context_window: Number of recent messages to keep (default: 10).

        Returns:
            A new ConversationSession instance.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> session = ConversationSession.create("new-session", storage)
            >>> session.is_empty
            True
        """
        storage.create_session(session_id)
        return cls(session_id, storage, context_window)

    @classmethod
    def load(
        cls, session_id: str, storage: ConversationStorage, context_window: int = 10
    ) -> ConversationSession | None:
        """Load existing session from storage.

        Retrieves conversation history from storage and initializes
        an in-memory cache. Returns None if the session does not exist.

        Args:
            session_id: Identifier of the session to load.
            storage: ConversationStorage instance for persistence.
            context_window: Number of recent messages to keep (default: 10).

        Returns:
            ConversationSession instance if found, None otherwise.

        Example:
        --------
            >>> storage = ConversationStorage()
            >>> session = ConversationSession.load("existing-session", storage)
            >>> if session is not None:
            ...     history = session.get_history()
        """
        # Check if session exists by attempting to load history
        messages = storage.get_history(session_id)

        # Session doesn't exist if we get an empty list (no messages)
        # Note: This assumes new sessions have no messages initially
        if messages == []:
            return None

        session = cls(session_id, storage, context_window)
        session._history = messages
        return session

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session.

        Appends a message to the in-memory history and persists it
        to storage immediately via save_message().

        Args:
            role: Message role (e.g., "user", "assistant", "system").
            content: Message content.

        Example:
        --------
            >>> session.add_message("user", "What is machine learning?")
            >>> session.add_message("assistant", "Machine learning is...")
        """
        # Add to in-memory history
        self._history.append({"role": role, "content": content})

        # Persist to storage
        self._storage.save_message(self._session_id, role, content)

        # Trim if exceeding context window
        if len(self._history) > self._context_window:
            self.trim_context()

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get conversation history.

        Returns messages from the in-memory cache, optionally limited
        to the most recent N messages.

        Args:
            limit: Maximum number of messages to return. If None, returns
                all messages in history.

        Returns:
            List of message dictionaries with role, content, and timestamp.

        Example:
        --------
            >>> history = session.get_history()
            >>> len(history)
            5
            >>> recent = session.get_history(limit=2)
            >>> len(recent)
            2
        """
        if limit is None:
            return self._history.copy()

        if limit <= 0:
            return []

        return self._history[-limit:]

    def get_context_messages(self) -> list[dict[str, Any]]:
        """Get messages for LLM context (respects context window).

        Returns the most recent N messages where N equals the context_window
        size. This is suitable for passing to an LLM as conversation context.

        Returns:
            List of recent message dictionaries formatted for LLM consumption.

        Example:
        --------
            >>> context = session.get_context_messages()
            >>> context[0]["role"]
            "user"
            >>> context[0]["content"]
            "Hello"
        """
        return self.get_history(limit=self._context_window)

    def trim_context(self) -> None:
        """Trim history to context window size.

        Removes oldest messages from the in-memory cache if the total
        message count exceeds the context_window. Updates storage with
        the trimmed message array.

        Example:
        --------
            >>> session._context_window = 5
            >>> for i in range(10):
            ...     session.add_message("user", f"Message {i}")
            >>> len(session.get_history())
            5
        """
        if len(self._history) <= self._context_window:
            return

        # Keep only the most recent messages
        self._history = self._history[-self._context_window :]
        self._storage.update_messages(self._session_id, self._history)

    def clear_history(self) -> None:
        """Clear all messages from session.

        Empties the in-memory message history and persists to storage.
        The session document remains but with an empty messages array.

        Example:
        --------
            >>> session.add_message("user", "Hello")
            >>> session.is_empty
            False
            >>> session.clear_history()
            >>> session.is_empty
            True
        """
        self._history = []
        # Persist the cleared history to storage
        if self._storage:
            self._storage.update_messages(self._session_id, [])

    @property
    def message_count(self) -> int:
        """Return number of messages in session.

        Returns:
            Total count of messages in the session history.

        Example:
        --------
            >>> session.message_count
            0
            >>> session.add_message("user", "Hi")
            >>> session.message_count
            1
        """
        return len(self._history)

    @property
    def is_empty(self) -> bool:
        """Return True if session has no messages.

        Returns:
            True if the session contains zero messages.

        Example:
        --------
            >>> session.is_empty
            True
            >>> session.add_message("user", "Hello")
            >>> session.is_empty
            False
        """
        return len(self._history) == 0
