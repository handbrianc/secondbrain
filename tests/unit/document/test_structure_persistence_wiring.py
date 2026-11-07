"""Persistence-wiring fixture for captured structure trees (A3).

Reproduces the capture → persist path end-to-end at unit level — a tree
captured by :func:`~secondbrain.document.structure_capture.capture_docling_headings`
(plain docling items, the synthesis path) reaches a real
:class:`~secondbrain.storage.structure_sqlite.StructureStore` through the
sync ingestor's real ``_process_parallel_with_progress`` — and locks the
fix-chapter-evidence-fidelity observability contract: every way a captured
tree can fail to reach the store is logged with the source and its node
count, never silently.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.document.structure_capture import capture_docling_headings
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureStore,
)

pytestmark = pytest.mark.unit


def doc_item(
    text: str,
    label: str = "section_header",
    level: int = 1,
    page: int | None = None,
) -> Any:
    """A docling-shaped text item (string label, prov page list)."""
    prov = [SimpleNamespace(page_no=page)] if page is not None else []
    return SimpleNamespace(text=text, label=label, level=level, prov=prov)


def docling_doc(*items: Any) -> Any:
    """A parsed-docling-document shape: just a ``texts`` list."""
    return SimpleNamespace(texts=list(items))


def captured_tree(file_path: Path) -> DocumentStructure:
    """A tree produced by the real docling heading capture (synthesis path)."""
    part = capture_docling_headings(
        docling_doc(
            doc_item("9. Krippendorff's Turn", label="text", level=0, page=10),
            doc_item("9.1 Knowledge Creation", label="text", level=0, page=11),
        ),
        file_path,
    )
    assert part is not None, "the fabricated docling doc must yield a tree"
    return part


def _run(
    ingestor: DocumentIngestor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any],
    store: StructureStore | None,
) -> tuple[int, int]:
    """Run one file through the real parallel-processing path."""
    file_path = Path(str(result["file_path"]))
    monkeypatch.setattr(
        "secondbrain.document.processor._extract_chunk_and_embed_file",
        lambda *args: result,
    )
    if store is not None:
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
    else:
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: None)
    successful, failed, _reasons, _skipped = ingestor._process_parallel_with_progress(
        [file_path],
        embedding_gen=None,
        storage=None,
        max_workers=1,
        pool="thread",
    )
    return successful, failed


class TestPersistenceWiring:
    """Captured trees reach the store; persistence losses are never silent."""

    def test_captured_tree_reaches_the_store(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        file_path = tmp_path / "book.epub"
        ingestor = DocumentIngestor()
        tree = captured_tree(file_path)
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        try:
            successful, failed = _run(
                ingestor,
                tmp_path,
                monkeypatch,
                {
                    "success": True,
                    "file_path": file_path,
                    "documents": [],
                    "error": None,
                    "skipped": True,
                    "extracted_chunks": 3,
                    "structure": tree,
                },
                store,
            )
            assert (successful, failed) == (1, 0)
            # The captured nodes are in the store for the source.
            assert store.has_tree(str(file_path))
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            assert loaded.nodes == tree.nodes
        finally:
            store.close()

    def test_zero_node_capture_warns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        file_path = tmp_path / "labels-only.pdf"
        ingestor = DocumentIngestor()
        # capture_structure's PDF path can return a tree with zero nodes
        # but page labels; the persist must say so, with the source.
        tree = DocumentStructure(
            source_file=str(file_path),
            nodes=[],
            sources={"page_labels": True},
        )
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        try:
            with caplog.at_level(
                "WARNING", logger="secondbrain.document.ingestor._sync"
            ):
                successful, failed = _run(
                    ingestor,
                    tmp_path,
                    monkeypatch,
                    {
                        "success": True,
                        "file_path": file_path,
                        "documents": [],
                        "error": None,
                        "skipped": True,
                        "structure": tree,
                    },
                    store,
                )
            assert (successful, failed) == (1, 0)  # ingest proceeds regardless
            assert "persisted with 0 nodes" in caplog.text
            assert str(file_path) in caplog.text
        finally:
            store.close()

    def test_failed_persist_warns_with_source_and_node_count(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        file_path = tmp_path / "book.epub"
        ingestor = DocumentIngestor()
        tree = captured_tree(file_path)
        store = StructureStore(db_path=str(tmp_path / "structures.db"))

        def broken_save(structure: DocumentStructure) -> None:
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(store, "save_structure", broken_save)
        try:
            with caplog.at_level(
                "WARNING", logger="secondbrain.document.ingestor._sync"
            ):
                successful, failed = _run(
                    ingestor,
                    tmp_path,
                    monkeypatch,
                    {
                        "success": True,
                        "file_path": file_path,
                        "documents": [],
                        "error": None,
                        "skipped": True,
                        "structure": tree,
                    },
                    store,
                )
            assert (successful, failed) == (1, 0)  # ingest proceeds regardless
            assert "Failed to persist structure tree" in caplog.text
            assert str(file_path) in caplog.text
            assert f"({len(tree.nodes)} nodes)" in caplog.text
        finally:
            store.close()

    def test_store_unavailable_warns_with_source_and_node_count(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        file_path = tmp_path / "book.epub"
        ingestor = DocumentIngestor()
        tree = captured_tree(file_path)
        with caplog.at_level("WARNING", logger="secondbrain.document.ingestor._sync"):
            successful, failed = _run(
                ingestor,
                tmp_path,
                monkeypatch,
                {
                    "success": True,
                    "file_path": file_path,
                    "documents": [],
                    "error": None,
                    "skipped": True,
                    "structure": tree,
                },
                None,
            )
        assert (successful, failed) == (1, 0)  # ingest proceeds regardless
        assert "not persisted" in caplog.text
        assert str(file_path) in caplog.text
        assert f"({len(tree.nodes)} nodes)" in caplog.text
