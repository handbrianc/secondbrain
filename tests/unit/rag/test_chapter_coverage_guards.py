"""fix-chapter-coverage guards: ToC span, degenerate map, titles, windows.

Groups:

1. ToC-span guard (task 2.1): dot-leader-dense chapter-shaped node ranges
   contribute no chapter-map entry; the probe caps its page list; a
   storage without ``find_chunks`` leaves the guard fully inactive.
2. Degenerate-map fallback (task 2.2): when the surviving number-keyed map
   covers fewer chapters than the tree's chapter-shaped nodes outside ToC
   spans (number-less survivors included), the empty map sends
   ``_tree_chapter_query`` down the existing legacy seam; a healthy tree
   is untouched, byte-identical to the plain map.
3. Window-end clamp (task 3.2): undershooting tree window ends extend to
   the next chapter's derived start minus one — never shrink, never
   overrun — while healthy ``_CHAPTER_PLAN`` ranges are a clamp identity.
4. Dotted-section title guard (task 3.1): a bare chapter-number line
   followed by a section heading ("1 newline 1.1 Central Management")
   never supplies the chapter's title; a ToC listing or a spaced heading
   wins the slot instead, and the roster prints the chapter title-less
   rather than a section heading.
"""

from __future__ import annotations

from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._structure_mixin import _TOC_PROBE_MAX_PAGES
from secondbrain.storage.structure_sqlite import StructureNode, StructureStore
from tests.unit.rag.test_structure_tree_query import (
    _CANNED_ANSWER,
    _CHAPTER_PLAN,
    _SYNTH,
    _CannedProvider,
    _capture_logs,
    _make_pipeline,
    _release_logs,
    _run_iterative,
    _save_tree,
    _synthetic_chunks,
    _TreeStorage,
)

_GUARD_SRC = "/data/workspace/uploads/guard-shape-synthetic.pdf"


def _node(
    node_id: str,
    *,
    number: str | None,
    title: str,
    pages: tuple[int, int] | None,
    parent_id: str | None = None,
) -> StructureNode:
    start, end = pages if pages is not None else (None, None)
    return StructureNode(
        node_id=node_id,
        parent_id=parent_id,
        kind="chapter",
        level=1,
        number=number,
        title=title,
        page_start=start,
        page_end=end,
        t_start=None,
        t_end=None,
        heading_path=title,
    )


def _prose_chunk(source: str, page: int) -> dict[str, Any]:
    return {
        "chunk_id": f"{source}#p{page}c0",
        "source_file": source,
        "page_number": page,
        "page_pos": 0,
        "chunk_text": f"Narrative prose continues the argument on page {page}.",
        "element_type": "paragraph",
        "chunk_role": "body",
    }


def _guard_chunks(
    source: str,
    *,
    toc_pages: range | None,
) -> list[dict[str, Any]]:
    """Probe fixture: ToC-dense rows on ``toc_pages``, prose everywhere else.

    ToC rows end in a page serial and carry a dot leader (dense under
    :meth:`_dot_leader_page`); prose lines end in a period, so no line
    trips the serial-tail rule.
    """
    chunks: list[dict[str, Any]] = []
    for page in range(1, 42):
        if toc_pages is not None and page in toc_pages:
            rows = "\n".join(
                f"{row} Section heading {row} ......... {10 * row + page}"
                for row in range(1, 11)
            )
            chunks.append({**_prose_chunk(source, page), "chunk_text": rows})
        else:
            chunks.append(_prose_chunk(source, page))
    return chunks


def _toc_guard_nodes(*, numberless_in_toc: bool = False) -> list[StructureNode]:
    """The brief's 2-of-21 shape: 2 numbered ToC-span nodes + 19 body nodes."""
    nodes = [
        _node(
            "toc-ch-1",
            number="1",
            title="Contents part one",
            pages=(3, 8),
        ),
        _node(
            "toc-ch-2",
            number="2",
            title="Contents part two",
            pages=(9, 22),
        ),
    ]
    for i in range(19):
        pages = (3 + i, 4 + i) if numberless_in_toc else (23 + i, 23 + i)
        nodes.append(
            _node(f"body-node-{i}", number=None, title=f"Body block {i}", pages=pages)
        )
    return nodes


class TestToCSpanGuard:
    """Dot-leader-dense chapter nodes never build map entries (task 2.1)."""

    def test_dense_numbered_ranges_are_excluded_and_map_degenerates(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        nodes = _toc_guard_nodes()
        _save_tree(store, _GUARD_SRC, nodes_override=nodes)
        storage = _TreeStorage(_guard_chunks(_GUARD_SRC, toc_pages=range(3, 23)))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        tree = store.load_tree(_GUARD_SRC)
        assert tree is not None

        calls: list[str] = []

        def probe(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append("legacy")
            return []

        capture = _capture_logs(pipeline)
        try:
            guarded = pipeline._guarded_tree_chapter_map(
                tree.nodes, storage, _GUARD_SRC
            )
            assert guarded == ({}, {}), "dense ToC spans must yield no map"
            assert any("Degenerate tree chapter map" in m for m in capture.messages), (
                "the 19 number-less survivors must trigger the degenerate signal"
            )

            # Pipeline level: the empty map reaches the existing legacy seam
            # (same recipe as the duplicate-anthology characterization).
            monkeypatch.setattr(pipeline, "_probe_document_structure", probe)
            _run_iterative(pipeline, "summarize this document", _GUARD_SRC)
        finally:
            _release_logs(capture)

        assert calls == ["legacy"]
        assert pipeline._structure_source is None

    def test_all_dense_nodes_leave_no_degenerate_trace(self, tmp_path: Any) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        nodes = _toc_guard_nodes(numberless_in_toc=True)
        _save_tree(store, _GUARD_SRC, nodes_override=nodes)
        storage = _TreeStorage(_guard_chunks(_GUARD_SRC, toc_pages=range(3, 23)))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        tree = store.load_tree(_GUARD_SRC)
        assert tree is not None

        capture = _capture_logs(pipeline)
        try:
            guarded = pipeline._guarded_tree_chapter_map(
                tree.nodes, storage, _GUARD_SRC
            )
        finally:
            _release_logs(capture)

        # Nothing survived the guard, so the plain empty map returns without
        # the degenerate signal (nothing was kept to be degenerate about).
        assert guarded == ({}, {})
        assert any("Excluding ToC-span node" in m for m in capture.messages)
        assert not any("Degenerate tree chapter map" in m for m in capture.messages)

    def test_partial_map_is_degenerate(self, tmp_path: Any) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        nodes = [
            _node(
                f"ch-{n}",
                number=str(n),
                title=f"Title {n}",
                pages=(2 * n, 2 * n + 1),
            )
            for n in range(1, 6)
        ]
        nodes += [
            _node(f"body-{i}", number=None, title=f"Body {i}", pages=(12 + i, 12 + i))
            for i in range(4)
        ]
        _save_tree(store, _GUARD_SRC, nodes_override=nodes)
        # All-prose storage: no node is ToC-dense, the guard excludes
        # nothing, and the map still covers fewer chapters (5) than the
        # tree carries chapter-shaped nodes (9).
        storage = _TreeStorage(_guard_chunks(_GUARD_SRC, toc_pages=None))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        tree = store.load_tree(_GUARD_SRC)
        assert tree is not None

        capture = _capture_logs(pipeline)
        try:
            guarded = pipeline._guarded_tree_chapter_map(
                tree.nodes, storage, _GUARD_SRC
            )
        finally:
            _release_logs(capture)

        assert guarded == ({}, {})
        assert any("Degenerate tree chapter map" in m for m in capture.messages)

    def test_healthy_tree_with_sentinel_is_untouched(self, tmp_path: Any) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH, drop_page_range_for={2})
        storage = _TreeStorage(_synthetic_chunks(_SYNTH))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        tree = store.load_tree(_SYNTH)
        assert tree is not None

        capture = _capture_logs(pipeline)
        try:
            guarded = pipeline._guarded_tree_chapter_map(tree.nodes, storage, _SYNTH)
        finally:
            _release_logs(capture)

        expected_ranges = dict(_CHAPTER_PLAN)
        expected_ranges[2] = (0, -1)
        assert guarded == RAGPipeline._tree_chapter_map(tree.nodes)
        assert guarded == (
            expected_ranges,
            {ch: f"Title {ch}" for ch in expected_ranges},
        )
        assert not any("Degenerate tree chapter map" in m for m in capture.messages)

    def test_plain_map_builds_all_21_chapters(self) -> None:
        nodes = [
            _node(f"ch-{ch}", number=str(ch), title=f"Title {ch}", pages=plan)
            for ch, plan in _CHAPTER_PLAN.items()
        ]
        assert RAGPipeline._tree_chapter_map(nodes) == (
            dict(_CHAPTER_PLAN),
            {ch: f"Title {ch}" for ch in _CHAPTER_PLAN},
        )

    def test_probe_page_list_is_capped(self, tmp_path: Any) -> None:
        node = _node("ch-1", number="1", title="Unbounded", pages=(1, 10_000))
        recorded: list[list[int]] = []

        class _SpyStorage:
            """Records the page lists the guard probe fetches."""

            def __init__(self, inner: _TreeStorage) -> None:
                self._inner = inner

            def find_chunks(self, **kwargs: Any) -> list[dict[str, Any]]:
                pages = kwargs.get("page_number")
                if isinstance(pages, list):
                    recorded.append(list(pages))
                found: list[dict[str, Any]] = self._inner.find_chunks(**kwargs)
                return found

        storage = _SpyStorage(_TreeStorage(_synthetic_chunks(_SYNTH)))
        pipeline = _make_pipeline(storage, _CannedProvider())
        capture = _capture_logs(pipeline)
        try:
            guarded = pipeline._guarded_tree_chapter_map([node], storage, _SYNTH)
        finally:
            _release_logs(capture)

        assert recorded == [list(range(1, 1 + _TOC_PROBE_MAX_PAGES))]
        # The mis-captured node is admitted (prose pages) with its range
        # intact, and the single-node map stays healthy.
        assert guarded == ({1: (1, 10_000)}, {1: "Unbounded"})

    def test_storage_without_find_chunks_leaves_the_guard_inactive(self) -> None:
        class _LegacyStorage:
            """Pre-find_chunks storage double: the guard cannot probe."""

        nodes = [_node("ch-1", number="1", title="Dense", pages=(3, 8))]
        pipeline = _make_pipeline(_LegacyStorage(), _CannedProvider())
        guarded = pipeline._guarded_tree_chapter_map(
            nodes, _LegacyStorage(), _GUARD_SRC
        )
        assert guarded == ({1: (3, 8)}, {1: "Dense"})


class TestWindowEndClamp:
    """Undershooting window ends extend; nothing shrinks (task 3.2)."""

    def test_clamp_table(self) -> None:
        clamp = RAGPipeline._clamp_tree_window_ends
        # Undershoot extends to the next chapter's start minus one.
        assert clamp({1: (1, 2), 2: (10, 11)}) == {1: (1, 9), 2: (10, 11)}
        # Overlap never shrinks: next start - 1 below the current end.
        assert clamp({1: (1, 12), 2: (10, 11)}) == {1: (1, 12), 2: (10, 11)}
        # Adjacent windows are already exact: no-op.
        assert clamp({1: (1, 9), 2: (10, 11)}) == {1: (1, 9), 2: (10, 11)}
        # Numbering gaps do not matter: the next present key bounds.
        assert clamp({1: (1, 2), 3: (10, 11)}) == {1: (1, 9), 3: (10, 11)}
        # Sentinel ranges stay untouched and derive no boundary.
        assert clamp({1: (1, 2), 2: (0, -1), 3: (10, 20)}) == {
            1: (1, 2),
            2: (0, -1),
            3: (10, 20),
        }
        # A malformed range is never extended itself, but its start still
        # bounds its predecessor.
        assert clamp({1: (1, 2), 2: (5, 3)}) == {1: (1, 4), 2: (5, 3)}
        # Empty map: no-op.
        assert clamp({}) == {}

    def test_chapter_plan_is_clamp_identity(self) -> None:
        assert RAGPipeline._clamp_tree_window_ends(dict(_CHAPTER_PLAN)) == _CHAPTER_PLAN


class TestWindowClampPipeline:
    """The clamped map drives the single-target tree query (task 3.2)."""

    def test_single_target_window_reaches_its_exterior_sections(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(
            store,
            source,
            nodes_override=[
                _node("ch-1", number="1", title="Title 1", pages=(1, 2)),
                _node("ch-2", number="2", title="Title 2", pages=(10, 11)),
            ],
        )
        chunks: list[dict[str, Any]] = []
        pos_by_page: dict[int, int] = {}
        for page in range(1, 12):
            owner = 1 if page < 10 else 2
            pos = pos_by_page.get(page, 0)
            pos_by_page[page] = pos + 1
            chunks.append(
                {
                    "chunk_id": f"{source}#p{page}c{pos}",
                    "source_file": source,
                    "page_number": page,
                    "page_pos": pos,
                    "chunk_text": f"Chapter {owner} material on page {page}.",
                    "element_type": "paragraph",
                    "chunk_role": "body",
                    "node_id": f"ch-{owner}",
                    "chapter_id": str(owner),
                }
            )
        storage = _TreeStorage(chunks)
        pipeline = _make_pipeline(storage, _CannedProvider(), store)

        seen: dict[str, list[int]] = {}

        def _single_recorder(
            chunks_: list[dict[str, Any]],
            chapter_num: int | str,
            chapter_title: str,
            *,
            foreign_titles: list[str] | None = None,
        ) -> str:
            seen[str(chapter_num)] = sorted(c.get("page_number") or 0 for c in chunks_)
            return str(_CANNED_ANSWER)

        monkeypatch.setattr(
            pipeline, "_generate_single_chapter_summary", _single_recorder
        )

        # Chapter 1's node undershoots (pages 1-2) while its sections run
        # to page 9: the clamp extends its window to chapter 2's start - 1.
        _run_iterative(pipeline, "summarize chapter 1", source)
        assert seen.get("1") == list(range(1, 10))
        # Chapter 2's window is untouched.
        _run_iterative(pipeline, "summarize chapter 2", source)
        assert seen.get("2") == [10, 11]
        assert pipeline._structure_source == "tree"


class TestDottedSectionTitleGuard:
    """A dotted section heading never titles its chapter (task 3.1)."""

    @staticmethod
    def _chunk(text: str, page: int = 1) -> dict[str, Any]:
        return {
            "source_file": _GUARD_SRC,
            "page_number": page,
            "chunk_text": text,
            "chunk_role": "heading",
            "element_type": "heading",
        }

    def test_bogus_then_toc_row_yields_the_listing_title(self) -> None:
        pipeline = _make_pipeline(_TreeStorage([]), _CannedProvider())
        chunks = [
            self._chunk("1\n1.1 Central Management"),
            self._chunk("1 Introduction ........ 3", page=3),
            self._chunk("2 Installing Proxmox VE", page=5),
        ]
        entries, ch_good, appendix = pipeline._derive_chapter_numbers(chunks)

        assert entries == [
            (1, _GUARD_SRC, "Introduction"),
            (2, _GUARD_SRC, "Installing Proxmox VE"),
        ]
        assert ch_good == {1, 2}
        assert appendix == []

    def test_bogus_alone_yields_an_empty_title_entry(self) -> None:
        pipeline = _make_pipeline(_TreeStorage([]), _CannedProvider())
        entries, ch_good, appendix = pipeline._derive_chapter_numbers(
            [self._chunk("1\n1.1 Central Management")]
        )

        # The chapter number survives as a title-less placeholder: the
        # section heading never becomes the title, and the header builder
        # renders "Chapter 1" for the empty title.
        assert entries == [(1, _GUARD_SRC, "")]
        assert ch_good == {1}
        assert appendix == []

    def test_toc_row_first_wins_before_the_bogus_capture(self) -> None:
        pipeline = _make_pipeline(_TreeStorage([]), _CannedProvider())
        chunks = [
            self._chunk("1 Introduction ........ 3", page=3),
            self._chunk("1\n1.1 Central Management", page=7),
        ]
        entries, ch_good, _ = pipeline._derive_chapter_numbers(chunks)

        assert entries == [(1, _GUARD_SRC, "Introduction")]
        assert ch_good == {1}

    def test_healthy_spaced_heading_unchanged(self) -> None:
        pipeline = _make_pipeline(_TreeStorage([]), _CannedProvider())
        chunks = [
            self._chunk("2 Installing Proxmox VE"),
            self._chunk("2\n2 Installing Proxmox VE"),
        ]
        entries, ch_good, _ = pipeline._derive_chapter_numbers(chunks)

        assert entries == [(2, _GUARD_SRC, "Installing Proxmox VE")]
        assert ch_good == {2}

    def test_roster_never_prints_the_section_heading_as_title(self) -> None:
        pipeline = _make_pipeline(_TreeStorage([]), _CannedProvider())
        roster = pipeline._derive_chapter_roster(
            [self._chunk("1\n1.1 Central Management")]
        )

        assert "1.1 Central Management" not in roster
        # The chapter survives with a title-less slot ("Unknown" is the
        # roster's pre-existing rendering) and the section heading is still
        # listed as a SECTION of chapter 1.
        assert "[Chapter 1] 1.1 — Unknown" in roster
