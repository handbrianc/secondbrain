"""SQLite storage implementation for conversation sessions.

Replaces the legacy :class:`ConversationStorage` backend with an embedded
SQLite backend while preserving the exact public API so ``ConversationSession``
and all CLI/RAG callers work unchanged.

Storage layout mirrors the previous document envelope: a ``sessions`` row plus one
row per message in ``messages``. Ordering is pure array position (append +
most-recent-N slice + whole-array replace for context trim), matching the old
document semantics exactly.

Schema version is tracked via ``PRAGMA user_version``.

Each blocking CRUD method has an ``*_async`` twin (e.g.
:meth:`ConversationStorage.save_message_async`) that offloads the blocking
SQLite call to a worker thread via :func:`asyncio.to_thread`, mirroring the
convention used by the vector storage layer (``storage/qdrant.py``). All async
twins delegate to the sync methods, so the two APIs share the exact same
locking and transaction behavior.
"""

from __future__ import annotations

import asyncio
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
        super().__init__(cache_ttl=cfg.connection_cache_ttl)
        # Dedicated reentrant lock for ALL SQLite access on the single
        # shared connection. It is separate from the plain ``Lock`` installed
        # by ``ValidatableService.__init__`` (for its cache bookkeeping) so
        # it cannot be clobbered by the base class and is not shared with
        # cache logic. Reentrancy is required because write methods call the
        # ``conn`` property (which lazy-creates the connection under this
        # same lock) while already holding it — a plain Lock would
        # self-deadlock. Serializing reads too keeps concurrent async twins
        # (running on worker threads via asyncio.to_thread) from hitting
        # sqlite3's shared-connection statement-cache race.
        self._db_lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or lazily create the SQLite connection.

        Uses ``check_same_thread=False`` so calls from any thread share one
        connection (all access is serialized by :attr:`_db_lock`), with WAL
        journaling for concurrent readers. Lazy creation is guarded by
        ``self._db_lock`` with double-checked locking so concurrent async calls
        (executed on ``asyncio.to_thread`` worker threads) cannot race and
        create two connections.

        Returns
        -------
            A live :class:`sqlite3.Connection` to the conversation database.
        """
        if self._conn is None:
            with self._db_lock:
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
            with self._db_lock:
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
        with self._db_lock:
            self.conn.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            self.conn.commit()
        return session_id

    async def create_session_async(self, session_id: str) -> str:
        """Async wrapper over :meth:`create_session`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Unique identifier for the session.

        Returns
        -------
            The session_id of the created session.
        """
        return await asyncio.to_thread(self.create_session, session_id)

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message to a session.

        Args:
            session_id: Session identifier.
            role: Message role (e.g., "user", "assistant", "system").
            content: Message content.
        """
        now = datetime.now(UTC).isoformat()
        timestamp = now
        with self._db_lock:
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

    async def save_message_async(
        self, session_id: str, role: str, content: str
    ) -> None:
        """Async wrapper over :meth:`save_message`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Session identifier.
            role: Message role (e.g., "user", "assistant", "system").
            content: Message content.
        """
        await asyncio.to_thread(self.save_message, session_id, role, content)

    def update_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """Replace all messages in a session.

        Deletes all messages for the session and inserts the provided array at
        sequential positions. Used for context trimming where the message array
        needs to be updated wholesale.

        Args:
            session_id: Session identifier.
            messages: Complete list of message dictionaries to store.
        """
        now = datetime.now(UTC).isoformat()
        with self._db_lock:
            conn = self.conn
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
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

    async def update_messages_async(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Async wrapper over :meth:`update_messages`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Session identifier.
            messages: Complete list of message dictionaries to store.
        """
        await asyncio.to_thread(self.update_messages, session_id, messages)

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
        with self._db_lock:
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
            {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    async def get_history_async(
        self, session_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Async wrapper over :meth:`get_history`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return (most recent N).
                If ``None`` or ``<= 0``, returns all messages in order.

        Returns
        -------
            List of message dictionaries with role, content, and timestamp.
            Returns empty list if session not found or has no messages.
        """
        return await asyncio.to_thread(self.get_history, session_id, limit)

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists in storage.

        Args:
            session_id: Session identifier to check.

        Returns
        -------
            True if session exists, False otherwise.
        """
        with self._db_lock:
            row = self.conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row is not None

    async def session_exists_async(self, session_id: str) -> bool:
        """Async wrapper over :meth:`session_exists`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Session identifier to check.

        Returns
        -------
            True if session exists, False otherwise.
        """
        return await asyncio.to_thread(self.session_exists, session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session.

        Cascades to delete all associated messages.

        Args:
            session_id: Session identifier to delete.

        Returns
        -------
            True if session was deleted, False if session not found.
        """
        with self._db_lock:
            cur = self.conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            self.conn.commit()
            return cur.rowcount > 0

    async def delete_session_async(self, session_id: str) -> bool:
        """Async wrapper over :meth:`delete_session`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            session_id: Session identifier to delete.

        Returns
        -------
            True if session was deleted, False if session not found.
        """
        return await asyncio.to_thread(self.delete_session, session_id)

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
        with self._db_lock:
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

    async def list_sessions_async(self, limit: int = 100) -> list[dict[str, Any]]:
        """Async wrapper over :meth:`list_sessions`.

        Offloads the blocking SQLite call to a worker thread via
        :func:`asyncio.to_thread`.

        Args:
            limit: Maximum number of sessions to return (default: 100).

        Returns
        -------
            List of session metadata dictionaries with session_id,
            created_at, and message_count fields.
        """
        return await asyncio.to_thread(self.list_sessions, limit)

    def close(self) -> None:
        """Close the SQLite connection and release resources."""
        if self._conn is not None:
            with self._db_lock:
                self._conn.commit()
                self._conn.close()
            self._conn = None

    async def close_async(self) -> None:
        """Async wrapper over :meth:`close`.

        Offloads the blocking close to a worker thread via
        :func:`asyncio.to_thread`.
        """
        await asyncio.to_thread(self.close)

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
