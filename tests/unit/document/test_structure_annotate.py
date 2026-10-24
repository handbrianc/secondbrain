"""Unit tests for chunk structural annotation (task 8, design §7).

Covers the :func:`~secondbrain.document.structure_annotate.annotate_chunks`
contract: anchor by heading forms, inherit the deepest containing node,
``chapter_id``/``section_id``/``section_label`` derivation, audio
``t_start``/``t_end`` handling, add-only key semantics, and the
never-raises / never-mutates posture.
"""

from __future__ import annotations

from typing import Any

import pytest

from secondbrain.document.structure_annotate import (
    ANNOTATION_PAYLOAD_KEYS,
    annotate_chunks,
)
from secondbrain.storage.structure_sqlite import DocumentStructure, StructureNode

pytestmark = pytest.mark.unit


def node(
    node_id: str,
    *,
    parent: str | None = None,
    kind: str = "section",
    level: int = 2,
    number: str | None = None,
    title: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
    t_start: float | None = None,
    t_end: float | None = None,
    heading_path: str = "",
) -> StructureNode:
    return StructureNode(
        node_id=node_id,
        parent_id=parent,
        kind=kind,  # type: ignore[arg-type]
        level=level,
        number=number,
        title=title,
        page_start=page_start,
        page_end=page_end,
        t_start=t_start,
        t_end=t_end,
        heading_path=heading_path,
    )


def document_tree() -> DocumentStructure:
    """Chapter 5 with two numbered sections and one subsection."""
    return DocumentStructure(
        source_file="/tmp/book.pdf",
        nodes=[
            node(
                "ch05",
                kind="chapter",
                level=1,
                number="5",
                title="Installing",
                page_start=5,
                page_end=12,
                heading_path="Chapter 5 — Installing",
            ),
            node(
                "sec05.02",
                parent="ch05",
                number="5.2",
                title="Setup",
                page_start=7,
                page_end=9,
                heading_path="Chapter 5 — Installing > 5.2 Setup",
            ),
            node(
                "sec05.02.03",
                parent="sec05.02",
                level=3,
                number="5.2.3",
                title="First boot",
                page_start=8,
                page_end=9,
                heading_path="Chapter 5 — Installing > 5.2 Setup > 5.2.3 First boot",
            ),
            node(
                "sec05.04",
                parent="ch05",
                number="5.4",
                title="Tuning",
                page_start=10,
                page_end=12,
                heading_path="Chapter 5 — Installing > 5.4 Tuning",
            ),
        ],
        sources={"outline": True},
    )


def anthology_tree() -> DocumentStructure:
    """Part I over chapter 3: chapter_id resolves to the top-level part."""
    return DocumentStructure(
        source_file="/tmp/anthology.pdf",
        nodes=[
            node(
                "partI",
                kind="part",
                level=1,
                number="I",
                title="Part I — Beginnings",
                page_start=1,
                page_end=30,
                heading_path="Part I — Beginnings",
            ),
            node(
                "partI.3",
                parent="partI",
                kind="chapter",
                level=2,
                number="3",
                title="The Voyage",
                page_start=10,
                page_end=20,
                heading_path="Part I — Beginnings > Chapter 3 — The Voyage",
            ),
        ],
        sources={"outline": True},
    )


def audio_tree() -> DocumentStructure:
    return DocumentStructure(
        source_file="/tmp/talk.m4a",
        nodes=[
            node(
                "seg01",
                kind="segment",
                level=1,
                title="welcome everyone to the show",
                t_start=0.0,
                t_end=30.0,
                heading_path="Segment 01",
            ),
            node(
                "seg02",
                kind="segment",
                level=1,
                title="today we discuss rockets",
                t_start=30.0,
                t_end=60.0,
                heading_path="Segment 02",
            ),
        ],
        sources={"audio": True},
    )


def chunk(text: str, page: int = 1, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"text": text, "page": page}
    base.update(extra)
    return base


class TestAnchoring:
    """Chunks whose text starts with a node's heading forms anchor to it."""

    def test_dotted_number_anchors_to_section(self) -> None:
        chunks = [chunk("5.2 Setup " + "prose " * 40, page=7)]
        [out] = annotate_chunks(chunks, document_tree())
        assert out["node_id"] == "sec05.02"
        assert out["heading_path"] == "Chapter 5 — Installing > 5.2 Setup"
        assert out["section_id"] == "5.2"
        assert out["section_label"] == "Setup"

    def test_chapter_word_form_anchors_to_chapter(self) -> None:
        chunks = [chunk("Chapter 5 — Installing " + "prose " * 40, page=5)]
        [out] = annotate_chunks(chunks, document_tree())
        assert out["node_id"] == "ch05"
        assert out["chapter_id"] == "5"

    def test_number_title_form_anchors_to_chapter(self) -> None:
        chunks = [chunk("5 Installing " + "prose " * 40, page=5)]
        [out] = annotate_chunks(chunks, document_tree())
        assert out["node_id"] == "ch05"

    def test_unnumbered_title_anchors(self) -> None:
        tree = DocumentStructure(
            source_file="/tmp/book.pdf",
            nodes=[
                node(
                    "ch-intro",
                    kind="chapter",
                    level=1,
                    title="Introduction",
                    page_start=1,
                    page_end=4,
                    heading_path="Introduction",
                )
            ],
        )
        [out] = annotate_chunks([chunk("Introduction " + "prose " * 40, page=1)], tree)
        assert out["node_id"] == "ch-intro"
        assert out["chapter_id"] == "ch-intro"
        assert "section_id" not in out  # no numbered ancestor anywhere

    def test_anchor_requires_word_boundary(self) -> None:
        chunks = [chunk("5.23 Not this section " + "prose " * 40, page=10)]
        [out] = annotate_chunks(chunks, document_tree())
        # "5.2 Setup" must not match "5.23 ..."; the chunk falls through to
        # the deepest containing node (5.4 Tuning covers page 10).
        assert out["node_id"] == "sec05.04"

    def test_numbered_node_ignores_bare_title_match(self) -> None:
        chunks = [chunk("Tuning " + "prose " * 40, page=10)]
        [out] = annotate_chunks(chunks, document_tree())
        # Bare "Tuning" does not anchor to numbered section 5.4; inherit wins.
        assert out["node_id"] == "sec05.04"
        assert out["section_id"] == "5.4"


class TestInheritance:
    """Chunks without a heading anchor inherit the deepest containing node."""

    def test_mid_section_chunk_inherits_deepest(self) -> None:
        chunks = [chunk("more first-boot prose " * 30, page=8)]
        [out] = annotate_chunks(chunks, document_tree())
        assert out["node_id"] == "sec05.02.03"
        assert out["section_id"] == "5.2.3"
        assert out["section_label"] == "First boot"

    def test_chunk_before_any_node_gets_no_keys(self) -> None:
        chunks = [chunk("front matter prose " * 30, page=1)]
        [out] = annotate_chunks(chunks, document_tree())
        assert "node_id" not in out
        assert not (set(out) & set(ANNOTATION_PAYLOAD_KEYS))

    def test_unknown_page_gets_no_keys(self) -> None:
        [out] = annotate_chunks([chunk("prose " * 40, page=0)], document_tree())
        assert "node_id" not in out

    def test_missing_page_key_gets_no_keys(self) -> None:
        [out] = annotate_chunks([{"text": "prose " * 40}], document_tree())
        assert "node_id" not in out


class TestDerivedIds:
    """chapter_id / section_id / section_label derivation rules."""

    def test_chapter_chunk_carries_chapter_number_as_section_id(self) -> None:
        chunks = [chunk("5 Installing " + "prose " * 40, page=5)]
        [out] = annotate_chunks(chunks, document_tree())
        # The chapter itself is the nearest numbered non-part ancestor-or-self.
        assert out["chapter_id"] == "5"
        assert out["section_id"] == "5"
        assert out["section_label"] == "Installing"

    def test_anthology_chapter_id_is_the_part(self) -> None:
        chunks = [chunk("3 The Voyage " + "prose " * 40, page=10)]
        [out] = annotate_chunks(chunks, anthology_tree())
        # design §7: chapter_id is the TOP-LEVEL ancestor's number.
        assert out["chapter_id"] == "I"
        assert out["section_id"] == "3"  # parts are excluded from section walk
        assert out["section_label"] == "The Voyage"

    def test_unnumbered_chain_omits_section_keys(self) -> None:
        tree = DocumentStructure(
            source_file="/tmp/book.pdf",
            nodes=[
                node(
                    "ch-front",
                    kind="chapter",
                    level=1,
                    title="Front matter",
                    page_start=1,
                    page_end=9,
                    heading_path="Front matter",
                ),
                node(
                    "sec-preface",
                    parent="ch-front",
                    title="Preface",
                    page_start=2,
                    page_end=3,
                    heading_path="Front matter > Preface",
                ),
            ],
        )
        [out] = annotate_chunks([chunk("preface prose " * 30, page=2)], tree)
        assert out["node_id"] == "sec-preface"
        assert out["chapter_id"] == "ch-front"
        assert "section_id" not in out
        assert "section_label" not in out


class TestAudioTimeMode:
    """Audio trees annotate through the chunk's optional t_start/t_end keys."""

    def test_anchor_and_inherit_by_time_range(self) -> None:
        chunks = [
            chunk(
                "welcome everyone to the show and stay tuned",
                page=0,
                t_start=1.0,
                t_end=2.0,
            ),
            chunk("other rambling prose " * 20, page=0, t_start=40.0, t_end=41.0),
        ]
        outs = annotate_chunks(chunks, audio_tree())
        assert outs[0]["node_id"] == "seg01"
        assert outs[0]["t_start"] == 0.0
        assert outs[0]["t_end"] == 30.0
        assert outs[1]["node_id"] == "seg02"

    def test_chunk_without_time_keys_stays_unannotated(self) -> None:
        # Real ingest chunks carry no t keys today: without a usable position
        # the chunk stays refreshable instead of inheriting a wrong segment.
        [out] = annotate_chunks([chunk("welcome everyone", page=0)], audio_tree())
        assert "node_id" not in out

    def test_page_mode_ignores_time_spans_and_vice_versa(self) -> None:
        # A page-positioned chunk must never inherit an audio (time) node.
        [out] = annotate_chunks([chunk("welcome everyone", page=1)], audio_tree())
        assert "node_id" not in out


class TestAddOnlySemantics:
    """Annotation only adds keys; input is never mutated; never raises."""

    def test_existing_keys_and_unknown_keys_are_preserved(self) -> None:
        original = chunk(
            "5.2 Setup " + "prose " * 40,
            page=7,
            chunk_role="heading",
            text_hash="abc123",
            custom_field={"keep": "me"},
        )
        [out] = annotate_chunks([original], document_tree())
        assert out["chunk_role"] == "heading"
        assert out["text_hash"] == "abc123"
        assert out["custom_field"] == {"keep": "me"}
        assert out["text"] == original["text"]
        assert out["page"] == 7

    def test_input_is_never_mutated(self) -> None:
        original = chunk("5.2 Setup " + "prose " * 40, page=7)
        snapshot = dict(original)
        outs = annotate_chunks([original], document_tree())
        assert outs[0] is not original
        assert original == snapshot
        assert "node_id" not in original

    def test_broken_input_never_raises(self) -> None:
        # No text key, hostile page values — copies come back, no exception.
        hostile: list[dict[str, Any]] = [
            {"page": "not-a-number"},
            {"text": None, "page": 7},  # empty text: no anchor, but inherits
        ]
        outs = annotate_chunks(hostile, document_tree())
        assert len(outs) == 2
        assert "node_id" not in outs[0]
        assert outs[1]["node_id"] == "sec05.02"  # deepest node containing page 7

    def test_empty_tree_and_empty_chunks(self) -> None:
        empty = DocumentStructure(source_file="/tmp/none.pdf", nodes=[])
        assert annotate_chunks([], document_tree()) == []
        outs = annotate_chunks([chunk("prose", page=7)], empty)
        assert outs == [{"text": "prose", "page": 7}]

    def test_results_are_order_independent_for_nested_trees(self) -> None:
        """The containment filter matches per chunk, so batching is safe.

        This is the property the qdrant refresh relies on when it feeds
        arbitrary scroll batches through annotate_chunks.
        """
        chunks = [
            chunk("5.2 Setup " + "prose " * 40, page=7),
            chunk("mid prose " * 30, page=8),
            chunk("5.4 Tuning " + "prose " * 40, page=10),
            chunk("tail prose " * 30, page=12),
        ]
        forward = annotate_chunks(chunks, document_tree())
        reversed_chunks = list(reversed(chunks))
        backward = annotate_chunks(reversed_chunks, document_tree())
        assert [dict(c) for c in forward] == [dict(c) for c in reversed(backward)]
