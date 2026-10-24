"""Tests for Deleter's structure-tree cleanup (structure-aware ingestion).

The design (``add-structure-aware-ingestion`` §6) requires document deletes
to also remove the per-document structure tree persisted at ingest time, and
requires that a broken structure store never fails the delete. These tests
exercise that wiring against a real :class:`StructureStore` on a tmp_path
database, with the vector storage mocked following the existing
``tests/test_management/test_management.py`` fakes.
"""

import logging
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.management import Deleter
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)

SOURCES = ["/docs/report.pdf", "/docs/notes.md", "/docs/slides.pdf"]


@pytest.fixture()
def structure_db(tmp_path):
    """A real structure store on an isolated tmp_path SQLite file."""
    return StructureStore(db_path=str(tmp_path / "structures.db"))


def _save_tree(store: StructureStore, source_file: str) -> None:
    """Persist a minimal one-node tree for *source_file*."""
    store.save_structure(
        DocumentStructure(
            source_file=source_file,
            nodes=[
                StructureNode(
                    node_id="ch01",
                    parent_id=None,
                    kind="chapter",
                    level=1,
                    number="1",
                    title="Introduction",
                    page_start=1,
                    page_end=6,
                    heading_path="Chapter 1 — Introduction",
                )
            ],
            sources={"outline": True},
        )
    )


def _make_deleter(
    structure_db: StructureStore,
    list_source_files: list[str] | Exception | None = None,
    delete_by_source: list[int] | None = None,
    delete_all: int = 0,
) -> tuple[Deleter, MagicMock]:
    """Build a Deleter with a mocked vector store and the real structure db.

    Args:
        structure_db: The real tmp_path structure store to inject.
        list_source_files: Value for ``storage.list_source_files()`` (a list
            or an exception to raise); None leaves the MagicMock default.
        delete_by_source: Side effects for ``delete_by_source``.
        delete_all: Return value for ``delete_all``.

    Returns
    -------
        The deleter and the mocked vector storage for assertions.
    """
    storage = MagicMock()
    storage.validate_connection.return_value = True
    if list_source_files is not None:
        if isinstance(list_source_files, Exception):
            storage.list_source_files.side_effect = list_source_files
        else:
            storage.list_source_files.return_value = list_source_files
    if delete_by_source is not None:
        storage.delete_by_source.side_effect = delete_by_source
    storage.delete_all.return_value = delete_all

    with patch(
        "secondbrain.management.StorageFactory.create_from_config",
        return_value=storage,
    ):
        deleter = Deleter(structure_store=structure_db)
    assert deleter.storage is storage
    return deleter, storage


class TestDeleteBySourceRemovesTree:
    """Tests for --source deletes cleaning up the stored tree."""

    def test_tree_removed_after_successful_delete(
        self, structure_db: StructureStore
    ) -> None:
        """A source delete with deleted points also deletes the tree."""
        _save_tree(structure_db, "/docs/report.pdf")
        deleter, storage = _make_deleter(structure_db, delete_by_source=[5])

        count = deleter.delete(source="/docs/report.pdf")

        assert count == 5
        storage.delete_by_source.assert_called_once_with("/docs/report.pdf")
        assert structure_db.has_tree("/docs/report.pdf") is False

    def test_tree_kept_when_no_points_deleted(
        self, structure_db: StructureStore
    ) -> None:
        """Zero deleted points leaves the stored tree untouched."""
        _save_tree(structure_db, "/docs/report.pdf")
        deleter, _storage = _make_deleter(structure_db, delete_by_source=[0])

        count = deleter.delete(source="/docs/report.pdf")

        assert count == 0
        assert structure_db.has_tree("/docs/report.pdf") is True

    def test_delete_without_tree_is_a_clean_noop(
        self, structure_db: StructureStore
    ) -> None:
        """Deleting a source that never had a tree still succeeds."""
        deleter, storage = _make_deleter(structure_db, delete_by_source=[3])

        assert deleter.delete(source="/docs/other.pdf") == 3
        storage.delete_by_source.assert_called_once_with("/docs/other.pdf")


class TestBulkDeletesRemoveTrees:
    """Tests for --all / --file-type deletes collecting affected keys."""

    def test_delete_all_removes_every_listed_tree(
        self, structure_db: StructureStore
    ) -> None:
        """--all removes the trees of every enumerated source."""
        for source in SOURCES:
            _save_tree(structure_db, source)
        deleter, storage = _make_deleter(
            structure_db, list_source_files=SOURCES, delete_all=100
        )

        count = deleter.delete(all=True)

        assert count == 100
        storage.delete_all.assert_called_once()
        assert all(structure_db.has_tree(source) is False for source in SOURCES)

    def test_delete_all_enumerates_keys_before_deleting_points(
        self, structure_db: StructureStore
    ) -> None:
        """The key snapshot happens before delete_all empties the listing."""
        call_order: list[str] = []
        storage = MagicMock()
        storage.validate_connection.return_value = True
        storage.list_source_files.side_effect = lambda: (
            call_order.append("list") or ["/docs/report.pdf"]
        )
        storage.delete_all.side_effect = lambda: call_order.append("delete_all") or 1
        with patch(
            "secondbrain.management.StorageFactory.create_from_config",
            return_value=storage,
        ):
            deleter = Deleter(structure_store=structure_db)

        deleter.delete(all=True)

        assert call_order == ["list", "delete_all"]

    def test_delete_all_skips_tree_cleanup_when_listing_fails(
        self,
        structure_db: StructureStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failing listing warns but the point delete still succeeds."""
        _save_tree(structure_db, "/docs/report.pdf")
        deleter, storage = _make_deleter(
            structure_db,
            list_source_files=RuntimeError("qdrant down"),
            delete_all=100,
        )

        with caplog.at_level(logging.WARNING, logger="secondbrain.management"):
            count = deleter.delete(all=True)

        assert count == 100
        storage.delete_all.assert_called_once()
        # Tree untouched: the affected keys could not be collected.
        assert structure_db.has_tree("/docs/report.pdf") is True
        assert "Could not enumerate source files" in caplog.text

    def test_delete_by_file_type_removes_matching_trees_only(
        self, structure_db: StructureStore
    ) -> None:
        """--file-type removes the trees of the sources it actually deleted."""
        for source in SOURCES:
            _save_tree(structure_db, source)
        deleter, _storage = _make_deleter(
            structure_db,
            list_source_files=SOURCES,
            delete_by_source=[10, 5],
        )

        count = deleter.delete(file_type="pdf")

        assert count == 15
        assert structure_db.has_tree("/docs/report.pdf") is False
        assert structure_db.has_tree("/docs/slides.pdf") is False
        # The markdown source was not part of the delete.
        assert structure_db.has_tree("/docs/notes.md") is True

    def test_delete_by_file_type_keeps_tree_when_points_stay(
        self, structure_db: StructureStore
    ) -> None:
        """A matched source with zero deleted points keeps its tree."""
        _save_tree(structure_db, "/docs/report.pdf")
        deleter, _storage = _make_deleter(
            structure_db,
            list_source_files=["/docs/report.pdf"],
            delete_by_source=[0],
        )

        assert deleter.delete(file_type="pdf") == 0
        assert structure_db.has_tree("/docs/report.pdf") is True


class TestChunkDeleteKeepsTree:
    """Tests for chunk-scoped deletes leaving the document tree intact."""

    def test_delete_by_chunk_id_does_not_remove_tree(
        self, structure_db: StructureStore
    ) -> None:
        """Removing one chunk keeps the document and its stored tree."""
        _save_tree(structure_db, "/docs/report.pdf")
        deleter, storage = _make_deleter(structure_db)
        storage.delete_by_chunk_id.return_value = 1

        count = deleter.delete(chunk_id="chunk-123")

        assert count == 1
        assert structure_db.has_tree("/docs/report.pdf") is True


class TestBrokenStructureStore:
    """Tests that structure-store failure never fails a delete."""

    def test_unconstructible_store_degrades_to_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A structure store that cannot be built logs a warning, delete wins."""
        storage = MagicMock()
        storage.validate_connection.return_value = True
        storage.delete_by_source.return_value = 5
        with (
            patch(
                "secondbrain.management.StorageFactory.create_from_config",
                return_value=storage,
            ),
            patch(
                "secondbrain.storage.structure_sqlite.StructureStore",
                side_effect=RuntimeError("no sqlite"),
            ),
            caplog.at_level(logging.WARNING, logger="secondbrain.management"),
        ):
            deleter = Deleter()  # no injected store: lazy construction fails

            count = deleter.delete(source="/docs/report.pdf")

        assert count == 5
        storage.delete_by_source.assert_called_once_with("/docs/report.pdf")
        assert "Structure store unavailable" in caplog.text

    def test_failing_tree_delete_never_fails_delete(
        self,
        structure_db: StructureStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A structure-store error during tree removal is swallowed."""
        _save_tree(structure_db, "/docs/report.pdf")
        structure_db.delete_structure = (  # type: ignore[method-assign]
            lambda source: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            )
        )
        deleter, _storage = _make_deleter(structure_db, delete_by_source=[5])

        with caplog.at_level(logging.WARNING, logger="secondbrain.management"):
            count = deleter.delete(source="/docs/report.pdf")

        assert count == 5
        assert "Failed to delete stored structure tree" in caplog.text
