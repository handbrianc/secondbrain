"""Unit tests for secondbrain.document.structure_capture (lane 1a)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from secondbrain.document import structure_capture as sc
from secondbrain.document.structure_capture import (
    TocListing,
    _build_nodes_from_headings,
    _group_label_runs,
    _label_style,
    _outline_items_from_bookmarks,
    _parse_numbering,
    capture_docling_headings,
    capture_page_labels,
    capture_pdf_outline,
    capture_structure,
    merge_structures,
    parse_toc_rows,
    recover_chapter_numbers,
)
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    PageLabelRange,
    StructureStore,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Factories (fabricated shapes — no docling / pypdfium2 needed)
# ---------------------------------------------------------------------------


def bookmark(level_1based: int, title: str, page_1based: int | None) -> Any:
    """A pypdfium2-v5-shaped bookmark (0-based level, dest page index)."""

    def get_dest() -> Any:
        if page_1based is None:
            return None
        return SimpleNamespace(get_index=lambda: page_1based - 1)

    return SimpleNamespace(
        level=level_1based - 1,
        get_title=lambda: title,
        get_dest=get_dest,
    )


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


def headings_part(
    entries: Sequence[tuple[int, str, int | None]],
    source_file: str = "/docs/book.pdf",
    allow_parts: bool = True,
    final_page: int | None = None,
) -> DocumentStructure:
    """Build a part through the real heading→node pipeline."""
    nodes = _build_nodes_from_headings(
        list(entries),
        source_file=source_file,
        allow_parts=allow_parts,
        final_page=final_page,
    )
    return DocumentStructure(
        source_file=source_file,
        nodes=nodes,
        sources={"outline": allow_parts},
    )


# ---------------------------------------------------------------------------
# Numbering parser
# ---------------------------------------------------------------------------


class TestParseNumbering:
    """_parse_numbering recognizes the design §5 numbering shapes."""

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Chapter 5 — Installing", ("5", "Installing")),
            ("chapter 5: Installing", ("5", "Installing")),
            ("CHAPTER IV — Results", ("IV", "Results")),
            ("5.2 Input Handling", ("5.2", "Input Handling")),
            ("05.02 Input", ("5.2", "Input")),
            ("I.1 Foundations", ("I.1", "Foundations")),
            ("5 Introduction", ("5", "Introduction")),
            ("IV Results", ("IV", "Results")),
            ("Chapter 5", ("5", "Chapter 5")),
            ("5.2", ("5.2", "5.2")),
        ],
    )
    def test_numbered_shapes(
        self, title: str, expected: tuple[str | None, str]
    ) -> None:
        assert _parse_numbering(title) == expected

    @pytest.mark.parametrize(
        "title",
        [
            "Introduction",
            "1984",  # a year is a title, never a number
            "A Tale of Two Cities",  # single-char roman lookalike
            "I",
        ],
    )
    def test_unnumbered_titles(self, title: str) -> None:
        assert _parse_numbering(title) == (None, title)


# ---------------------------------------------------------------------------
# Node-id scheme + tree construction
# ---------------------------------------------------------------------------


class TestNodeIdScheme:
    """Deterministic ids per design §3 ("ch05", "sec05.02", "partI.1")."""

    def test_chapter_id_ch05(self) -> None:
        part = headings_part([(1, "Chapter 5 — Installing", 1)])
        assert part.nodes[0].node_id == "ch05"
        assert part.nodes[0].kind == "chapter"
        assert part.nodes[0].heading_path == "Chapter 5 — Installing"

    def test_section_id_sec05_02(self) -> None:
        part = headings_part(
            [(1, "Chapter 5 — Installing", 1), (2, "5.2 Input Handling", 3)]
        )
        chapter, section = part.nodes
        assert chapter.node_id == "ch05"
        assert section.node_id == "sec05.02"
        assert section.parent_id == "ch05"
        assert section.kind == "section"
        assert section.heading_path == "Chapter 5 — Installing > 5.2"

    def test_roman_component_id_sec_i_01(self) -> None:
        part = headings_part(
            [(1, "Chapter 5 — Installing", 1), (2, "I.1 Foundations", 3)]
        )
        assert part.nodes[1].node_id == "secI.01"

    def test_part_by_title_scopes_chapter_ids(self) -> None:
        part = headings_part(
            [
                (1, "Part I — Basics", 1),
                (2, "Chapter 1 — Installing", 2),
                (2, "Chapter 2 — Configuring", 9),
            ]
        )
        part_node, ch1, ch2 = part.nodes
        assert part_node.node_id == "partI"
        assert part_node.kind == "part"
        assert ch1.node_id == "partI.1"
        assert ch2.node_id == "partI.2"
        assert ch1.kind == "chapter" and ch2.kind == "chapter"
        assert ch1.parent_id == "partI"
        assert ch1.heading_path == "Part I > Chapter 1 — Installing"

    def test_part_by_chapter_restart(self) -> None:
        # Anthology signature: level-1 root whose first child restarts
        # chapter numbering at "1".
        part = headings_part(
            [
                (1, "Anthology", 1),
                (2, "Chapter 1 — Alpha", 2),
                (2, "Chapter 2 — Beta", 9),
            ]
        )
        root, ch1, ch2 = part.nodes
        assert root.kind == "part"
        assert root.node_id == "part-anthology"
        assert ch1.node_id == "part-anthology.1"
        assert ch2.node_id == "part-anthology.2"

    def test_unnumbered_slug_ids(self) -> None:
        part = headings_part([(1, "Installing the System", 1), (2, "Overview", 2)])
        chapter, section = part.nodes
        assert chapter.node_id == "ch-installing-the-system"
        assert section.node_id == "sec-overview"

    def test_page_ends_follow_tree_order(self) -> None:
        part = headings_part(
            [
                (1, "Chapter 1 — A", 1),
                (2, "1.1 X", 2),
                (2, "1.2 Y", 4),
                (1, "Chapter 2 — B", 6),
            ],
            final_page=10,
        )
        ch1, s11, s12, ch2 = part.nodes
        assert ch1.page_end == 5
        assert s11.page_end == 3
        assert s12.page_end == 5
        assert ch2.page_end == 10  # last node ends at the final page

    def test_same_page_openers_stay_nested(self) -> None:
        part = headings_part(
            [
                (1, "Chapter 1 — A", 3),
                (2, "1.1 X", 3),
                (1, "Chapter 2 — B", 5),
            ],
            final_page=6,
        )
        ch1, s11, ch2 = part.nodes
        assert ch1.page_end == 4
        assert s11.page_end == 4
        assert s11.page_start == 3  # never ends before it starts
        assert ch2.page_end == 6


class TestOutlineItemsFromBookmarks:
    """_outline_items_from_bookmarks normalizes the pypdfium2 v5 shapes."""

    def test_converts_zero_based_level_and_page(self) -> None:
        items = _outline_items_from_bookmarks(
            [
                bookmark(1, "Chapter 1", 4),
                bookmark(2, "1.1 X", 5),
            ]
        )
        assert items == [(1, "Chapter 1", 4), (2, "1.1 X", 5)]

    def test_skips_destless_bookmarks(self) -> None:
        items = _outline_items_from_bookmarks(
            [bookmark(1, "No destination", None), bookmark(1, "Real", 2)]
        )
        assert items == [(1, "Real", 2)]


# ---------------------------------------------------------------------------
# docling heading capture
# ---------------------------------------------------------------------------


class TestCaptureDoclingHeadings:
    """capture_docling_headings maps SectionHeaderItems to a node tree."""

    def test_level_mapping_and_ids(self, tmp_path: Any) -> None:
        doc = docling_doc(
            doc_item("Body paragraph", label="text", level=0, page=1),
            doc_item("Introduction", level=1, page=2),
            doc_item("5.2 Input Handling", level=2, page=4),
            doc_item("5.2.3 Details", level=3, page=5),
        )
        part = capture_docling_headings(doc, tmp_path / "book.pdf")
        assert part is not None
        assert part.source_file == str(tmp_path / "book.pdf")
        assert part.sources == {"heading_hierarchy": True}
        chapter, section, subsection = part.nodes
        assert chapter.node_id == "ch-introduction"
        assert chapter.kind == "chapter"
        assert section.node_id == "sec05.02"
        assert section.kind == "section"
        assert section.parent_id == chapter.node_id
        assert subsection.node_id == "sec05.02.03"
        assert subsection.kind == "subsection"
        assert subsection.parent_id == section.node_id
        assert subsection.heading_path == "Introduction > 5.2 > 5.2.3"

    def test_windowed_documents_concatenate(self, tmp_path: Any) -> None:
        window_a = docling_doc(doc_item("Chapter 1 — A", level=1, page=1))
        window_b = docling_doc(doc_item("Chapter 2 — B", level=1, page=6))
        part = capture_docling_headings([window_a, window_b], tmp_path / "w.pdf")
        assert part is not None
        ch1, ch2 = part.nodes
        assert ch1.node_id == "ch01" and ch2.node_id == "ch02"
        assert ch1.page_end == 5  # next chapter starts on page 6
        assert ch2.page_end == 6  # last node ends at the last known page

    def test_no_headers_returns_none(self, tmp_path: Any) -> None:
        doc = docling_doc(doc_item("Just prose", label="text", level=0, page=1))
        assert capture_docling_headings(doc, tmp_path / "book.pdf") is None

    def test_pageless_headers_return_none(self, tmp_path: Any) -> None:
        doc = docling_doc(doc_item("Floating header", level=1, page=None))
        assert capture_docling_headings(doc, tmp_path / "book.pdf") is None

    def test_never_raises_on_hostile_items(self, tmp_path: Any) -> None:
        doc = docling_doc(
            SimpleNamespace(text="ok", label="section_header", level=1, prov=[]),
            SimpleNamespace(text="page is a string", label="section_header", level=1),
        )
        part = capture_docling_headings(doc, tmp_path / "book.pdf")
        assert part is None or part.source_file == str(tmp_path / "book.pdf")


# ---------------------------------------------------------------------------
# Heading plausibility gate (fix-chunk-heading-context, tasks 2.1/2.2)
# ---------------------------------------------------------------------------


class TestCaptureDoclingHeadingGate:
    """Implausible docling headings create no tree nodes (design D1).

    The gate only decides which ``section_header`` items are treated as
    headings: outline capture stays ungated and no text item is altered,
    dropped, or reordered.
    """

    def test_run_in_label_creates_no_node(self, tmp_path: Any) -> None:
        doc = docling_doc(
            doc_item("Restart chrony:", level=1, page=2),
            doc_item("Chapter 1 — Timekeeping", level=1, page=3),
        )
        part = capture_docling_headings(doc, tmp_path / "book.pdf")
        assert part is not None
        # The chapter title is normalized (number parsed out); the run-in
        # label must appear nowhere in the tree.
        assert [n.title for n in part.nodes] == ["Timekeeping"]
        assert [n.heading_path for n in part.nodes] == ["Chapter 1 — Timekeeping"]

    def test_numbered_heading_passes_the_gate(self, tmp_path: Any) -> None:
        doc = docling_doc(
            doc_item("Restart chrony:", level=1, page=2),
            doc_item("19.2 pveperf", level=2, page=4),
        )
        part = capture_docling_headings(doc, tmp_path / "book.pdf")
        assert part is not None
        (section,) = part.nodes
        assert (section.number, section.title) == ("19.2", "pveperf")

    def test_short_all_caps_run_in_heading_stays_a_node(self, tmp_path: Any) -> None:
        # Spec scenario: a short, punctuation-free run-in heading is real.
        doc = docling_doc(doc_item("GENERAL BTRFS ADVANTAGES", level=2, page=7))
        part = capture_docling_headings(doc, tmp_path / "book.pdf")
        assert part is not None
        assert [n.title for n in part.nodes] == ["GENERAL BTRFS ADVANTAGES"]

    def test_only_implausible_headers_yield_no_part(self, tmp_path: Any) -> None:
        doc = docling_doc(
            doc_item("Restart chrony:", level=1, page=2),
            doc_item("pvesubscription - Subscription Management", level=1, page=3),
        )
        assert capture_docling_headings(doc, tmp_path / "book.pdf") is None

    def test_text_items_are_never_touched(self, tmp_path: Any) -> None:
        # Gating is heading selection only: the parsed items leave capture
        # exactly as they entered (spec: never altered, reordered, dropped).
        items = [
            doc_item("Restart chrony:", level=1, page=2),
            doc_item("Chapter 1 — Timekeeping", level=1, page=3),
        ]
        part = capture_docling_headings(docling_doc(*items), tmp_path / "book.pdf")
        assert part is not None
        assert [i.text for i in items] == [
            "Restart chrony:",
            "Chapter 1 — Timekeeping",
        ]

    def test_outline_derived_node_is_never_gated(self, tmp_path: Any) -> None:
        # Spec scenario: outline (bookmark) evidence is authoritative — an
        # entry whose title would fail the plausibility test still becomes a
        # node, because the gate lives only in capture_docling_headings.
        try:
            from reportlab.pdfgen import canvas as pdf_canvas
        except ImportError:  # pragma: no cover - env without reportlab
            pytest.skip("reportlab is not installed")

        pdf_path = tmp_path / "runin_outline.pdf"
        c = pdf_canvas.Canvas(str(pdf_path))
        c.bookmarkPage("runin")
        c.addOutlineEntry("Restart chrony:", "runin", level=0, closed=False)
        c.drawString(72, 750, "Restart chrony:")
        c.showPage()
        c.save()

        part = capture_pdf_outline(pdf_path)
        assert [n.title for n in part.nodes] == ["Restart chrony:"]


# ---------------------------------------------------------------------------
# Page labels
# ---------------------------------------------------------------------------


class TestPageLabels:
    """_label_style / _group_label_runs behavior."""

    @pytest.mark.parametrize(
        ("label", "style"),
        [
            ("12", "decimal"),
            ("iv", "lower_roman"),
            ("IX", "upper_roman"),
            ("x", "lower_roman"),  # "x" IS roman (ten); roman wins over alpha
            ("y", "lower_alpha"),
            ("Z", "upper_alpha"),
            ("12a", None),
            ("cover", None),
            ("", None),
        ],
    )
    def test_label_style(self, label: str, style: str | None) -> None:
        assert _label_style(label) == style

    def test_groups_equal_consecutive_labels(self) -> None:
        runs = _group_label_runs(["i", "i", "1", "1", "1", "A"])
        assert [(r.page_start, r.page_end, r.label, r.style) for r in runs] == [
            (1, 2, "i", "lower_roman"),
            (3, 5, "1", "decimal"),
            (6, 6, "A", "upper_alpha"),
        ]

    def test_empty_labels_are_skipped(self) -> None:
        assert _group_label_runs(["", "y", "", ""]) == [
            PageLabelRange(page_start=2, page_end=2, label="y", style="lower_alpha")
        ]

    def test_no_labels_yields_no_rows(self) -> None:
        assert _group_label_runs([]) == []
        assert _group_label_runs(["", "", ""]) == []


# ---------------------------------------------------------------------------
# Merge semantics
# ---------------------------------------------------------------------------


class TestMergeStructures:
    """merge_structures: outline wins, docling fills, ids stay deterministic."""

    def test_outline_wins_on_same_page_and_title(self) -> None:
        outline = headings_part([(1, "Chapter 5 — Installing", 3)], final_page=10)
        docling = capture_docling_headings(
            docling_doc(doc_item("Chapter 5 — Installing", level=1, page=3)),
            Path(outline.source_file),
        )
        assert docling is not None
        merged = merge_structures(outline, docling)
        assert [n.node_id for n in merged.nodes] == ["ch05"]
        assert merged.sources["outline"] is True
        assert merged.sources["heading_hierarchy"] is True

    def test_docling_section_attaches_under_outline_chapter(self) -> None:
        outline = headings_part([(1, "Chapter 5 — Installing", 3)], final_page=10)
        docling = capture_docling_headings(
            docling_doc(doc_item("5.2 Input Handling", level=2, page=5)),
            Path(outline.source_file),
        )
        assert docling is not None
        merged = merge_structures(outline, docling)
        chapter, section = merged.nodes
        assert chapter.node_id == "ch05"
        assert section.parent_id == "ch05"
        assert section.kind == "section"  # level 2 under a level-1 chapter
        assert section.heading_path == "Chapter 5 — Installing > 5.2"
        # Page ends re-derived from merged tree order (nothing follows).
        assert chapter.page_end == 10
        assert section.page_end == 10

    def test_docling_nests_under_deepest_outline_container(self) -> None:
        outline = headings_part(
            [
                (1, "Chapter 5 — Installing", 3),
                (2, "5.1 Setup", 4),
            ],
            final_page=10,
        )
        docling = capture_docling_headings(
            docling_doc(doc_item("5.2 Input Handling", level=2, page=5)),
            Path(outline.source_file),
        )
        assert docling is not None
        merged = merge_structures(outline, docling)
        chapter, section, docling_section = merged.nodes
        assert docling_section.parent_id == section.node_id  # 5.1 contains p.5
        # Re-based so a child is never at or above its parent's level.
        assert docling_section.level == 3
        assert docling_section.kind == "subsection"
        assert docling_section.heading_path == "Chapter 5 — Installing > 5.1 > 5.2"
        assert chapter.node_id == "ch05"

    def test_docling_only_forest_stands_alone(self) -> None:
        docling = capture_docling_headings(
            docling_doc(
                doc_item("Chapter 1 — A", level=1, page=2),
                doc_item("1.1 X", level=2, page=4),
            ),
            Path("/docs/solo.epub"),
        )
        assert docling is not None
        merged = merge_structures(docling)
        chapter, section = merged.nodes
        assert chapter.node_id == "ch01"
        assert section.parent_id == "ch01"
        assert section.page_end == chapter.page_end

    def test_colliding_docling_id_is_deterministically_suffixed(self) -> None:
        outline = headings_part([(1, "Chapter 5 — Installing", 3)], final_page=10)
        docling = capture_docling_headings(
            docling_doc(doc_item("Chapter 5 — Configuring", level=1, page=8)),
            Path(outline.source_file),
        )
        assert docling is not None
        # Different page AND title → not a duplicate → id must disambiguate.
        merged = merge_structures(outline, docling)
        ids = sorted(n.node_id for n in merged.nodes)
        assert ids == ["ch05", "ch05-2"]

    def test_none_parts_yield_empty_structure(self) -> None:
        merged = merge_structures(None, None)
        assert merged.nodes == []
        assert merged.source_file == ""

    def test_windows_of_docling_parts_merge_in_order(self) -> None:
        part_a = capture_docling_headings(
            docling_doc(doc_item("Chapter 1 — A", level=1, page=1)),
            Path("/docs/win.pdf"),
        )
        part_b = capture_docling_headings(
            docling_doc(doc_item("Chapter 2 — B", level=1, page=201)),
            Path("/docs/win.pdf"),
        )
        assert part_a is not None and part_b is not None
        merged = merge_structures(part_a, part_b)
        assert [n.node_id for n in merged.nodes] == ["ch01", "ch02"]
        assert merged.nodes[0].page_end == 200
        assert merged.nodes[1].page_end == 201


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestCaptureStructureDispatcher:
    """capture_structure routes by file type and never raises."""

    def test_pdf_with_docling_part_merges_despite_failed_outline(
        self, tmp_path: Any
    ) -> None:
        path = tmp_path / "ghost.pdf"  # does not exist: outline capture fails
        docling = docling_doc(doc_item("Introduction", level=1, page=2))
        structure = capture_structure(path, docling_doc=docling, file_type="pdf")
        assert structure is not None
        assert structure.source_file == str(path)
        assert [n.node_id for n in structure.nodes] == ["ch-introduction"]
        assert structure.sources["outline"] is False
        assert structure.sources["heading_hierarchy"] is True

    def test_non_pdf_without_docling_is_none(self, tmp_path: Any) -> None:
        structure = capture_structure(tmp_path / "doc.txt", file_type="text")
        assert structure is None

    def test_audio_is_none_in_this_lane(self, tmp_path: Any) -> None:
        assert capture_structure(tmp_path / "a.wav", file_type="audio") is None
        # Suffix-only detection (no file_type hint) routes audio too.
        assert capture_structure(tmp_path / "a.mp3") is None

    def test_never_raises_when_merge_fails(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(sc, "merge_structures", boom)
        structure = capture_structure(
            tmp_path / "book.pdf",
            docling_doc=docling_doc(doc_item("X", level=1, page=1)),
            file_type="pdf",
        )
        assert structure is None


# ---------------------------------------------------------------------------
# Real-PDF smoke test (reportlab-generated outline)
# ---------------------------------------------------------------------------


class TestCapturePdfOutlineRealPdf:
    """End-to-end capture against a real reportlab PDF with an outline."""

    @pytest.fixture
    def outlined_pdf(self, tmp_path: Any) -> Any:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as pdf_canvas
        except ImportError:  # pragma: no cover - env without reportlab
            pytest.skip("reportlab is not installed")

        pdf_path = tmp_path / "outlined.pdf"
        c = pdf_canvas.Canvas(str(pdf_path), pagesize=A4)
        c.bookmarkPage("ch1")
        c.addOutlineEntry("Chapter 1 — Installing", "ch1", level=0, closed=False)
        c.drawString(72, 750, "Chapter 1 — Installing")
        c.showPage()

        c.bookmarkPage("s11")
        c.addOutlineEntry("1.1 Prerequisites", "s11", level=1, closed=False)
        c.drawString(72, 750, "1.1 Prerequisites")
        c.showPage()

        c.bookmarkPage("ch2")
        c.addOutlineEntry("Chapter 2 — Configuring", "ch2", level=0, closed=False)
        c.drawString(72, 750, "Chapter 2 — Configuring")
        c.showPage()
        c.save()
        return pdf_path

    def test_capture_pdf_outline_roundtrip(self, outlined_pdf: Any) -> None:
        part = capture_pdf_outline(outlined_pdf)
        assert part.sources == {"outline": True}
        ch1, s11, ch2 = part.nodes
        assert ch1.node_id == "ch01"
        assert s11.node_id == "sec01.01" and s11.parent_id == "ch01"
        assert ch2.node_id == "ch02"
        # Page ranges from tree order; last node ends at the page count (3).
        assert ch1.page_start == 1 and s11.page_start == 2
        assert ch2.page_end == 3

    def test_page_labels_absent_yield_empty(self, outlined_pdf: Any) -> None:
        assert capture_page_labels(outlined_pdf) == []

    def test_capture_structure_end_to_end(self, outlined_pdf: Any) -> None:
        structure = capture_structure(outlined_pdf, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert structure.source_file == str(outlined_pdf)
        assert structure.sources["outline"] is True
        ids = [n.node_id for n in structure.nodes]
        assert ids == ["ch01", "sec01.01", "ch02"]
        assert structure.page_labels == []


# ---------------------------------------------------------------------------
# ToC-row parser (fix-chapter-coverage, task 1.1)
# ---------------------------------------------------------------------------


class TestParseTocRows:
    """parse_toc_rows: dot-leader rows in, (number, title, page, level) out."""

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("1 Introduction .... 1", ("1", "Introduction", 1, 1)),
            ("1.1 Central Management .... 2", ("1.1", "Central Management", 2, 2)),
            ("05.02 Input .... 3", ("5.2", "Input", 3, 2)),
            (
                "1.13 Translating Proxmox VE .... 15",
                ("1.13", "Translating Proxmox VE", 15, 2),
            ),
            ("1. Introduction .... 1", ("1", "Introduction", 1, 1)),  # punctuated
            ("1 Introduction . . . . 1", ("1", "Introduction", 1, 1)),  # spaced dots
            ("1 Introduction .......... 1", ("1", "Introduction", 1, 1)),
            ("   1.1 Indented row .... 2", ("1.1", "Indented row", 2, 2)),
            ("3.2 Local File-System", ("3.2", "Local File-System", None, 2)),
            ("2.3 Release 7.2 .... 5", ("2.3", "Release 7.2", 5, 2)),
            # Leader-less chapter rows (real pve-admin-guide 9.1 shape): the
            # printed page is glued after the title with a plain space.
            ("1 Introduction 1", ("1", "Introduction", 1, 1)),
            ("2 Installing Proxmox VE 10", ("2", "Installing Proxmox VE", 10, 1)),
            (
                "10 QEMU/KVM Virtual Machines 203",
                ("10", "QEMU/KVM Virtual Machines", 203, 1),
            ),
            (
                "6 Proxmox Cluster File System (pmxcfs) 136",
                ("6", "Proxmox Cluster File System (pmxcfs)", 136, 1),
            ),
            ("1 Introduction", ("1", "Introduction", None, 1)),  # no page anywhere
        ],
    )
    def test_row_shapes(
        self, line: str, expected: tuple[str, str, int | None, int]
    ) -> None:
        (row,) = parse_toc_rows(line)
        assert row == TocListing(*expected)

    def test_glued_camelcase_title(self) -> None:
        (row,) = parse_toc_rows("2.1 InstallingProxmoxVE .... 8")
        assert row == TocListing("2.1", "Installing Proxmox VE", 8, 2)

    def test_glued_number_title_junction(self) -> None:
        (row,) = parse_toc_rows("5.14.2MigrationNetwork .... 12")
        assert row == TocListing("5.14.2", "Migration Network", 12, 3)

    def test_glued_single_word_is_rejected(self) -> None:
        # One unbroken capitalized word is prose noise, never a glue victim.
        assert parse_toc_rows("1.2Beta .... 12") == []

    def test_version_rest_without_page_stays_whole(self) -> None:
        # "Release 7.2": no whitespace before the trailing digits, and the
        # dot inside "7.2" is glued to its token, not a leader — the rest
        # must stay whole and page-less, never "Release 7" with page 2.
        (row,) = parse_toc_rows("2.3 Release 7.2")
        assert row == TocListing("2.3", "Release 7.2", None, 2)
        # A real printed page after the version still splits off cleanly.
        (row,) = parse_toc_rows("2.3 Release 7.2 5")
        assert row == TocListing("2.3", "Release 7.2", 5, 2)

    def test_glued_row_with_bare_page(self) -> None:
        # The glued junction also parses when the page tail has no leader.
        (row,) = parse_toc_rows("5.14.2MigrationNetwork 12")
        assert row == TocListing("5.14.2", "Migration Network", 12, 3)

    def test_bare_page_never_splits_letterless_rest(self) -> None:
        # A pure-number rest has no alphabetic title left after the split —
        # the split is refused, and a rest without any letters at all has no
        # title text either, so the line is no row at all.
        assert parse_toc_rows("1 2 3") == []
        assert parse_toc_rows("1.1 .... 2") == []

    def test_crush_tree_line_stays_pageless(self) -> None:
        # Real `ceph osd crush tree` example output (pve body page): the
        # dots in "0.72769"/"osd.12" are glued to their tokens, not leaders,
        # and the trailing digits have no whitespace before them — the line
        # must never yield a fabricated page column.
        (row,) = parse_toc_rows("12 nvme 0.72769 osd.12")
        assert row == TocListing("12", "nvme 0.72769 osd.12", None, 1)

    def test_punctuated_row_with_bare_page_is_trusted(self) -> None:
        # A punctuated single-component row was only ever trusted WITH a
        # page column; the bare-page split now provides one ("1. Item 1" in
        # a markdown primer). Body pages full of such lines are rejected as
        # span outliers (see TestPdfTocListingsSpan).
        (row,) = parse_toc_rows("1. Item 1")
        assert row == TocListing("1", "Item", 1, 1)

    def test_pve_leaderless_chapter_rows(self) -> None:
        # Real pve-admin-guide 9.1 ToC shape: chapter rows carry NO dot
        # leader while subsection rows keep spaced dot leaders.
        rows = parse_toc_rows(
            "1 Introduction 1\n"
            "1.1 Central Management . . . . . . . . . . . . . . . . 2\n"
            "1.13 Translating Proxmox VE . . . . . . . . . . . . . . 8\n"
            "2 Installing Proxmox VE 10\n"
            "2.1 System Requirements . . . . . . . . . . . . . . . . 10\n"
        )
        assert [(r.number, r.title, r.page, r.level) for r in rows] == [
            ("1", "Introduction", 1, 1),
            ("1.1", "Central Management", 2, 2),
            ("1.13", "Translating Proxmox VE", 8, 2),
            ("2", "Installing Proxmox VE", 10, 1),
            ("2.1", "System Requirements", 10, 2),
        ]

    def test_wrapped_row_page_on_next_line(self) -> None:
        rows = parse_toc_rows(
            "1.10 Configuring the Network for\n    Guest Access .... 12"
        )
        assert rows == [
            TocListing("1.10", "Configuring the Network for Guest Access", 12, 2)
        ]

    def test_wrapped_row_number_alone(self) -> None:
        rows = parse_toc_rows("1.13\nTranslating Proxmox VE .... 15")
        assert rows == [TocListing("1.13", "Translating Proxmox VE", 15, 2)]

    def test_fold_expires_after_one_line(self) -> None:
        # Only the next non-blank line may close a page-less row; prose in
        # between expires it and later paged lines are ignored.
        rows = parse_toc_rows(
            "1.10 Configuring the Network for\n"
            "A paragraph intervenes\n"
            "Guest Access .... 12\n"
        )
        assert rows == [TocListing("1.10", "Configuring the Network for", None, 2)]

    @pytest.mark.parametrize(
        "line",
        [
            "1. Install the package",  # prose list item
            "1984",  # a year is a title, never a number
            "12",  # footer page number
            "1.1 .... 2",  # no title text
            "Contents",  # unnumbered header
            "Chapter 1 Introduction .... 5",  # chapter-word rows unsupported
            "iii Preface .... 2",  # roman-numeral rows unsupported
        ],
    )
    def test_non_rows_rejected(self, line: str) -> None:
        assert parse_toc_rows(line) == []

    def test_pve_toc_block(self) -> None:
        rows = parse_toc_rows(
            "Contents\n"
            "1 Introduction .... 1\n"
            "1.1 Central Management .... 2\n"
            "1.2 System Requirements .... 3\n"
            "1.13 Translating Proxmox VE .... 15\n"
            "2 Installing Proxmox VE .... 16\n"
        )
        assert [(r.number, r.title, r.page, r.level) for r in rows] == [
            ("1", "Introduction", 1, 1),
            ("1.1", "Central Management", 2, 2),
            ("1.2", "System Requirements", 3, 2),
            ("1.13", "Translating Proxmox VE", 15, 2),
            ("2", "Installing Proxmox VE", 16, 1),
        ]


# ---------------------------------------------------------------------------
# ToC page span = contiguous run (fix-chapter-coverage, amendment B)
# ---------------------------------------------------------------------------


class TestPdfTocListingsSpan:
    """_pdf_toc_listings: the ToC page span is a contiguous run of pages."""

    def test_longest_run_with_gap_tolerance(self) -> None:
        # Up to two page-less pages between consecutive paged pages keep the
        # run going (5→8 skips 6, 7); a larger gap ends it (4→8 skips three,
        # 5→9 skips three) and the outlier page is never glued on.
        assert sc._longest_paged_run([3, 4, 5, 8, 9, 213]) == (3, 9)
        assert sc._longest_paged_run([3, 4, 8, 213]) == (3, 4)
        assert sc._longest_paged_run([7]) == (7, 7)

    def test_longest_run_ties_take_the_earliest(self) -> None:
        assert sc._longest_paged_run([3, 4, 20, 21]) == (3, 4)

    def test_page213_outlier_rows_are_dropped(self, monkeypatch: Any) -> None:
        # Real pve-admin-guide shape (amendment evidence): 19 contiguous ToC
        # pages, then a Ceph body page whose `ceph osd crush tree` output
        # fabricates ToC-looking rows ("12 nvme 0.72769 osd.12" — page-less
        # under the hardened tails, plus a bare-page line that parses WITH a
        # page). A min/max span would have stretched to the outlier and the
        # span guard would have excluded every real body node; the run keeps
        # the span at the ToC and drops the outlier's rows entirely.
        pages = [
            {
                "page": toc_page,
                "text": (
                    f"{chapter} Chapter{chapter} {chapter}\n"
                    f"{chapter}.1 Detail . . . . {chapter}"
                ),
            }
            for chapter, toc_page in enumerate(range(3, 22), start=1)
        ]
        pages.append(
            {
                "page": 213,
                "text": "\n".join(f"{n} nvme 0.72769 osd.{n}" for n in (12, 13, 14))
                + "\n2 osd pools 3",
            }
        )
        monkeypatch.setattr(sc, "extract_native_pdf_text", lambda _p: pages)
        listings, span = sc._pdf_toc_listings(Path("/docs/pve.pdf"))
        assert span == (3, 21)
        expected: list[TocListing] = []
        for chapter in range(1, 20):
            expected.append(TocListing(str(chapter), f"Chapter{chapter}", chapter, 1))
            expected.append(TocListing(f"{chapter}.1", "Detail", chapter, 2))
        assert listings == expected  # nothing from page 213 survives

    def test_body_nodes_recover_across_the_whole_run(self) -> None:
        # Regression for the page-213 failure: with a (3, 21) ToC span, body
        # nodes after the run — even far beyond it — still recover; the old
        # min/max span (3, 213) excluded every node in between. Printed
        # pages sit a constant 9 behind the physical ones (the D5 offset the
        # walk derives from its first match), so every later row's derived
        # page lands on its node.
        outline = headings_part(
            [
                (1, "Introduction", 10),  # inside the ToC run
                (1, "Installing Proxmox VE", 23),  # right after it
                (1, "Deploy Hyper-Converged Ceph Cluster", 195),
                (2, "Ceph Client", 214),  # the outlier's neighborhood
            ],
            final_page=300,
        )
        listings = [
            TocListing("1", "Introduction", 1, 1),
            TocListing("2", "Installing Proxmox VE", 14, 1),
            TocListing("8", "Deploy Hyper-Converged Ceph Cluster", 186, 1),
            TocListing("8.11", "Ceph Client", 205, 2),
        ]
        recovered = recover_chapter_numbers(
            merge_structures(outline), listings, toc_page_span=(3, 21)
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Introduction"].number is None  # page 10 inside the run
        assert by_title["Installing Proxmox VE"].number == "2"
        assert by_title["Deploy Hyper-Converged Ceph Cluster"].number == "8"
        assert by_title["Ceph Client"].number == "8.11"


# ---------------------------------------------------------------------------
# Post-merge numbering recovery (fix-chapter-coverage, task 1.2, D1)
# ---------------------------------------------------------------------------


def pve_outline_part(source_file: str = "/docs/pve.pdf") -> DocumentStructure:
    """A pve-shaped outline part whose bookmark titles carry NO numbers."""
    return headings_part(
        [
            (1, "Introduction", 23),
            (2, "Central Management", 23),
            (2, "System Requirements", 24),
            (2, "Translating Proxmox VE", 30),
            (1, "Installing Proxmox VE", 32),
            (2, "Using the Proxmox VE Installer", 33),
            (1, "GNU Free Documentation License", 300),
        ],
        source_file=source_file,
        allow_parts=True,
        final_page=340,
    )


def pve_listings() -> list[TocListing]:
    """The pve-shaped ToC listings matching :func:`pve_outline_part`.

    Printed pages sit a consistent ~21-22 physical pages behind their
    bookmark pages (the D5 offset the label-less walk derives from its
    first match), so every row's derived page lands on its node.
    """
    return [
        TocListing("1", "Introduction", 1, 1),
        TocListing("1.1", "Central Management", 2, 2),
        TocListing("1.2", "System Requirements", 3, 2),
        TocListing("1.3", "Translating Proxmox VE", 7, 2),
        TocListing("2", "Installing Proxmox VE", 10, 1),
        TocListing("2.1", "Using the Proxmox VE Installer", 11, 2),
    ]


class TestRecoverChapterNumbers:
    """The D1 pass: number-less nodes gain numbers from ToC listings."""

    def test_numberless_outline_yields_numbered_tree(self) -> None:
        # Spec scenario: a number-less PDF outline + its own ToC listings
        # produce a fully numbered tree at the bookmark page ranges.
        merged = merge_structures(pve_outline_part())
        recovered = recover_chapter_numbers(
            merged, pve_listings(), toc_page_span=(3, 22)
        )
        by_title = {node.title: node for node in recovered.nodes}
        intro = by_title["Introduction"]
        assert intro.number == "1"
        assert intro.node_id == "ch-introduction"  # ids stay the storage keys
        assert (intro.page_start, intro.page_end) == (23, 31)  # bookmark range
        assert intro.heading_path == "Chapter 1 — Introduction"
        for title, number in (
            ("Central Management", "1.1"),
            ("System Requirements", "1.2"),
            ("Translating Proxmox VE", "1.3"),
            ("Installing Proxmox VE", "2"),
            ("Using the Proxmox VE Installer", "2.1"),
        ):
            assert by_title[title].number == number
        # inheritance: descendants carry the chapter's leading component
        assert (
            by_title["Central Management"].heading_path
            == "Chapter 1 — Introduction > 1.1"
        )
        assert (
            by_title["Using the Proxmox VE Installer"].parent_id
            == by_title["Installing Proxmox VE"].node_id
        )
        # unlisted nodes stay number-less
        assert by_title["GNU Free Documentation License"].number is None
        assert recovered.sources["toc_number_recovery"] is True

    def test_recovery_is_pure(self) -> None:
        merged = merge_structures(pve_outline_part())
        snapshot = [(node.number, node.heading_path) for node in merged.nodes]
        recover_chapter_numbers(merged, pve_listings())
        assert [(node.number, node.heading_path) for node in merged.nodes] == snapshot

    def test_parsed_numbers_are_never_overwritten(self) -> None:
        # Spec scenario: a title that already carries a numbering token
        # ("2.3 Using the Proxmox VE Installer") is kept as-is.
        outline = headings_part(
            [
                (1, "Introduction", 23),
                (2, "Central Management", 23),
                (1, "Configuring Systems", 40),
                (2, "2.3 Using the Proxmox VE Installer", 41),
            ],
            final_page=50,
        )
        listings = [
            TocListing("1", "Introduction", 1, 1),
            TocListing("1.1", "Central Management", 2, 2),
            TocListing("2", "Configuring Systems", 20, 1),
            TocListing("2.3", "Using the Proxmox VE Installer", 22, 2),
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        by_id = {node.node_id: node for node in recovered.nodes}
        parsed = by_id["sec02.03"]
        assert parsed.number == "2.3"
        assert parsed.title == "Using the Proxmox VE Installer"
        # its recovered ancestor still relabels the path; the parsed number
        # itself is untouched
        assert parsed.heading_path == "Chapter 2 — Configuring Systems > 2.3"

    def test_ambiguous_match_stays_unnumbered(self) -> None:
        # Spec scenario: a title matching multiple listings equally — and a
        # title matching nothing — persist without a number. Both same-title
        # rows map near the node (printed +22), so the ambiguity (not the
        # page bound) refuses them; the CommandLine node sits on its own
        # row's derived page.
        outline = headings_part(
            [
                (1, "Introduction", 23),
                (2, "Configuration File Options", 25),
                (1, "Command Line Options", 72),
                (2, "Configuration File Options", 61),
            ],
            final_page=80,
        )
        listings = [
            TocListing("1", "Introduction", 1, 1),
            TocListing("3.1", "Configuration File Options", 1, 2),
            TocListing("9.1", "Configuration File Options", 4, 2),
            TocListing("10", "Command Line Options", 50, 1),
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        numbered = [
            (node.title, node.number)
            for node in recovered.nodes
            if node.number is not None
        ]
        assert numbered == [("Introduction", "1"), ("Command Line Options", "10")]
        options = [
            node
            for node in recovered.nodes
            if node.title == "Configuration File Options"
        ]
        assert [node.number for node in options] == [None, None]

    def test_one_listing_assigns_at_most_one_node(self) -> None:
        outline = headings_part(
            [(1, "Overview", 5), (1, "Overview", 20)], final_page=30
        )
        recovered = recover_chapter_numbers(
            merge_structures(outline), [TocListing("1", "Overview", 1, 1)]
        )
        assert [node.number for node in recovered.nodes] == ["1", None]

    def test_duplicate_listings_are_ambiguous_for_every_node(self) -> None:
        outline = headings_part(
            [(1, "Overview", 5), (1, "Overview", 20)], final_page=30
        )
        listings = [
            TocListing("1", "Overview", 1, 1),
            TocListing("2", "Overview", 2, 1),
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        assert [node.number for node in recovered.nodes] == [None, None]

    def test_level_mismatch_stays_unnumbered(self) -> None:
        outline = headings_part([(1, "Overview", 5)], final_page=10)
        listings = [TocListing("1.1", "Overview", 2, 2)]  # ToC: section, tree: chapter
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        assert recovered.nodes[0].number is None

    def test_out_of_order_match_stays_unnumbered(self) -> None:
        # Document order must agree with ToC order: the first node takes the
        # only listing still ahead of the cursor, the second finds none.
        outline = headings_part(
            [(1, "Installing", 20), (1, "Configuring", 30)], final_page=40
        )
        listings = [
            TocListing("2", "Configuring", 10, 1),
            TocListing("1", "Installing", 5, 1),
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        assert [node.number for node in recovered.nodes] == ["1", None]

    def test_nodes_inside_toc_span_are_excluded(self) -> None:
        # Headings captured from ToC-page text must never number themselves.
        outline = headings_part(
            [(1, "Introduction", 15), (1, "Installing", 23)], final_page=40
        )
        listings = [
            TocListing("1", "Introduction", 1, 1),
            TocListing("2", "Installing", 2, 1),
        ]
        recovered = recover_chapter_numbers(
            merge_structures(outline), listings, toc_page_span=(3, 22)
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Introduction"].number is None  # page 15 inside the span
        assert by_title["Installing"].number == "2"  # page 23 outside it

    def test_junk_toc_page_headings_do_not_desynchronize(self) -> None:
        outline = pve_outline_part()
        junk = capture_docling_headings(
            docling_doc(
                doc_item("1 Introduction", level=1, page=3),  # numbered junk
                doc_item("Introduction", level=1, page=15),  # number-less junk
            ),
            Path(outline.source_file),
        )
        assert junk is not None
        merged = merge_structures(outline, junk)
        recovered = recover_chapter_numbers(
            merged, pve_listings(), toc_page_span=(3, 22)
        )
        junk_numbered = next(n for n in recovered.nodes if n.page_start == 3)
        junk_numberless = next(n for n in recovered.nodes if n.page_start == 15)
        intro = next(
            n
            for n in recovered.nodes
            if n.title == "Introduction" and n.page_start == 23
        )
        assert junk_numbered.number == "1"  # parsed number, untouched
        assert junk_numberless.number is None  # inside the ToC span
        assert intro.number == "1"  # the real chapter still recovers

    def test_inconsistent_with_recovered_parent_stays_unnumbered(self) -> None:
        outline = headings_part([(1, "Storage", 23), (2, "Extents", 24)], final_page=40)
        listings = [
            TocListing("5", "Storage", 1, 1),
            TocListing("9.9", "Extents", 2, 2),
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Storage"].number == "5"
        assert by_title["Extents"].number is None  # 9.9 cannot live under 5

    def test_section_under_unnumbered_parent_still_recovers(self) -> None:
        # An unmatched parent does not make the child's ToC-derived number
        # wrong; only a NUMBERED parent constrains its children.
        outline = headings_part([(1, "Storage", 23), (2, "Extents", 24)], final_page=40)
        listings = [TocListing("9.9", "Extents", 2, 2)]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Storage"].number is None
        assert by_title["Extents"].number == "9.9"

    def test_inconsistent_with_parsed_children_stays_unnumbered(self) -> None:
        outline = headings_part(
            [(1, "Storage", 23), (2, "5.2 Extents", 24)], final_page=40
        )
        listings = [TocListing("3", "Storage", 1, 1)]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        storage, extents = recovered.nodes
        assert storage.number is None  # children parsed as 5.x, not 3.x
        assert extents.number == "5.2"  # parsed child untouched

    def test_glued_node_title_matches_spaced_listing(self) -> None:
        outline = headings_part([(1, "InstallingProxmoxVE", 32)], final_page=40)
        listings = [TocListing("2", "Installing Proxmox VE", 15, 1)]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        assert recovered.nodes[0].number == "2"
        assert recovered.nodes[0].title == "InstallingProxmoxVE"  # titles untouched

    def test_glued_listing_matches_spaced_node(self) -> None:
        outline = headings_part([(1, "Installing Proxmox VE", 32)], final_page=40)
        (listing,) = parse_toc_rows("2 InstallingProxmoxVE .... 15")
        recovered = recover_chapter_numbers(merge_structures(outline), [listing])
        assert recovered.nodes[0].number == "2"

    def test_recovery_from_parsed_toc_text(self) -> None:
        merged = merge_structures(pve_outline_part())
        listings = parse_toc_rows(
            "1 Introduction .... 1\n"
            "1.1 Central Management .... 2\n"
            "1.2 System Requirements .... 3\n"
            "1.3 Translating Proxmox VE .... 7\n"
            "2 Installing Proxmox VE .... 10\n"
            "2.1 Using the Proxmox VE Installer .... 11\n"
        )
        recovered = recover_chapter_numbers(merged, listings, toc_page_span=(3, 22))
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Introduction"].number == "1"
        assert by_title["Translating Proxmox VE"].number == "1.3"

    def test_recovery_is_idempotent(self) -> None:
        once = recover_chapter_numbers(
            merge_structures(pve_outline_part()), pve_listings(), toc_page_span=(3, 22)
        )
        twice = recover_chapter_numbers(once, pve_listings(), toc_page_span=(3, 22))
        assert twice.nodes == once.nodes

    def test_no_listings_or_no_nodes_return_unchanged(self) -> None:
        merged = merge_structures(pve_outline_part())
        assert recover_chapter_numbers(merged, []) is merged
        empty = merge_structures(None, None)
        assert recover_chapter_numbers(empty, pve_listings()) is empty


# ---------------------------------------------------------------------------
# Page bound on the recovery match (fix-chapter-coverage, D1 refinement)
# ---------------------------------------------------------------------------


def bound_labels() -> list[PageLabelRange]:
    """One decimal label run: printed page P sits on physical page P + 4."""
    return [PageLabelRange(page_start=5, page_end=60, label="1", style="decimal")]


def bound_structure(
    entries: list[tuple[int, str, int]],
    labels: list[PageLabelRange] | None = None,
) -> DocumentStructure:
    """A merged structure carrying /PageLabels, as capture wiring does.

    Args:
        entries: ``(level, title, page)`` heading tuples.
        labels: Page-label runs to attach; None attaches the default decimal
            run (:func:`bound_labels`), ``[]`` models a label-less document.
    """
    merged = merge_structures(headings_part(entries, final_page=70))
    merged.page_labels = bound_labels() if labels is None else list(labels)
    return merged


# All level 1 so the parent-consistency guard stays out of the way. ToC
# order puts the generic "Configuration" row LAST, 29 physical pages past
# the node old order-only matching lets it number — consuming it starves
# Beta, whose row lies before the consumed index.
JUMP_ENTRIES = [
    (1, "Alpha", 10),
    (1, "Configuration", 20),
    (1, "Beta", 30),
]
JUMP_LISTINGS = [
    TocListing("1", "Alpha", 6, 1),  # printed 6 -> physical 10: Alpha's page
    TocListing("5", "Beta", 26, 1),  # printed 26 -> physical 30: Beta's page
    TocListing("9", "Configuration", 45, 1),  # printed 45 -> physical 49: far
]


class TestRecoveryPageBound:
    """A listing may only number a node near where the ToC says it sits."""

    def test_far_ahead_match_rejected_and_starved_sibling_recovers(self) -> None:
        # Old order-only walk: Alpha -> "1", then the generic "Configuration"
        # node consumes the far "9 Configuration" row (physical 49 vs p.20)
        # and starves Beta. With the page bound the far row is rejected and
        # Beta recovers instead.
        recovered = recover_chapter_numbers(
            bound_structure(JUMP_ENTRIES), JUMP_LISTINGS
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Alpha"].number == "1"  # near match still accepted
        assert by_title["Configuration"].number is None  # 29 pages away: no
        assert by_title["Beta"].number == "5"  # no longer starved

    def test_without_page_labels_bounded_by_derived_offset(self) -> None:
        # D5: a label-less document bounds its walk with the offset its own
        # matched listings observe — Alpha anchors it (no evidence yet, the
        # order-only rule), the far-ahead "9 Configuration" row is then
        # rejected (45 + 4 != 20), and the starved Beta recovers.
        recovered = recover_chapter_numbers(
            bound_structure(JUMP_ENTRIES, labels=[]), JUMP_LISTINGS
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Alpha"].number == "1"  # first anchor: order-only
        assert by_title["Configuration"].number is None  # 29 pages off: no
        assert by_title["Beta"].number == "5"  # no longer starved

    def test_without_labels_or_evidence_fails_open_to_order_only(self) -> None:
        # Zero evidence (no labels, no matched listings yet): the very first
        # candidate anchors order-only — today's behavior, unchanged.
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Configuration", 20)], labels=[]),
            [TocListing("9", "Configuration", 45, 1)],  # printed 45 → far
        )
        assert recovered.nodes[0].number == "9"

    def test_refused_skew_cannot_steer_the_derived_offset(self) -> None:
        # D5: the offset pool feeds only from MATCHED rows, so the derived
        # bound stays the honest median of what the walk actually observed.
        # A row whose printed page disagrees with it beyond the tolerance is
        # refused and its skew never enters the pool: Gamma's row (printed
        # 34 → 38 under the offset-4 evidence, twelve pages short of the
        # node at 50) starves, while Delta still recovers after it — a pool
        # poisoned by the refused skew (mean 8) would map Delta's row to 74
        # and starve it too.
        labels: list[PageLabelRange] = []  # label-less: D5 fallback drives
        outline = headings_part(
            [
                (1, "Alpha", 10),
                (1, "Beta", 30),
                (1, "Gamma", 50),
                (1, "Delta", 70),
                (1, "Epsilon", 80),
            ],
            final_page=90,
        )
        outline.page_labels = labels
        listings = [
            TocListing("1", "Alpha", 6, 1),  # anchor: order-only, offset 4
            TocListing("2", "Beta", 26, 1),  # 26 + 4: matches
            TocListing("3", "Gamma", 34, 1),  # 34 + 4 = 38 vs 50: refused
            TocListing("4", "Delta", 66, 1),  # 66 + 4: matches — pool honest
            TocListing("5", "Epsilon", 94, 1),  # 94 + 4 vs 80: refused
        ]
        recovered = recover_chapter_numbers(merge_structures(outline), listings)
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Alpha"].number == "1"
        assert by_title["Beta"].number == "2"
        assert by_title["Gamma"].number is None
        assert by_title["Delta"].number == "4"
        assert by_title["Epsilon"].number is None

    def test_bound_resolves_ambiguity_toward_the_near_row(self) -> None:
        # Two same-title listings: order-only sees ambiguity and numbers
        # nothing; the bound rejects the far row, the near one becomes the
        # unique candidate.
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Configuration", 20)]),
            [
                TocListing("5", "Configuration", 16, 1),  # -> physical 20
                TocListing("9", "Configuration", 45, 1),  # -> physical 49
            ],
        )
        assert recovered.nodes[0].number == "5"

    @pytest.mark.parametrize(
        ("node_page", "expected"),
        [
            (17, "4"),  # |17 - 14| == tolerance
            (11, "4"),
            (18, None),  # one past tolerance
            (10, None),
        ],
        ids=["at-plus-tol", "at-minus-tol", "past-plus-tol", "past-minus-tol"],
    )
    def test_tolerance_edges(self, node_page: int, expected: str | None) -> None:
        # '4 Zeta' printed 10 maps to physical 14; only nodes within 3
        # physical pages may take its number.
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Zeta", node_page)]),
            [TocListing("4", "Zeta", 10, 1)],
        )
        assert recovered.nodes[0].number == expected

    def test_page_less_listing_uses_interpolated_bracket(self) -> None:
        # '2 Zeta' carries no page: its bracket comes from the paged rows
        # around it (physical 10 and 20 -> allowed [7, 23]).
        listings = [
            TocListing("1", "Alpha", 6, 1),  # -> physical 10
            TocListing("2", "Zeta", None, 1),
            TocListing("3", "Beta", 16, 1),  # -> physical 20
        ]
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Alpha", 10), (1, "Zeta", 14), (1, "Beta", 20)]),
            listings,
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Zeta"].number == "2"
        assert by_title["Alpha"].number == "1"
        assert by_title["Beta"].number == "3"

    def test_page_less_listing_rejects_beyond_bracket(self) -> None:
        # Nodes come back in page order, so the far "Beta" row here is only
        # the bracket anchor (mapped 20): no node matches it, keeping Zeta
        # first in the walk. Order-only would hand Zeta the row; the bracket
        # [7, 23] rejects it.
        listings = [
            TocListing("1", "Alpha", 6, 1),  # -> physical 10
            TocListing("2", "Zeta", None, 1),
            TocListing("3", "Beta", 16, 1),  # -> physical 20
        ]
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Zeta", 60)]), listings
        )
        assert recovered.nodes[0].number is None  # 60 beyond [7, 23]

    def test_page_less_bracket_missing_side_stays_open_to_that_side(self) -> None:
        # No paged row BEFORE the page-less one: only the next row bounds it
        # (the "Beta" row is the anchor — no node matches it, so Zeta is
        # walked first).
        listings = [
            TocListing("1", "Zeta", None, 1),
            TocListing("2", "Beta", 16, 1),  # -> physical 20, bounds from above
        ]
        beyond = recover_chapter_numbers(bound_structure([(1, "Zeta", 60)]), listings)
        assert beyond.nodes[0].number is None  # 60 past 20 + 3
        # No paged row AFTER the page-less one: only the previous row bounds
        # it — inside the open side it still matches, before the closed side
        # it does not.
        listings = [
            TocListing("1", "Alpha", 6, 1),  # -> physical 10, bounds from below
            TocListing("2", "Zeta", None, 1),
        ]
        inside = recover_chapter_numbers(
            bound_structure([(1, "Alpha", 10), (1, "Zeta", 40)]), listings
        )
        by_title = {node.title: node for node in inside.nodes}
        assert by_title["Alpha"].number == "1"
        assert by_title["Zeta"].number == "2"  # 40 within [7, inf)
        before = recover_chapter_numbers(
            bound_structure([(1, "Alpha", 10), (1, "Zeta", 3)]), listings
        )
        by_title = {node.title: node for node in before.nodes}
        assert by_title["Alpha"].number == "1"
        assert by_title["Zeta"].number is None  # 3 below 10 - 3

    def test_page_less_without_mappable_neighbors_fails_open(self) -> None:
        # Labels exist, but the only listing is page-less and has no paged
        # ToC neighbors: nothing to bracket, order-only applies.
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Zeta", 100)]),
            [TocListing("4", "Zeta", None, 1)],
        )
        assert recovered.nodes[0].number == "4"

    def test_roman_only_labels_fail_open(self) -> None:
        # Roman runs carry no body pages: decimal mapping finds nothing and
        # the bound fails open instead of rejecting everything.
        roman = [
            PageLabelRange(page_start=1, page_end=100, label="i", style="lower_roman")
        ]
        recovered = recover_chapter_numbers(
            bound_structure([(1, "Zeta", 100)], labels=roman),
            [TocListing("4", "Zeta", 10, 1)],
        )
        assert recovered.nodes[0].number == "4"

    def test_recovery_with_bound_is_idempotent(self) -> None:
        once = recover_chapter_numbers(bound_structure(JUMP_ENTRIES), JUMP_LISTINGS)
        twice = recover_chapter_numbers(once, JUMP_LISTINGS)
        assert twice is once  # nothing left to assign: unchanged object
        assert twice.nodes == once.nodes

    def test_second_run_rescues_row_passed_by_same_page_sibling(self) -> None:
        # A same-page node walked first consumes the row AFTER the deeper
        # node's (storage load order walks level 2 before level 3 at one
        # page), passing that row: run 1 starves the deeper node, run 2 —
        # with the passer numbered and no longer advancing the cursor —
        # rescues it with its own page-valid row. A third run is a no-op.
        entries = [
            (1, "Chapter", 29),  # printed 25 -> physical 29
            (2, "Misc", 30),
            (3, "Hookscripts", 30),
            (2, "Security", 30),
        ]
        listings = [
            TocListing("11", "Chapter", 25, 1),  # -> physical 29
            TocListing("11.4.7", "Hookscripts", 26, 3),  # -> physical 30
            TocListing("11.4", "Misc", 26, 2),  # -> physical 30
            TocListing("11.5", "Security", 26, 2),  # -> physical 30
        ]
        once = recover_chapter_numbers(bound_structure(entries), listings)
        numbers = {n.title: n.number for n in once.nodes}
        assert numbers == {
            "Chapter": "11",
            "Misc": "11.4",
            "Hookscripts": None,  # its row was passed by Misc's assignment
            "Security": "11.5",
        }
        twice = recover_chapter_numbers(once, listings)
        numbers = {n.title: n.number for n in twice.nodes}
        assert numbers["Hookscripts"] == "11.4.7"  # rescued, page-valid
        assert numbers["Security"] == "11.5"  # nothing renumbered
        assert recover_chapter_numbers(twice, listings) is twice  # fixpoint


# ---------------------------------------------------------------------------
# Wiring: capture_structure runs the pass before persistence (task 1.3, D1)
# ---------------------------------------------------------------------------


class TestTocRecoveryWiring:
    """capture_structure's PDF branch runs the recovery pass (single call)."""

    def test_pdf_capture_recovers_numbers_from_toc_text(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        path = tmp_path / "book.pdf"  # does not exist: real outline/labels fail
        monkeypatch.setattr(
            sc,
            "capture_pdf_outline",
            lambda p: headings_part(
                [(1, "Introduction", 23), (2, "Central Management", 23)],
                source_file=str(p),
                final_page=40,
            ),
        )
        monkeypatch.setattr(
            sc,
            "extract_native_pdf_text",
            lambda p: [
                {
                    "text": "1 Introduction .... 1\n1.1 Central Management .... 2",
                    "page": 3,
                }
            ],
        )
        structure = capture_structure(path, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert [(node.title, node.number) for node in structure.nodes] == [
            ("Introduction", "1"),
            ("Central Management", "1.1"),
        ]
        assert structure.sources["toc_number_recovery"] is True

    def test_failed_toc_scan_leaves_the_tree_unrecovered(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        path = tmp_path / "book.pdf"
        monkeypatch.setattr(
            sc,
            "capture_pdf_outline",
            lambda p: headings_part(
                [(1, "Introduction", 23)], source_file=str(p), final_page=40
            ),
        )
        monkeypatch.setattr(sc, "extract_native_pdf_text", lambda p: [])
        structure = capture_structure(path, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert structure.nodes[0].number is None
        assert "toc_number_recovery" not in structure.sources

    def test_recovery_failure_never_breaks_capture(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        path = tmp_path / "book.pdf"
        monkeypatch.setattr(
            sc,
            "capture_pdf_outline",
            lambda p: headings_part(
                [(1, "Introduction", 23)], source_file=str(p), final_page=40
            ),
        )
        monkeypatch.setattr(
            sc,
            "extract_native_pdf_text",
            lambda p: [{"text": "1 Introduction .... 1", "page": 3}],
        )

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(sc, "recover_chapter_numbers", boom)
        structure = capture_structure(path, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert [node.number for node in structure.nodes] == [None]

    def test_non_pdf_branch_never_scans_for_toc(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        called: list[bool] = []

        def fake_scan(_path: Any) -> tuple[list[TocListing], None]:
            called.append(True)
            return [], None

        monkeypatch.setattr(sc, "_pdf_toc_listings", fake_scan)
        assert capture_structure(tmp_path / "doc.txt", file_type="text") is None
        assert called == []  # the ToC scan is PDF-branch only


class TestTocRecoveryPersistence:
    """Recovered numbers round-trip through StructureStore (task 1.3)."""

    def test_recovered_numbers_roundtrip_through_sqlite(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        path = tmp_path / "pve.pdf"
        outline = pve_outline_part(source_file=str(path))
        monkeypatch.setattr(sc, "capture_pdf_outline", lambda p: outline)
        monkeypatch.setattr(
            sc,
            "extract_native_pdf_text",
            lambda p: [
                {
                    "text": (
                        "1 Introduction .... 1\n"
                        "1.1 Central Management .... 2\n"
                        "1.2 System Requirements .... 3\n"
                        "1.3 Translating Proxmox VE .... 7\n"
                        "2 Installing Proxmox VE .... 10\n"
                        "2.1 Using the Proxmox VE Installer .... 11\n"
                    ),
                    "page": 3,
                }
            ],
        )
        structure = capture_structure(path, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert [node.number for node in structure.nodes] == [
            "1",
            "1.1",
            "1.2",
            "1.3",
            "2",
            "2.1",
            None,
        ]

        store = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
        try:
            store.save_structure(structure)
            loaded = store.load_tree(str(path))
        finally:
            store.close()
        assert loaded is not None
        assert loaded.nodes == structure.nodes  # full fidelity, numbers included
        by_title = {node.title: node for node in loaded.nodes}
        assert by_title["Introduction"].number == "1"
        assert by_title["Central Management"].number == "1.1"
        assert by_title["Installing Proxmox VE"].number == "2"
        assert by_title["GNU Free Documentation License"].number is None
        assert (
            by_title["Central Management"].heading_path
            == "Chapter 1 — Introduction > 1.1"
        )


class TestTocRecoveryRealPdf:
    """End-to-end against a real reportlab PDF (skipped without reportlab)."""

    def test_capture_recovers_from_real_pdf(self, tmp_path: Any) -> None:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as pdf_canvas
        except ImportError:  # pragma: no cover - env without reportlab
            pytest.skip("reportlab is not installed")

        pdf_path = tmp_path / "toc-book.pdf"
        c = pdf_canvas.Canvas(str(pdf_path), pagesize=A4)
        # Page 1: a dot-leader ToC.
        c.drawString(72, 750, "Contents")
        c.drawString(72, 730, "1 Introduction .... 1")
        c.drawString(72, 710, "1.1 Central Management .... 2")
        c.showPage()
        # Pages 2+: number-less bookmark outline over the body.
        c.bookmarkPage("ch1")
        c.addOutlineEntry("Introduction", "ch1", level=0, closed=False)
        c.drawString(72, 750, "Introduction")
        c.showPage()
        c.bookmarkPage("s11")
        c.addOutlineEntry("Central Management", "s11", level=1, closed=False)
        c.drawString(72, 750, "Central Management")
        c.showPage()
        c.save()

        structure = capture_structure(pdf_path, docling_doc=None, file_type="pdf")
        assert structure is not None
        assert structure.sources["outline"] is True
        assert structure.sources["toc_number_recovery"] is True
        chapter, section = structure.nodes
        assert (chapter.title, chapter.number) == ("Introduction", "1")
        assert chapter.node_id == "ch-introduction"
        assert (section.title, section.number) == ("Central Management", "1.1")
        assert section.heading_path == "Chapter 1 — Introduction > 1.1"


# ---------------------------------------------------------------------------
# ToC ghost suppression at capture (fix-chat-session-integrity D4 / task 3.1)
# ---------------------------------------------------------------------------


def _pve_labels() -> list[PageLabelRange]:
    """One decimal label run: printed page P sits on physical page P + 10.

    The brief's shape: the ToC prints "7 Proxmox VE Storage … 153" while the
    real chapter 7 opens on physical page 163 (front matter shifts the body).
    """
    return [PageLabelRange(page_start=11, page_end=300, label="1", style="decimal")]


class TestToCGhostSuppression:
    """ToC-page candidates that echo a listing row are suppressed (D4)."""

    def test_span_and_match_matrix(self, tmp_path: Any) -> None:
        # Both conditions are required: span + listing-row match drops the
        # ghost; span alone, match alone, and neither all keep the heading.
        part = capture_docling_headings(
            docling_doc(
                doc_item("Foreword", level=1, page=5),  # span only: front matter
                doc_item("7 Proxmox VE Storage", level=1, page=9),  # span + match
                doc_item("Cluster Architecture", level=1, page=30),  # neither
                doc_item("Proxmox VE Storage", level=1, page=163),  # match only
            ),
            tmp_path / "book.pdf",
            toc_listings=[TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 22),
        )
        assert part is not None
        assert [(node.title, node.page_start) for node in part.nodes] == [
            ("Foreword", 5),
            ("Cluster Architecture", 30),
            ("Proxmox VE Storage", 163),  # the real chapter survives
        ]
        assert sc._suppressed_entries_of(part) == [
            {"title": "7 Proxmox VE Storage", "page": 9}
        ]
        assert isinstance(part.sources[sc._META_SUPPRESSED_KEY], str)

    def test_span_boundaries_are_inclusive(self, tmp_path: Any) -> None:
        part = capture_docling_headings(
            docling_doc(
                *[
                    doc_item("Proxmox VE Storage", level=1, page=page)
                    for page in (2, 3, 22, 23)
                ]
            ),
            tmp_path / "book.pdf",
            toc_listings=[TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 22),
        )
        assert part is not None
        assert [node.page_start for node in part.nodes] == [2, 23]
        assert [e["page"] for e in sc._suppressed_entries_of(part)] == [3, 22]

    def test_no_evidence_suppresses_nothing(self, tmp_path: Any) -> None:
        ghost = docling_doc(doc_item("7 Proxmox VE Storage", level=1, page=9))
        listing = TocListing("7", "Proxmox VE Storage", 153, 1)
        # Span unknown: nothing can be placed inside it, so nothing is dropped.
        part = capture_docling_headings(
            ghost,
            tmp_path / "book.pdf",
            toc_listings=[listing],
            toc_page_span=None,
        )
        assert part is not None
        assert sc._META_SUPPRESSED_KEY not in part.sources
        # Rows unknown: a text match alone is too eager (front matter shares
        # the span's pages), so the span-only page test cannot run.
        part = capture_docling_headings(
            ghost,
            tmp_path / "book.pdf",
            toc_listings=[],
            toc_page_span=(3, 22),
        )
        assert part is not None
        assert sc._META_SUPPRESSED_KEY not in part.sources
        # No evidence passed at all on a non-PDF path: same posture.
        part = capture_docling_headings(ghost, tmp_path / "book.txt")
        assert part is not None
        assert sc._META_SUPPRESSED_KEY not in part.sources

    def test_precomputed_evidence_is_reused_not_rescanned(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        def no_rescan(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("evidence was passed; no rescan may happen")

        monkeypatch.setattr(sc, "_toc_evidence", no_rescan)
        part = capture_docling_headings(
            docling_doc(doc_item("7 Proxmox VE Storage", level=1, page=9)),
            tmp_path / "book.pdf",
            toc_listings=[TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 22),
        )
        assert part is None  # the ghost was suppressed without any rescan

    def test_every_candidate_suppressed_reports_none(self, tmp_path: Any) -> None:
        part = capture_docling_headings(
            docling_doc(
                doc_item("1 Introduction", level=1, page=3),
                doc_item("7 Proxmox VE Storage", level=1, page=9),
            ),
            tmp_path / "book.pdf",
            toc_listings=[
                TocListing("1", "Introduction", 1, 1),
                TocListing("7", "Proxmox VE Storage", 153, 1),
            ],
            toc_page_span=(3, 22),
        )
        assert part is None  # no part survives — the ghosts are gone either way

    def test_pageless_candidates_survive_the_seam(self) -> None:
        # A candidate without provenance cannot be placed inside a span, so
        # suppression never drops it (node building later skips it).
        kept, suppressed = sc._suppress_toc_page_headings(
            [(1, "7 Proxmox VE Storage", None), (1, "Foreword", 5)],
            [TocListing("7", "Proxmox VE Storage", 153, 1)],
            (3, 22),
        )
        assert kept == [(1, "7 Proxmox VE Storage", None), (1, "Foreword", 5)]
        assert suppressed == []

    def test_listing_text_match_variants(self) -> None:
        keys = [
            (
                sc._match_key("Proxmox VE Storage"),
                sc._match_squash("Proxmox VE Storage"),
            )
        ]
        assert sc._text_matches_toc_listing("7 Proxmox VE Storage", keys)
        assert sc._text_matches_toc_listing("ProxmoxVEStorage", keys)  # glued
        assert not sc._text_matches_toc_listing("Proxmox VE Installation", keys)

    def test_e2e_capture_suppresses_ghosts_and_records_evidence(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        # The brief's defect shape: docling reads the flattened ToC rows on
        # pages 3-5 as numbered section headers; the real number-less
        # chapters sit at 13/163/195. Suppression drops the ghosts, and the
        # recovery pass (shared evidence) numbers the real chapters through
        # the printed-page labels.
        path = tmp_path / "pve.pdf"  # does not exist: outline/labels are faked
        scans: list[Path] = []

        def fake_text(p: Path) -> list[dict[str, Any]]:
            scans.append(p)
            return [
                {
                    "text": "1 Introduction .... 1\n2 Installing Proxmox VE .... 10",
                    "page": 3,
                },
                {"text": "7 Proxmox VE Storage .... 153", "page": 4},
                {"text": "8 Backup and Restore .... 185", "page": 5},
            ]

        monkeypatch.setattr(sc, "capture_pdf_outline", lambda p: None)
        monkeypatch.setattr(sc, "capture_page_labels", lambda p: _pve_labels())
        monkeypatch.setattr(sc, "extract_native_pdf_text", fake_text)
        structure = capture_structure(
            path,
            docling_doc=docling_doc(
                doc_item("1 Introduction", level=1, page=3),  # ghost
                doc_item("2 Installing Proxmox VE", level=1, page=4),  # ghost
                doc_item("7 Proxmox VE Storage", level=1, page=5),  # ghost
                doc_item("Introduction", level=1, page=13),  # real chapter 1
                doc_item("Proxmox VE Storage", level=1, page=163),  # real 7
                doc_item("Backup and Restore", level=1, page=195),  # real 8
                doc_item(
                    "GNU Free Documentation License", level=2, page=215
                ),  # trailing section
            ),
            file_type="pdf",
        )
        assert structure is not None
        assert [(n.title, n.number) for n in structure.nodes] == [
            ("Introduction", "1"),
            ("Proxmox VE Storage", "7"),
            ("Backup and Restore", "8"),
            ("GNU Free Documentation License", None),
        ]
        assert not any(
            node.page_start is not None and 3 <= node.page_start <= 5
            for node in structure.nodes
        )
        assert structure.nodes[1].heading_path == "Chapter 7 — Proxmox VE Storage"
        assert structure.sources["toc_number_recovery"] is True
        assert sc._suppressed_entries_of(structure) == [
            {"title": "1 Introduction", "page": 3},
            {"title": "2 Installing Proxmox VE", "page": 4},
            {"title": "7 Proxmox VE Storage", "page": 5},
        ]
        assert scans == [path]  # one text-layer scan serves both passes

    def test_structure_meta_row_carries_the_suppression_json(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        path = tmp_path / "pve.pdf"
        monkeypatch.setattr(sc, "capture_pdf_outline", lambda p: None)
        monkeypatch.setattr(sc, "capture_page_labels", lambda p: _pve_labels())
        monkeypatch.setattr(
            sc,
            "extract_native_pdf_text",
            lambda p: [{"text": "7 Proxmox VE Storage .... 153", "page": 5}],
        )
        structure = capture_structure(
            path,
            docling_doc=docling_doc(
                doc_item("7 Proxmox VE Storage", level=1, page=5),  # ghost
                doc_item("Proxmox VE Storage", level=1, page=163),  # real 7
            ),
            file_type="pdf",
        )
        assert structure is not None

        store = StructureStore(db_path=str(tmp_path / "secondbrain.db"))
        try:
            store.save_structure(structure)
            row = (
                sqlite3.connect(str(tmp_path / "secondbrain.db"))
                .execute(
                    "SELECT sources FROM structure_meta WHERE source_file = ?",
                    (str(path),),
                )
                .fetchone()
            )
        finally:
            store.close()
        assert row is not None
        payload = json.loads(row[0])
        assert payload["heading_hierarchy"] is True
        # The suppressed candidates ride structure_meta verbatim as JSON.
        assert json.loads(payload[sc._META_SUPPRESSED_KEY]) == [
            {"page": 5, "title": "7 Proxmox VE Storage"}
        ]

    def test_merge_reattaches_combined_records(self, tmp_path: Any) -> None:
        # Page-windowed captures each suppress their own ghosts; the merge
        # re-attaches every part's record (the union skips the key).
        part_a = capture_docling_headings(
            docling_doc(
                doc_item("1 Introduction", level=1, page=3),  # ghost
                doc_item("Introduction", level=1, page=13),  # real chapter
            ),
            tmp_path / "book.pdf",
            toc_listings=[TocListing("1", "Introduction", 1, 1)],
            toc_page_span=(3, 4),
        )
        part_b = capture_docling_headings(
            docling_doc(
                doc_item("7 Proxmox VE Storage", level=1, page=4),  # ghost
                doc_item("Proxmox VE Storage", level=1, page=163),  # real 7
            ),
            tmp_path / "book.pdf",
            toc_listings=[TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 4),
        )
        assert part_a is not None and part_b is not None
        merged = merge_structures(part_a, part_b)
        assert sc._suppressed_entries_of(merged) == [
            {"title": "1 Introduction", "page": 3},
            {"title": "7 Proxmox VE Storage", "page": 4},
        ]
        assert isinstance(merged.sources[sc._META_SUPPRESSED_KEY], str)


# ---------------------------------------------------------------------------
# Printed-page mapping + collision refusal in recovery (task 3.2, D5)
# ---------------------------------------------------------------------------


class TestRecoveryPrintedPageMapping:
    """The recovery bound maps printed ToC pages through /PageLabels."""

    def test_pve_chapter_seven_recovers_through_printed_page_labels(self) -> None:
        # The brief: the ToC prints "7 Proxmox VE Storage … 153"; /PageLabels
        # place printed 153 on physical 163, where the real chapter 7 opens.
        merged = merge_structures(
            headings_part([(1, "Proxmox VE Storage", 163)], final_page=194)
        )
        merged.page_labels = _pve_labels()
        recovered = recover_chapter_numbers(
            merged,
            [TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 22),
        )
        (node,) = recovered.nodes
        assert node.number == "7"
        assert (node.page_start, node.page_end) == (163, 194)
        assert node.heading_path == "Chapter 7 — Proxmox VE Storage"
        assert recovered.sources["toc_number_recovery"] is True

    def test_span_ghost_stays_unnumbered_while_the_real_node_recovers(self) -> None:
        # A number-less ghost sitting inside the ToC span never takes the
        # row's number (headings captured from ToC-page text must not number
        # themselves); the real node at the mapped page does.
        merged = merge_structures(
            headings_part(
                [(1, "Proxmox VE Storage", 9), (1, "Proxmox VE Storage", 163)],
                final_page=194,
            )
        )
        merged.page_labels = _pve_labels()
        recovered = recover_chapter_numbers(
            merged,
            [TocListing("7", "Proxmox VE Storage", 153, 1)],
            toc_page_span=(3, 22),
        )
        by_page = {node.page_start: node for node in recovered.nodes}
        assert by_page[9].number is None  # inside the ToC span
        assert by_page[163].number == "7"


class TestRecoveryCollisionRefusal:
    """A recovered number is never doubled among same-scope siblings (D5)."""

    def test_second_same_number_sibling_is_refused(self) -> None:
        # Two leftover same-title ghosts with two "7 Storage" rows: the walk
        # recovers "7" once, then refuses the second assignment rather than
        # stamping the tree with two recovered 7s.
        merged = merge_structures(
            headings_part([(1, "Storage", 163), (1, "Storage", 165)], final_page=200)
        )
        merged.page_labels = _pve_labels()
        recovered = recover_chapter_numbers(
            merged,
            [
                TocListing("7", "Storage", 153, 1),  # -> 163: matches node 1
                TocListing("7", "Storage", 158, 1),  # -> 168: node 2's row
            ],
        )
        assert [node.number for node in recovered.nodes] == ["7", None]

    def test_parsed_sibling_number_does_not_block_recovery(self) -> None:
        # Anthology safety: a sibling's PARSED number is not this pass's
        # doing, so it never collides — parsed and recovered "1" coexist
        # (part restarts; the junk-desync test pins the same contract).
        merged = merge_structures(
            headings_part([(1, "1 Preamble", 5), (1, "Storage", 30)], final_page=60)
        )
        merged.page_labels = bound_labels()
        recovered = recover_chapter_numbers(
            merged,
            [TocListing("1", "Storage", 26, 1)],
        )
        by_title = {node.title: node for node in recovered.nodes}
        assert by_title["Preamble"].number == "1"  # parsed, untouched
        assert by_title["Storage"].number == "1"  # recovery may coexist
