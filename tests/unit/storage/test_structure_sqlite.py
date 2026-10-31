"""Unit tests for secondbrain.storage.structure_sqlite (StructureStore)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from secondbrain.storage.structure_sqlite import (
    AudioSegment,
    DocumentStructure,
    PageLabelRange,
    StructureNode,
    StructureStore,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures + factories
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> StructureStore:
    """A StructureStore on an isolated tmp_path database."""
    s = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
    yield s
    s.close()


def chapter_node(**overrides: object) -> StructureNode:
    """A representative chapter node."""
    fields: dict[str, object] = {
        "node_id": "ch05",
        "kind": "chapter",
        "level": 1,
        "number": "5",
        "title": "Installing",
        "page_start": 1,
        "page_end": 12,
        "heading_path": "Chapter 5 — Installing",
    }
    fields.update(overrides)
    return StructureNode(**fields)  # type: ignore[arg-type]


def sample_tree(source_file: str = "/docs/hcd.pdf") -> DocumentStructure:
    """A full tree: two nodes + a page-label run + one audio segment."""
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            chapter_node(),
            StructureNode(
                node_id="sec05.02",
                parent_id="ch05",
                kind="section",
                level=2,
                number="5.2",
                title="Input handling",
                page_start=3,
                page_end=7,
                heading_path="Chapter 5 — Installing > 5.2",
            ),
        ],
        page_labels=[
            PageLabelRange(page_start=1, page_end=2, label="i", style="lower_roman"),
            PageLabelRange(page_start=3, page_end=12, label="1", style="decimal"),
        ],
        audio_segments=[
            AudioSegment(seg_id=0, t_start=0.0, t_end=12.5, title="Intro"),
        ],
        sources={"outline": True, "page_labels": True},
    )


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    """save_structure → load_tree fidelity."""

    def test_roundtrip_full_tree(self, store: StructureStore) -> None:
        tree = sample_tree()
        store.save_structure(tree)
        assert store.has_tree(tree.source_file)

        loaded = store.load_tree(tree.source_file)
        assert loaded is not None
        assert loaded.source_file == tree.source_file
        assert loaded.nodes == tree.nodes
        assert loaded.page_labels == tree.page_labels
        assert loaded.audio_segments == tree.audio_segments
        assert loaded.sources == tree.sources
        assert loaded.captured_at == tree.captured_at

    def test_save_is_idempotent(self, store: StructureStore) -> None:
        tree = sample_tree()
        store.save_structure(tree)
        store.save_structure(tree)
        loaded = store.load_tree(tree.source_file)
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert len(loaded.page_labels) == 2

    def test_resave_replaces_whole_tree(self, store: StructureStore) -> None:
        source_file = "/docs/hcd.pdf"
        store.save_structure(sample_tree(source_file))
        # Re-capture produced a different (smaller) tree: full replace.
        replacement = DocumentStructure(
            source_file=source_file,
            nodes=[chapter_node()],
            sources={"outline": True},
        )
        store.save_structure(replacement)

        loaded = store.load_tree(source_file)
        assert loaded is not None
        assert [n.node_id for n in loaded.nodes] == ["ch05"]
        assert loaded.page_labels == []
        assert loaded.audio_segments == []
        assert loaded.sources == {"outline": True}

    def test_empty_tree_roundtrip(self, store: StructureStore) -> None:
        treeless = DocumentStructure(source_file="/docs/flat.txt")
        store.save_structure(treeless)
        assert store.has_tree("/docs/flat.txt")
        loaded = store.load_tree("/docs/flat.txt")
        assert loaded is not None
        assert loaded.nodes == []

    def test_load_unknown_returns_none(self, store: StructureStore) -> None:
        assert store.load_tree("/docs/never-seen.pdf") is None
        assert store.has_tree("/docs/never-seen.pdf") is False

    def test_delete_removes_tree(self, store: StructureStore) -> None:
        tree = sample_tree()
        store.save_structure(tree)
        store.delete_structure(tree.source_file)
        assert store.has_tree(tree.source_file) is False
        assert store.load_tree(tree.source_file) is None

    def test_delete_unknown_is_noop(self, store: StructureStore) -> None:
        store.delete_structure("/docs/never-seen.pdf")  # must not raise

    def test_multi_document_coexistence(self, store: StructureStore) -> None:
        store.save_structure(sample_tree("/docs/a.pdf"))
        store.save_structure(sample_tree("/docs/b.pdf"))
        assert store.has_tree("/docs/a.pdf")
        assert store.has_tree("/docs/b.pdf")
        store.delete_structure("/docs/a.pdf")
        assert store.has_tree("/docs/a.pdf") is False
        assert store.has_tree("/docs/b.pdf")
        assert store.load_tree("/docs/b.pdf") is not None


# ---------------------------------------------------------------------------
# Per-source number lookup (fix-chat-session-integrity task 2.1)
# ---------------------------------------------------------------------------


def _numbered_tree(source_file: str, nodes: list[StructureNode]) -> DocumentStructure:
    """A tree carrying exactly the given nodes (metadata sources only)."""
    return DocumentStructure(
        source_file=source_file,
        nodes=nodes,
        sources={"outline": True},
    )


class TestSourcesWithNumber:
    """sources_with_number: which stored trees carry a chapter/section number."""

    @staticmethod
    def _seed(store: StructureStore) -> None:
        """Four documents: collision on 15, unique 5.2/3.1, noise kinds."""
        store.save_structure(
            _numbered_tree(
                "/docs/a.pdf",
                [
                    chapter_node(node_id="chA5", number="5", page_start=1, page_end=9),
                    StructureNode(
                        node_id="secA5.02",
                        parent_id="chA5",
                        kind="section",
                        level=2,
                        number="5.2",
                        title="Input handling",
                        page_start=3,
                        page_end=7,
                        heading_path="Chapter 5 — Installing > 5.2",
                    ),
                    chapter_node(
                        node_id="chA15", number="15", page_start=10, page_end=20
                    ),
                    chapter_node(
                        node_id="partA2",
                        kind="part",
                        number="II",
                        title="Part II",
                        page_start=21,
                        page_end=30,
                    ),
                ],
            )
        )
        store.save_structure(
            _numbered_tree(
                "/docs/b.pdf",
                [
                    chapter_node(
                        node_id="chB15", number="15", page_start=5, page_end=8
                    ),
                ],
            )
        )
        store.save_structure(
            _numbered_tree(
                "/docs/c.pdf",
                [
                    chapter_node(node_id="chC3", number="3", page_start=1, page_end=6),
                    StructureNode(
                        node_id="subC3.01",
                        parent_id="chC3",
                        kind="subsection",
                        level=3,
                        number="3.1",
                        title="Setup",
                        page_start=2,
                        page_end=4,
                        heading_path="Chapter 3 — Setup > 3.1",
                    ),
                ],
            )
        )
        # A treeless capture (metadata only, no nodes) contributes nothing.
        store.save_structure(_numbered_tree("/docs/d.pdf", []))

    def test_colliding_number_lists_every_carrying_source(
        self, store: StructureStore
    ) -> None:
        self._seed(store)
        assert store.sources_with_number("15") == ["/docs/a.pdf", "/docs/b.pdf"]

    def test_dotted_section_number_scopes_to_its_source(
        self, store: StructureStore
    ) -> None:
        self._seed(store)
        assert store.sources_with_number("5.2") == ["/docs/a.pdf"]
        assert store.sources_with_number("3.1") == ["/docs/c.pdf"]

    def test_exact_match_never_prefix_matches(self, store: StructureStore) -> None:
        self._seed(store)
        # "5" matches chapter 5 only — never the "5.2" section.
        assert store.sources_with_number("5") == ["/docs/a.pdf"]

    def test_unknown_number_returns_empty(self, store: StructureStore) -> None:
        self._seed(store)
        assert store.sources_with_number("9") == []

    def test_blank_number_returns_empty(self, store: StructureStore) -> None:
        self._seed(store)
        assert store.sources_with_number("") == []
        assert store.sources_with_number("   ") == []

    def test_whitespace_is_normalized(self, store: StructureStore) -> None:
        self._seed(store)
        assert store.sources_with_number(" 15 ") == [
            "/docs/a.pdf",
            "/docs/b.pdf",
        ]

    def test_only_chapter_shaped_kinds_count(self, store: StructureStore) -> None:
        self._seed(store)
        # The "part" node carries number II but is not chapter/section shaped.
        assert store.sources_with_number("II") == []

    def test_delete_removes_the_source_from_the_lookup(
        self, store: StructureStore
    ) -> None:
        self._seed(store)
        store.delete_structure("/docs/b.pdf")
        assert store.sources_with_number("15") == ["/docs/a.pdf"]

    def test_resave_replaces_the_carrying_set(self, store: StructureStore) -> None:
        self._seed(store)
        # Re-capture of a.pdf drops chapter 15: the collision collapses.
        store.save_structure(
            _numbered_tree(
                "/docs/a.pdf",
                [chapter_node(node_id="chA5", number="5", page_start=1, page_end=9)],
            )
        )
        assert store.sources_with_number("15") == ["/docs/b.pdf"]

    def test_empty_store_returns_empty(self, tmp_path: Path) -> None:
        fresh = StructureStore(db_path=str(tmp_path / "fresh.db"))
        try:
            assert fresh.sources_with_number("15") == []
        finally:
            fresh.close()

    async def test_async_twin_mirrors_sync(self, store: StructureStore) -> None:
        self._seed(store)
        assert await store.sources_with_number_async("15") == [
            "/docs/a.pdf",
            "/docs/b.pdf",
        ]
        assert await store.sources_with_number_async("9") == []


# ---------------------------------------------------------------------------
# Schema rules
# ---------------------------------------------------------------------------


class TestSchemaContract:
    """The store owns only its own tables and never touches user_version."""

    def test_creates_expected_tables_and_index(self, tmp_path: Path) -> None:
        db_path = tmp_path / "secondbrain.db"
        store = StructureStore(db_path=str(db_path))
        try:
            conn = store.conn
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
                )
            }
            assert {
                "structure_nodes",
                "page_labels",
                "audio_segments",
                "structure_meta",
                "idx_structure_nodes_doc",
            } <= names
        finally:
            store.close()

    def test_user_version_untouched_when_preexisting(self, tmp_path: Path) -> None:
        # The conversation store owns PRAGMA user_version (7 here); the
        # structure store must never touch it (design §4 hard rule).
        db_path = tmp_path / "secondbrain.db"
        owner = sqlite3.connect(str(db_path))
        owner.execute("PRAGMA user_version=7")
        owner.commit()
        owner.close()

        store = StructureStore(db_path=str(db_path))
        try:
            store.save_structure(sample_tree())
            assert store.has_tree("/docs/hcd.pdf")
        finally:
            store.close()

        check = sqlite3.connect(str(db_path))
        try:
            assert check.execute("PRAGMA user_version").fetchone()[0] == 7
        finally:
            check.close()

    def test_user_version_stays_zero_on_fresh_db(self, store: StructureStore) -> None:
        store.save_structure(sample_tree())
        row = store.conn.execute("PRAGMA user_version").fetchone()
        assert row[0] == 0

    def test_busy_timeout_at_least_five_seconds(self, store: StructureStore) -> None:
        row = store.conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] >= 5000


# ---------------------------------------------------------------------------
# Async twins
# ---------------------------------------------------------------------------


class TestAsyncTwins:
    """The *_async wrappers mirror the sync CRUD behavior."""

    async def test_save_load_has_delete_async(self, tmp_path: Path) -> None:
        store = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
        try:
            tree = sample_tree("/docs/async.pdf")
            await store.save_structure_async(tree)
            assert await store.has_tree_async("/docs/async.pdf") is True
            loaded = await store.load_tree_async("/docs/async.pdf")
            assert loaded is not None
            assert loaded.nodes == tree.nodes
            await store.delete_structure_async("/docs/async.pdf")
            assert await store.has_tree_async("/docs/async.pdf") is False
            assert await store.load_tree_async("/docs/async.pdf") is None
        finally:
            await store.close_async()

    async def test_validate_connection_async(self, store: StructureStore) -> None:
        assert await store.validate_connection_async(
            force=True, bypass_circuit_breaker=True
        )


# ---------------------------------------------------------------------------
# Validation + lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """validate_connection and context-manager behavior."""

    def test_validate_connection_true(self, store: StructureStore) -> None:
        assert store.validate_connection(force=True, bypass_circuit_breaker=True)

    def test_validate_connection_false_for_unwritable_path(
        self, tmp_path: Path
    ) -> None:
        # A directory cannot be opened as a SQLite database file.
        blocker = tmp_path / "not-a-db"
        blocker.mkdir()
        store = StructureStore(db_path=str(blocker))
        assert (
            store.validate_connection(force=True, bypass_circuit_breaker=True) is False
        )

    def test_context_manager_closes(self, tmp_path: Path) -> None:
        with StructureStore(db_path=str(tmp_path / "secondbrain.db")) as store:
            store.save_structure(sample_tree())
            assert store.has_tree("/docs/hcd.pdf")
        assert store._conn is None
