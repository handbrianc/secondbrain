"""Unit tests for secondbrain.document.structure_capture (lane 1a)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from secondbrain.document import structure_capture as sc
from secondbrain.document.structure_capture import (
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
)
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    PageLabelRange,
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
    entries: list[tuple[int, str, int]],
    source_file: str = "/docs/book.pdf",
    allow_parts: bool = True,
    final_page: int | None = None,
) -> DocumentStructure:
    """Build a part through the real heading→node pipeline."""
    nodes = _build_nodes_from_headings(
        entries,
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
