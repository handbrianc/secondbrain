"""Cross-check: capture-side ToC suppression meets the runtime tree guard.

fix-chat-session-integrity tasks 3.1-3.3: the capture lane suppresses
flattened-ToC ghost headings (D4) and recovers chapter numbers through the
printed-page labels (D5) BEFORE the tree is stored; the rag pipeline's
``_guarded_tree_chapter_map`` (fix-chapter-coverage D2) is the runtime
backstop that drops chapter-shaped nodes whose page range probes
dot-leader dense. This file seeds a tmp-sqlite tree with BOTH passes
applied and asserts the runtime guard is a pass-through for a clean
capture — and that it still fires on a ghost fed to it by hand.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from secondbrain.document import structure_capture as sc
from secondbrain.document.structure_capture import capture_structure
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.storage.structure_sqlite import (
    PageLabelRange,
    StructureNode,
    StructureStore,
)

pytestmark = pytest.mark.unit

# The brief's defect shape, synthesized: a flattened ToC on pages 3-5 whose
# rows docling stamps as section headers, and the real number-less chapters
# the recovery pass numbers through the /PageLabels mapping (printed page P
# sits on physical page P + 10, so printed 153 → physical 163).
_PVE_LABELS = [PageLabelRange(page_start=11, page_end=300, label="1", style="decimal")]

_TOC_TEXT = [
    {"text": "1 Introduction .... 1\n2 Installing Proxmox VE .... 10", "page": 3},
    {"text": "7 Proxmox VE Storage .... 153", "page": 4},
    {"text": "8 Backup and Restore .... 185", "page": 5},
]

_EXPECTED_RANGES = {1: (13, 162), 7: (163, 194), 8: (195, 215)}
_EXPECTED_TITLES = {
    1: "Introduction",
    7: "Proxmox VE Storage",
    8: "Backup and Restore",
}


def _doc_item(text: str, level: int = 1, page: int | None = None) -> SimpleNamespace:
    """A docling-shaped section-header item with a 1-based provenance page."""
    prov = [SimpleNamespace(page_no=page)] if page is not None else []
    return SimpleNamespace(text=text, label="section_header", level=level, prov=prov)


def _pve_docling_doc() -> SimpleNamespace:
    """Ghost rows on the ToC pages plus the real number-less chapters."""
    return SimpleNamespace(
        texts=[
            _doc_item("1 Introduction", page=3),  # ghost (span + row match)
            _doc_item("2 Installing Proxmox VE", page=4),  # ghost
            _doc_item("7 Proxmox VE Storage", page=5),  # ghost
            _doc_item("Introduction", page=13),  # real chapter 1
            _doc_item("Proxmox VE Storage", page=163),  # real chapter 7
            _doc_item("Backup and Restore", page=195),  # real chapter 8
            _doc_item("GNU Free Documentation License", level=2, page=215),
        ]
    )


class _Searcher:
    """Searcher double carrying the fixture storage (search stays empty)."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    """LLM double returning one fixed, plausible, non-empty sentence."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return "The document develops its argument across the recovered chapters."


class _Storage:
    """Vector-storage double with the page-list ``find_chunks`` API.

    Mirrors the live semantics the guard probe relies on: equality on
    ``source_file`` and an exact page-number list, no role filter.
    """

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    def find_chunks(
        self,
        source_file: str | None = None,
        *,
        page_number: int | list[int] | None = None,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        pages: list[int] | None
        if isinstance(page_number, list):
            pages = page_number
        elif page_number is not None:
            pages = [page_number]
        else:
            pages = None
        return [
            dict(chunk)
            for chunk in self._chunks
            if (source_file is None or chunk["source_file"] == source_file)
            and (pages is None or chunk["page_number"] in pages)
        ]


def _probe_chunks(src: str) -> list[dict[str, Any]]:
    """One chunk per page: dot-leader ToC rows on pages 3-5, prose elsewhere.

    The ToC rows end in a page serial and carry a dot leader (dense under
    the guard's ``_dot_leader_page``); the prose lines end in a period, so
    no line trips the serial-tail rule.
    """
    chunks: list[dict[str, Any]] = []
    for page in range(1, 231):
        if page in (3, 4, 5):
            rows = "\n".join(
                f"{row} Section heading {row} ......... {10 * row + page}"
                for row in range(1, 11)
            )
        else:
            rows = f"Narrative prose continues the argument on page {page}."
        chunks.append(
            {
                "chunk_id": f"{src}#p{page}c0",
                "source_file": src,
                "page_number": page,
                "page_pos": 0,
                "chunk_text": rows,
                "element_type": "paragraph",
                "chunk_role": "body",
            }
        )
    return chunks


@pytest.fixture(autouse=True)
def _fresh_toc_evidence_cache() -> Iterator[None]:
    """Keep the ToC-evidence LRU from leaking rows across tests."""
    sc._cached_toc_evidence.cache_clear()
    yield
    sc._cached_toc_evidence.cache_clear()


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """Capture → store → pipeline rig over the pve-shape synthetic PDF."""
    path = tmp_path / "pve.pdf"  # does not exist: outline/labels are faked
    src = str(path)
    monkeypatch.setattr(sc, "capture_pdf_outline", lambda _p: None)
    monkeypatch.setattr(sc, "capture_page_labels", lambda _p: list(_PVE_LABELS))
    monkeypatch.setattr(
        sc, "extract_native_pdf_text", lambda _p: [dict(row) for row in _TOC_TEXT]
    )
    structure = capture_structure(path, docling_doc=_pve_docling_doc(), file_type="pdf")
    assert structure is not None

    store = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
    store.save_structure(structure)
    tree = store.load_tree(src)
    assert tree is not None

    storage = _Storage(_probe_chunks(src))
    pipeline = RAGPipeline(
        searcher=_Searcher(storage),  # type: ignore[arg-type]
        llm_provider=_CannedProvider(),  # type: ignore[arg-type]
        top_k=8,
    )
    pipeline._config.streaming_enabled = False
    pipeline._structure_store = store
    pipeline._structure_store_ready = True

    yield SimpleNamespace(
        src=src,
        structure=structure,
        tree=tree,
        store=store,
        storage=storage,
        pipeline=pipeline,
    )
    store.close()


class TestCaptureMeetsRuntimeGuard:
    """A suppressed, recovered tree sails through the runtime guard."""

    def test_capture_tree_is_clean_and_fully_numbered(self, rig: Any) -> None:
        # 3.1: every ghost the docling pass saw inside the span is gone and
        # recorded; 3.2: the real chapters carry their printed-page numbers.
        assert [
            (node.title, node.number, node.page_start) for node in rig.structure.nodes
        ] == [
            ("Introduction", "1", 13),
            ("Proxmox VE Storage", "7", 163),
            ("Backup and Restore", "8", 195),
            ("GNU Free Documentation License", None, 215),
        ]
        assert not any(
            node.page_start is not None and 3 <= node.page_start <= 5
            for node in rig.structure.nodes
        )
        assert rig.structure.nodes[1].heading_path == ("Chapter 7 — Proxmox VE Storage")
        assert sc._suppressed_entries_of(rig.structure) == [
            {"title": "1 Introduction", "page": 3},
            {"title": "2 Installing Proxmox VE", "page": 4},
            {"title": "7 Proxmox VE Storage", "page": 5},
        ]

    def test_reload_preserves_the_clean_tree(self, rig: Any) -> None:
        tree = rig.store.load_tree(rig.src)
        assert tree is not None
        assert [node.number for node in tree.nodes] == [
            "1",
            "7",
            "8",
            None,
        ]
        assert not any(
            node.page_start is not None and 3 <= node.page_start <= 5
            for node in tree.nodes
        )

    def test_guarded_map_equals_the_plain_map_and_covers_every_chapter(
        self, rig: Any
    ) -> None:
        # The runtime guard is a pass-through on a clean capture: the same
        # full number-keyed map the plain builder yields, with no ToC-span
        # entry anywhere and no degenerate fallback.
        ranges, titles = rig.pipeline._guarded_tree_chapter_map(
            rig.tree.nodes, rig.storage, rig.src
        )
        assert ranges == _EXPECTED_RANGES
        assert titles == _EXPECTED_TITLES
        assert (ranges, titles) == rig.pipeline._tree_chapter_map(rig.tree.nodes)

    def test_guard_still_fires_on_a_fed_back_ghost(self, rig: Any) -> None:
        # Belt and braces: a leftover ToC-span ghost handed to the guard by
        # hand is probed, classified dot-leader dense, and dropped — the
        # guarded map stays full where the plain builder would bail on the
        # ghost's duplicate chapter number.
        ghost = StructureNode(
            node_id="toc-ghost",
            parent_id=None,
            kind="chapter",
            level=1,
            number="7",
            title="Proxmox VE Storage",
            page_start=3,
            page_end=5,
            t_start=None,
            t_end=None,
            heading_path="7 Proxmox VE Storage",
        )
        nodes = [ghost, *rig.tree.nodes]
        ranges, titles = rig.pipeline._guarded_tree_chapter_map(
            nodes, rig.storage, rig.src
        )
        assert ranges == _EXPECTED_RANGES
        assert titles == _EXPECTED_TITLES
        assert rig.pipeline._tree_chapter_map(nodes) == ({}, {})
