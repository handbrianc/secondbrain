"""SQLite storage implementation for conversation sessions.

Replaces the MongoDB-backed :class:`ConversationStorage` with an embedded
SQLite backend while preserving the exact public API so ``ConversationSession``
and all CLI/RAG callers work unchanged.

Storage layout mirrors the previous Mongo envelope: a ``sessions`` row plus one
row per message in ``messages``. Ordering is pure array position (append +
most-recent-N slice + whole-array replace for context trim), matching the old
document semantics exactly.

Schema version is tracked via ``PRAGMA user_version``.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from secondbrain.config import config
from secondbrain.utils.connections import ValidatableService

__all__ = ["ConversationStorage"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  position    INTEGER NOT NULL,
  role        TEXT NOT NULL,
  content     TEXT NOT NULL,
  timestamp   TEXT NOT NULL,
  PRIMARY KEY (session_id, position)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_pos
  ON messages(session_id, position);
"""


class ConversationStorage(ValidatableService):
    """Embedded SQLite storage for conversation sessions.

    Provides CRUD operations for managing conversation sessions with message
    history. Uses the ``ValidatableService`` base class for connection
    validation with TTL-based caching.

    Example:
    --------
        >>> storage = ConversationStorage()
        >>> session_id = storage.create_session("session-123")
        >>> storage.save_message(session_id, "user", "Hello")
        >>> storage.save_message(session_id, "assistant", "Hi there!")
        >>> history = storage.get_history(session_id)
        >>> storage.delete_session(session_id)
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize conversation storage with an embedded SQLite database.

        Args:
            db_path: Filesystem path to the SQLite database. If ``None``,
                uses the configured ``cfg.sqlite_path`` (already expanduser'd).
        """
        cfg = config()
        path = db_path if db_path is not None else cfg.sqlite_path
        self.db_path: str = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        super().__init__(cache_ttl=cfg.connection_cache_ttl)

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or lazily create the SQLite connection.

        Uses ``check_same_thread=False`` so calls from any thread share one
        connection (all writes are serialized by :attr:`_lock`), with WAL
        journaling for concurrent readers.

        Returns
        -------
            A live :class:`sqlite3.Connection` to the conversation database.
        """
        if self._conn is None:
            db_path = Path(self.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA user_version=1")
            conn.executescript(SCHEMA)
            self._conn = conn
        return self._conn

    def _do_validate(self) -> bool:
        """Validate the SQLite connection.

        Connects to the database and runs ``PRAGMA quick_check(1)`` to verify
        integrity.

        Returns
        -------
            True if the connection is valid, False otherwise.
        """
        try:
            row = self.conn.execute("PRAGMA quick_check(1)").fetchone()
            return bool(row and row[0] == "ok")
        except sqlite3.Error:
            return False

    def create_session(self, session_id: str) -> str:
        """Create a new conversation session.

        Args:
            session_id: Unique identifier for the session.

        Returns
        -------
            The session_id of the created session.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self.conn.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            self.conn.commit()
        return session_id

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message to a session.

        Args:
            session_id: Session identifier.
            role: Message role (e.g., "user", "assistant", "system").
            content: Message content.
        """
        now = datetime.now(UTC).isoformat()
        timestamp = now
        with self._lock:
            conn = self.conn
            row = conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            position = int(row[0])
            conn.execute(
                "INSERT INTO messages (session_id, position, role, content, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, position, role, content, timestamp),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()

    def update_messages(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Replace all messages in a session.

        Deletes all messages for the session and inserts the provided array at
        sequential positions. Used for context trimming where the message array
        needs to be updated wholesale.

        Args:
            session_id: Session identifier.
            messages: Complete list of message dictionaries to store.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            conn = self.conn
            conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            conn.executemany(
                "INSERT INTO messages (session_id, position, role, content, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        i,
                        msg.get("role", ""),
                        msg.get("content", ""),
                        msg.get("timestamp", now),
                    )
                    for i, msg in enumerate(messages)
                ],
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()

    def get_history(
        self, session_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return (most recent N).
                If ``None`` or ``<= 0``, returns all messages in order.

        Returns
        -------
            List of message dictionaries with role, content, and timestamp.
            Returns empty list if session not found or has no messages.
        """
        conn = self.conn
        if limit is not None and limit > 0:
            rows = conn.execute(
                "SELECT * FROM ("
                "  SELECT * FROM messages WHERE session_id = ? "
                "  ORDER BY position DESC LIMIT ?"
                ") ORDER BY position ASC",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY position ASC",
                (session_id,),
            ).fetchall()

        return [
            {"role": row["role"], "content": row["content"], "timestamp": row["timestamp"]}
            for row in rows
        ]

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists in storage.

        Args:
            session_id: Session identifier to check.

        Returns
        -------
            True if session exists, False otherwise.
        """
        row = self.conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session.

        Cascades to delete all associated messages.

        Args:
            session_id: Session identifier to delete.

        Returns
        -------
            True if session was deleted, False if session not found.
        """
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            self.conn.commit()
            return cur.rowcount > 0

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List conversation sessions.

        Returns metadata for each session including session_id, created_at,
        and message count.

        Args:
            limit: Maximum number of sessions to return (default: 100).

        Returns
        -------
            List of session metadata dictionaries with session_id,
            created_at, and message_count fields.
        """
        rows = self.conn.execute(
            "SELECT s.session_id, s.created_at, COUNT(m.position) AS message_count "
            "FROM sessions s "
            "LEFT JOIN messages m ON m.session_id = s.session_id "
            "GROUP BY s.session_id, s.created_at "
            "ORDER BY s.session_id "
            "LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    def close(self) -> None:
        """Close the SQLite connection and release resources."""
        if self._conn is not None:
            with self._lock:
                self._conn.commit()
                self._conn.close()
            self._conn = None

    def __enter__(self) -> ConversationStorage:
        """Enter runtime context manager.

        Returns
        -------
            Self instance for use in with statement.
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
        """
        self.close()
