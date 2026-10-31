"""SQLite storage for per-document structure trees (structure-aware ingestion).

Stores the document structure captured at ingest time — heading nodes
(parts/chapters/sections/subsections), ``/PageLabels`` ranges and audio
segments — keyed by the exact ``source_file`` string the vector payload uses,
so query time becomes a lookup instead of a regex reconstruction.

The store lives in the SAME SQLite file as the conversation store
(:class:`secondbrain.conversation.storage_sqlite.ConversationStorage`,
``cfg.sqlite_path``) but owns its own tables only:

* ``structure_nodes`` — one row per tree node,
* ``page_labels`` — grouped ``/PageLabels`` runs,
* ``audio_segments`` — audio ASR segment rows,
* ``structure_meta`` — one row per document (capture timestamp + sources).

Hard rules inherited from the change design (``§4 Data model``):

* **Never touch ``PRAGMA user_version``** — the conversation store owns the
  schema version of the shared database file; this store only runs idempotent
  ``CREATE TABLE IF NOT EXISTS`` statements at first connection.
* ``save_structure`` replaces the whole tree for one ``source_file`` inside a
  single transaction (delete + insert), so re-capture is idempotent.
* WAL-compatible defaults with a ``busy_timeout`` of at least 5 s, so the
  structure store coexists with conversation writers on the same file.

Each blocking CRUD method has an ``*_async`` twin (e.g.
:meth:`StructureStore.save_structure_async`) that offloads the blocking SQLite
call to a worker thread via :func:`asyncio.to_thread`, mirroring the
convention used by :class:`ConversationStorage` and the vector storage layer.
All async twins delegate to the sync methods, so the two APIs share the exact
same locking and transaction behavior.

This module is self-contained: it carries the pydantic models
(:class:`StructureNode`, :class:`PageLabelRange`, :class:`AudioSegment`,
:class:`DocumentStructure`) *and* the store, per the pinned shared contract in
the change design (§3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from secondbrain.config import config
from secondbrain.config.resilience import circuit_breaker_config_from_config
from secondbrain.utils.circuit_breaker import CircuitBreakerError
from secondbrain.utils.connections import ValidatableService

__all__ = [
    "AudioSegment",
    "DocumentStructure",
    "PageLabelRange",
    "StructureNode",
    "StructureStore",
]

logger = logging.getLogger(__name__)

StructureKind = Literal["part", "chapter", "section", "subsection", "segment"]

# Sentinel used to order rows whose page_start is NULL after every page-bearing
# row when restoring a tree (SQL has no "NULLS LAST" on older SQLite builds and
# the column is nullable).
_MAX_PAGE_SENTINEL = 2_147_483_647

SCHEMA = """
CREATE TABLE IF NOT EXISTS structure_nodes (
  source_file TEXT NOT NULL, node_id TEXT NOT NULL, parent_id TEXT,
  kind TEXT NOT NULL, level INTEGER NOT NULL, number TEXT, title TEXT NOT NULL,
  page_start INTEGER, page_end INTEGER, t_start REAL, t_end REAL,
  heading_path TEXT NOT NULL,
  PRIMARY KEY (source_file, node_id));
CREATE INDEX IF NOT EXISTS idx_structure_nodes_doc
  ON structure_nodes(source_file, page_start);
CREATE TABLE IF NOT EXISTS page_labels (
  source_file TEXT NOT NULL, page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
  label TEXT NOT NULL, style TEXT, PRIMARY KEY (source_file, page_start));
CREATE TABLE IF NOT EXISTS audio_segments (
  source_file TEXT NOT NULL, seg_id INTEGER NOT NULL, t_start REAL NOT NULL,
  t_end REAL NOT NULL, title TEXT, PRIMARY KEY (source_file, seg_id));
CREATE TABLE IF NOT EXISTS structure_meta (
  source_file TEXT PRIMARY KEY, captured_at TEXT NOT NULL, sources TEXT NOT NULL,
  doc_hash TEXT);
"""


class StructureNode(BaseModel):
    """One node of a document structure tree.

    A node is a heading-derived region of a document (part, chapter, section,
    subsection) or a time-bounded audio segment. ``node_id`` values are
    deterministic — ``"ch05"``, ``"sec05.02"``, ``"partI.1"``, ``"seg03"`` —
    so re-capture produces the same tree identity for the same input.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    parent_id: str | None = None
    kind: StructureKind
    level: int = Field(description="1 = top")
    number: str | None = Field(
        default=None, description='"5", "5.2", "I.1"; None for unnumbered'
    )
    title: str
    page_start: int | None = Field(default=None, description="1-based physical page")
    page_end: int | None = Field(
        default=None, description="inclusive; spans to next sibling boundary"
    )
    t_start: float | None = Field(default=None, description="seconds (audio)")
    t_end: float | None = Field(default=None, description="seconds (audio)")
    heading_path: str = Field(
        default="", description='"Chapter 1 — Installing > 1.2 > 1.2.3"'
    )


class PageLabelRange(BaseModel):
    """One run of consecutive physical pages sharing the same ``/PageLabels`` label."""

    model_config = ConfigDict(extra="forbid")

    page_start: int
    page_end: int
    label: str
    style: str | None = None


class AudioSegment(BaseModel):
    """One ASR segment of an audio document (timestamps in seconds)."""

    model_config = ConfigDict(extra="forbid")

    seg_id: int
    t_start: float
    t_end: float
    title: str | None = None


class DocumentStructure(BaseModel):
    """The captured structure of one document.

    ``source_file`` MUST equal the exact string stored in the qdrant payload
    ``source_file`` (the path as passed to ingest) or lookups will miss.
    """

    model_config = ConfigDict(extra="forbid")

    source_file: str
    nodes: list[StructureNode] = Field(default_factory=list)
    page_labels: list[PageLabelRange] = Field(default_factory=list)
    audio_segments: list[AudioSegment] = Field(default_factory=list)
    sources: dict[str, bool] = Field(
        default_factory=dict,
        description='{"outline":…, "heading_hierarchy":…, "page_labels":…, "audio":…}',
    )
    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class StructureStore(ValidatableService):
    """Embedded SQLite storage for per-document structure trees.

    Mirrors :class:`secondbrain.conversation.storage_sqlite.ConversationStorage`
    (same ``ValidatableService`` base, same lazy single-connection pattern with
    a reentrant lock, same ``*_async`` twins via :func:`asyncio.to_thread`),
    sharing the same SQLite database file (``cfg.sqlite_path``) while owning
    only its own ``structure_*`` tables. It never touches
    ``PRAGMA user_version`` — the conversation store owns that.

    Example:
    --------
        >>> store = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
        >>> store.save_structure(DocumentStructure(source_file="/docs/hcd.pdf"))
        >>> store.has_tree("/docs/hcd.pdf")
        True
        >>> store.delete_structure("/docs/hcd.pdf")
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize structure storage on the shared SQLite database.

        Args:
            db_path: Filesystem path to the SQLite database. If ``None``,
                uses the configured ``cfg.sqlite_path`` (the same file the
                conversation store uses). Tests pass an explicit tmp_path.
        """
        cfg = config()
        path = db_path if db_path is not None else cfg.sqlite_path
        self.db_path: str = path
        self._conn: sqlite3.Connection | None = None
        super().__init__(
            cache_ttl=cfg.connection_cache_ttl,
            circuit_breaker_config=circuit_breaker_config_from_config(cfg),
        )
        # Dedicated reentrant lock for ALL SQLite access on the single shared
        # connection — same rationale as ConversationStorage (lazy connection
        # creation under this lock while already held; serialized access so
        # asyncio.to_thread twins cannot race sqlite3's statement cache).
        self._db_lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or lazily create the SQLite connection.

        Same double-checked-lazy pattern as :class:`ConversationStorage.conn`
        (``check_same_thread=False`` + :attr:`_db_lock`). Runs only idempotent
        ``CREATE TABLE IF NOT EXISTS`` statements and **never** touches
        ``PRAGMA user_version`` (owned by the conversation store).

        Returns
        -------
            A live :class:`sqlite3.Connection` to the shared database.
        """
        if self._conn is None:
            with self._db_lock:
                if self._conn is None:
                    db_path = Path(self.db_path)
                    db_path.parent.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(str(db_path), check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    # busy_timeout FIRST so the WAL switch below (and every
                    # later statement) waits out a concurrent writer instead
                    # of failing with "database is locked".
                    conn.execute("PRAGMA busy_timeout=5000")
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA journal_mode=WAL")
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

    def validate_connection(
        self, force: bool = False, bypass_circuit_breaker: bool = False
    ) -> bool:
        """Validate the SQLite connection through the circuit breaker.

        Routes the cached probe through
        :meth:`ValidatableService.validate_connection_with_circuit_breaker`,
        exactly like :class:`ConversationStorage`.

        Args:
            force: If True, bypass cache and check connection.
            bypass_circuit_breaker: Run the probe without consulting or
                updating the circuit breaker.

        Returns
        -------
            True if the connection is valid, False otherwise.
        """
        try:
            return self.validate_connection_with_circuit_breaker(
                force=force, bypass_circuit_breaker=bypass_circuit_breaker
            )
        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker open for %s; skipping structure-storage probe",
                self.__class__.__name__,
            )
            return False

    async def validate_connection_async(
        self, force: bool = False, bypass_circuit_breaker: bool = False
    ) -> bool:
        """Async wrapper over :meth:`validate_connection`.

        Args:
            force: If True, bypass cache and check connection.
            bypass_circuit_breaker: Run the probe without consulting or
                updating the circuit breaker.

        Returns
        -------
            True if the connection is valid, False otherwise.
        """
        return await asyncio.to_thread(
            self.validate_connection, force, bypass_circuit_breaker
        )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def save_structure(self, structure: DocumentStructure) -> None:
        """Replace the stored tree for ``structure.source_file`` wholesale.

        Deletes every existing row of the four structure tables for
        ``source_file`` and inserts the full new tree inside ONE transaction,
        so re-capture is idempotent: saving the same (or an updated) tree
        twice leaves exactly one consistent tree behind. Rows are written
        with ``INSERT OR REPLACE`` semantics as belt-and-braces against any
        primary-key residue.

        Args:
            structure: The captured document structure. ``structure.source_file``
                is the storage key and MUST equal the qdrant payload
                ``source_file`` string for the document.
        """
        source_file = structure.source_file
        with self._db_lock:
            conn = self.conn
            try:
                conn.execute(
                    "DELETE FROM structure_nodes WHERE source_file = ?",
                    (source_file,),
                )
                conn.execute(
                    "DELETE FROM page_labels WHERE source_file = ?", (source_file,)
                )
                conn.execute(
                    "DELETE FROM audio_segments WHERE source_file = ?", (source_file,)
                )
                conn.execute(
                    "DELETE FROM structure_meta WHERE source_file = ?", (source_file,)
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO structure_nodes ("
                    "source_file, node_id, parent_id, kind, level, number, title,"
                    " page_start, page_end, t_start, t_end, heading_path"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            source_file,
                            node.node_id,
                            node.parent_id,
                            node.kind,
                            node.level,
                            node.number,
                            node.title,
                            node.page_start,
                            node.page_end,
                            node.t_start,
                            node.t_end,
                            node.heading_path,
                        )
                        for node in structure.nodes
                    ],
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO page_labels ("
                    "source_file, page_start, page_end, label, style"
                    ") VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            source_file,
                            label_range.page_start,
                            label_range.page_end,
                            label_range.label,
                            label_range.style,
                        )
                        for label_range in structure.page_labels
                    ],
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO audio_segments ("
                    "source_file, seg_id, t_start, t_end, title"
                    ") VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            source_file,
                            segment.seg_id,
                            segment.t_start,
                            segment.t_end,
                            segment.title,
                        )
                        for segment in structure.audio_segments
                    ],
                )
                conn.execute(
                    "INSERT OR REPLACE INTO structure_meta ("
                    "source_file, captured_at, sources, doc_hash"
                    ") VALUES (?, ?, ?, ?)",
                    (
                        source_file,
                        structure.captured_at,
                        json.dumps(structure.sources, sort_keys=True),
                        None,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def save_structure_async(self, structure: DocumentStructure) -> None:
        """Async wrapper over :meth:`save_structure`.

        The shared persist helper both ingest paths call (design §6): the sync
        path uses :meth:`save_structure` directly on the owner thread, the
        async path awaits this twin. Offloads the blocking SQLite call to a
        worker thread via :func:`asyncio.to_thread`.

        Args:
            structure: The captured document structure to persist.
        """
        await asyncio.to_thread(self.save_structure, structure)

    def delete_structure(self, source_file: str) -> None:
        """Delete the stored tree for *source_file* (no-op when absent).

        Args:
            source_file: The document key whose tree should be removed.
        """
        with self._db_lock:
            conn = self.conn
            conn.execute(
                "DELETE FROM structure_nodes WHERE source_file = ?", (source_file,)
            )
            conn.execute(
                "DELETE FROM page_labels WHERE source_file = ?", (source_file,)
            )
            conn.execute(
                "DELETE FROM audio_segments WHERE source_file = ?", (source_file,)
            )
            conn.execute(
                "DELETE FROM structure_meta WHERE source_file = ?", (source_file,)
            )
            conn.commit()

    async def delete_structure_async(self, source_file: str) -> None:
        """Async wrapper over :meth:`delete_structure`.

        Args:
            source_file: The document key whose tree should be removed.
        """
        await asyncio.to_thread(self.delete_structure, source_file)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def load_tree(self, source_file: str) -> DocumentStructure | None:
        """Load the stored tree for *source_file*, or None when absent.

        Args:
            source_file: The document key (same string as the qdrant payload
                ``source_file``).

        Returns
        -------
            The stored :class:`DocumentStructure`, or ``None`` when no tree
            was ever saved for the document.
        """
        with self._db_lock:
            conn = self.conn
            meta = conn.execute(
                "SELECT captured_at, sources FROM structure_meta WHERE source_file = ?",
                (source_file,),
            ).fetchone()
            if meta is None:
                return None
            node_rows = conn.execute(
                "SELECT node_id, parent_id, kind, level, number, title,"
                " page_start, page_end, t_start, t_end, heading_path"
                " FROM structure_nodes WHERE source_file = ?"
                " ORDER BY COALESCE(page_start, ?), level, rowid",
                (source_file, _MAX_PAGE_SENTINEL),
            ).fetchall()
            label_rows = conn.execute(
                "SELECT page_start, page_end, label, style FROM page_labels"
                " WHERE source_file = ? ORDER BY page_start ASC",
                (source_file,),
            ).fetchall()
            segment_rows = conn.execute(
                "SELECT seg_id, t_start, t_end, title FROM audio_segments"
                " WHERE source_file = ? ORDER BY seg_id ASC",
                (source_file,),
            ).fetchall()

        return DocumentStructure(
            source_file=source_file,
            nodes=[
                StructureNode(
                    node_id=row["node_id"],
                    parent_id=row["parent_id"],
                    kind=row["kind"],
                    level=row["level"],
                    number=row["number"],
                    title=row["title"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    t_start=row["t_start"],
                    t_end=row["t_end"],
                    heading_path=row["heading_path"],
                )
                for row in node_rows
            ],
            page_labels=[
                PageLabelRange(
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    label=row["label"],
                    style=row["style"],
                )
                for row in label_rows
            ],
            audio_segments=[
                AudioSegment(
                    seg_id=row["seg_id"],
                    t_start=row["t_start"],
                    t_end=row["t_end"],
                    title=row["title"],
                )
                for row in segment_rows
            ],
            captured_at=meta["captured_at"],
            sources=_parse_sources(meta["sources"]),
        )

    async def load_tree_async(self, source_file: str) -> DocumentStructure | None:
        """Async wrapper over :meth:`load_tree`.

        Args:
            source_file: The document key (same string as the qdrant payload
                ``source_file``).

        Returns
        -------
            The stored :class:`DocumentStructure`, or ``None`` when absent.
        """
        return await asyncio.to_thread(self.load_tree, source_file)

    def has_tree(self, source_file: str) -> bool:
        """Check whether a tree (any capture) exists for *source_file*.

        Args:
            source_file: The document key (same string as the qdrant payload
                ``source_file``).

        Returns
        -------
            True when a structure was saved for the document, False otherwise.
        """
        with self._db_lock:
            row = self.conn.execute(
                "SELECT 1 FROM structure_meta WHERE source_file = ?", (source_file,)
            ).fetchone()
        return row is not None

    async def has_tree_async(self, source_file: str) -> bool:
        """Async wrapper over :meth:`has_tree`.

        Args:
            source_file: The document key (same string as the qdrant payload
                ``source_file``).

        Returns
        -------
            True when a structure was saved for the document, False otherwise.
        """
        return await asyncio.to_thread(self.has_tree, source_file)

    def sources_with_number(self, number: str) -> list[str]:
        """Return the source files whose stored tree carries *number*.

        Per-source resolution lookup (fix-chat-session-integrity D1): for an
        unscoped numbered chapter/section query ("summarize chapter 15") the
        pipeline asks which sources' trees carry a chapter-or-section node
        with the requested number, instead of ranking whole documents by
        body-chunk count. Matching is exact on the stored ``number`` string
        ("15" never matches "15.2"), and only chapter-shaped kinds count —
        ``chapter``, ``section`` and ``subsection``; ``part`` and ``segment``
        nodes are excluded.

        Args:
            number: The requested chapter or section number, e.g. ``"15"``
                or ``"5.2"``. Whitespace is ignored; an empty string
                returns no sources.

        Returns
        -------
            The distinct ``source_file`` keys (sorted ascending) whose tree
            has at least one matching node. Empty when no stored tree
            carries the number.
        """
        requested = number.strip()
        if not requested:
            return []
        with self._db_lock:
            rows = self.conn.execute(
                "SELECT DISTINCT source_file FROM structure_nodes"
                " WHERE number = ? AND kind IN ('chapter', 'section',"
                " 'subsection') ORDER BY source_file ASC",
                (requested,),
            ).fetchall()
        return [row["source_file"] for row in rows]

    async def sources_with_number_async(self, number: str) -> list[str]:
        """Async wrapper over :meth:`sources_with_number`.

        Args:
            number: The requested chapter or section number, e.g. ``"15"``
                or ``"5.2"``.

        Returns
        -------
            The distinct ``source_file`` keys carrying a node with that
            number, sorted ascending.
        """
        return await asyncio.to_thread(self.sources_with_number, number)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection and release resources."""
        if self._conn is not None:
            with self._db_lock:
                self._conn.commit()
                self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        """Best-effort close when a store is garbage-collected unclosed.

        Tests and ad-hoc scripts construct stores without the context
        manager; an unclosed sqlite3.Connection warns on collection
        ("unclosed database"), and that warning has landed in captured CLI
        output mid-invoke (the flaky test_json_dump_shape). Explicit
        close()/context-manager use remains the norm; this only silences
        the leaked-store path. Never raises: a failed best-effort close is
        dropped (partially-initialized instances, interpreter shutdown).
        """
        with contextlib.suppress(Exception):
            self.close()

    async def close_async(self) -> None:
        """Async wrapper over :meth:`close`.

        Offloads the blocking close to a worker thread via
        :func:`asyncio.to_thread`.
        """
        await asyncio.to_thread(self.close)

    def __enter__(self) -> StructureStore:
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


def _parse_sources(raw: Any) -> dict[str, bool]:
    """Parse the stored ``sources`` JSON, degrading to an empty dict.

    Args:
        raw: The raw ``sources`` column value (a JSON object string).

    Returns
    -------
        The parsed sources mapping, or ``{}`` when unparsable/absent.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except TypeError, ValueError:
        logger.warning("Unparsable structure sources payload %r; ignoring", raw)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): bool(value) for key, value in parsed.items()}
