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


def sibling_section_tree() -> DocumentStructure:
    """ch05 whose 5.2 (pages 7-9) and 5.4 (pages 9-11) share page 9."""
    return DocumentStructure(
        source_file="/books/siblings.pdf",
        nodes=[
            node(
                "ch05",
                kind="chapter",
                level=1,
                number="5",
                title="Installing",
                page_start=5,
                page_end=12,
            ),
            node(
                "sec05.02",
                parent="ch05",
                number="5.2",
                title="Setup",
                page_start=7,
                page_end=9,
            ),
            node(
                "sec05.04",
                parent="ch05",
                number="5.4",
                title="Tuning",
                page_start=9,
                page_end=11,
            ),
        ],
    )


def ambiguous_page_tree() -> DocumentStructure:
    """Page 7 is shared by sibling sections 5.2 and 5.3 (chain-inconsistent)."""
    return DocumentStructure(
        source_file="/books/ambiguous.pdf",
        nodes=[
            node(
                "ch05",
                kind="chapter",
                level=1,
                number="5",
                title="Installing",
                page_start=5,
                page_end=12,
            ),
            node(
                "sec05.02",
                parent="ch05",
                number="5.2",
                title="Setup",
                page_start=7,
                page_end=9,
            ),
            node(
                "sec05.03",
                parent="ch05",
                number="5.3",
                title="Ignition",
                page_start=7,
                page_end=8,
            ),
            node(
                "sec05.04",
                parent="ch05",
                number="5.4",
                title="Tuning",
                page_start=9,
                page_end=11,
            ),
        ],
    )


def chunk(text: str, page: int = 1, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"text": text, "page": page}
    base.update(extra)
    return base


class TestSharedPageOwnership:
    @staticmethod
    def _tree() -> DocumentStructure:
        return DocumentStructure(
            source_file="/books/shared-page.pdf",
            nodes=[
                node(
                    "ch05",
                    kind="chapter",
                    level=1,
                    number="5",
                    title="Installing",
                    page_start=5,
                    page_end=11,
                ),
                node(
                    "ch06",
                    kind="chapter",
                    level=1,
                    number="6",
                    title="Operations",
                    page_start=11,
                    page_end=20,
                ),
                node(
                    "sec06.01",
                    parent="ch06",
                    number="6.1",
                    title="Maintenance",
                    page_start=11,
                    page_end=12,
                ),
            ],
        )

    def test_shared_page_body_is_not_assigned_to_later_branch(self) -> None:
        chunks = [
            chunk("closing prose from the installation chapter", page=11),
            chunk("Chapter 6 Operations", page=11),
            chunk("unanchored prose after the next chapter heading", page=11),
        ]

        outputs = annotate_chunks(chunks, self._tree())

        assert "node_id" not in outputs[0]
        assert outputs[1]["node_id"] == "ch06"
        assert "node_id" not in outputs[2]
        assert "node_id" not in chunks[1]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Chapter 5 Installing", "ch05"),
            ("Chapter 6 Operations", "ch06"),
            ("6.1 Maintenance", "sec06.01"),
        ],
    )
    def test_shared_page_explicit_anchor_stays_authoritative(
        self, text: str, expected: str
    ) -> None:
        [out] = annotate_chunks([chunk(text, page=11)], self._tree())

        assert out["node_id"] == expected

    def test_nested_containment_outside_shared_page_still_inherits(self) -> None:
        [out] = annotate_chunks(
            [chunk("ordinary maintenance prose", page=12)], self._tree()
        )

        assert out["node_id"] == "sec06.01"
        assert out["chapter_id"] == "6"


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
        assert outs[0]["t_start"] == 1.0
        assert outs[0]["t_end"] == 2.0
        assert outs[1]["node_id"] == "seg02"
        assert (outs[1]["t_start"], outs[1]["t_end"]) == (40.0, 41.0)

    def test_chunk_without_time_keys_stays_unannotated(self) -> None:
        # Without a usable position, the chunk stays refreshable instead of
        # inheriting a wrong segment.
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

        This is the unordered (default) property: chunk order does not
        matter for well-formed trees. Ordered mode deliberately trades it
        for reading-order disambiguation, so only callers that walk chunks
        in reading order (or sort first, like the qdrant refresh) may pass
        ``ordered=True``.
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


class TestOrderedStickyInheritance:
    """ordered=True carries the previous target as a sticky owner (design D2).

    Only page mode: the sticky owner must resolve the same-page sibling
    ambiguity, never misfire on oscillating pages, and stay off for audio
    (time mode) trees. The unordered default keeps today's behavior.
    """

    def test_unanchored_body_after_second_heading_inherits_it(self) -> None:
        chunks = [
            chunk("5.2 Setup " + "prose " * 40, page=7),
            chunk("5.4 Tuning " + "prose " * 40, page=9),
            chunk("tuning body prose " * 20, page=9),
        ]
        ordered = annotate_chunks(chunks, sibling_section_tree(), ordered=True)
        unordered = annotate_chunks(chunks, sibling_section_tree())

        # Anchors resolve identically in both modes ...
        assert ordered[0]["node_id"] == "sec05.02"
        assert ordered[0] == unordered[0]
        # page 9 lies in both sections' ranges; only 5.4's heading forms match.
        assert ordered[1]["node_id"] == "sec05.04"
        assert ordered[1] == unordered[1]
        # ... but the unanchored body chunk annotates only in ordered mode:
        # the sticky owner (5.4) beats the same-page bail-out.
        assert ordered[2]["node_id"] == "sec05.04"
        assert ordered[2]["section_id"] == "5.4"
        assert ordered[2]["chapter_id"] == "5"
        assert "node_id" not in unordered[2]  # default behavior unchanged

    def test_oscillating_page_does_not_inherit_the_stale_owner(self) -> None:
        chunks = [
            chunk("5.4 Tuning " + "prose " * 40, page=9),
            chunk("setup prose before its heading " * 10, page=7),
        ]
        ordered = annotate_chunks(chunks, ambiguous_page_tree(), ordered=True)
        unordered = annotate_chunks(chunks, ambiguous_page_tree())

        assert ordered[0]["node_id"] == "sec05.04"
        # The sticky owner (5.4, pages 9-11) does NOT contain page 7, so it
        # must NOT be inherited (design D2 rule 2). Ordered mode still
        # resolves via the most-recent-start candidate (rule 3): among the
        # page-7 containers the last-started sibling is 5.3 — containment-
        # bounded, never the stale owner. The unordered call keeps today's
        # same-page bail-out.
        assert ordered[1]["node_id"] == "sec05.03"
        assert ordered[1]["node_id"] != "sec05.04"
        assert "node_id" not in unordered[1]  # default behavior unchanged

    def test_unanchored_first_chunk_inherits_most_recent_start(self) -> None:
        # No sticky owner exists yet (first chunk) — ordered mode resolves
        # through the most-recent-start candidate instead of bailing (D2
        # rule 3); page 9's containers are 5.2 (starts 7) and 5.4 (starts 9).
        chunks = [chunk("orphan body prose " * 20, page=9)]
        ordered = annotate_chunks(chunks, sibling_section_tree(), ordered=True)
        unordered = annotate_chunks(chunks, sibling_section_tree())

        assert ordered[0]["node_id"] == "sec05.04"  # most-recent start (page 9)
        assert "node_id" not in unordered[0]  # unordered keeps the bail-out

    def test_sticky_owner_survives_unannotated_gaps(self) -> None:
        chunks = [
            chunk("5.2 Setup " + "prose " * 40, page=7),
            chunk("orphan prose on an unknown page " * 10, page=99),
            chunk("still setup prose " * 20, page=9),  # page 9: 5.2 + 5.4 overlap
        ]
        outs = annotate_chunks(chunks, sibling_section_tree(), ordered=True)

        assert outs[0]["node_id"] == "sec05.02"
        assert "node_id" not in outs[1]  # the gap gets no keys, stays refreshable
        # The owner is NOT reset by the unannotated gap: containment is
        # re-checked per chunk, and 5.2's range still contains page 9.
        assert outs[2]["node_id"] == "sec05.02"

    def test_time_mode_never_applies_the_sticky_rule(self) -> None:
        chunks = [
            chunk(
                "welcome everyone to the show and stay tuned",
                page=0,
                t_start=0.0,
                t_end=1.0,
            ),
            chunk("rambling prose " * 20, page=0, t_start=30.0, t_end=31.0),
        ]
        ordered = annotate_chunks(chunks, audio_tree(), ordered=True)
        unordered = annotate_chunks(chunks, audio_tree())

        assert ordered[0]["node_id"] == "seg01"  # anchor, as today
        # t=30 is contained by BOTH segments; the deepest-wins rule picks
        # seg02. A sticky owner (seg01) would be wrong — ordered mode must
        # not apply it in time mode (audio annotation stays stateless).
        assert ordered[1]["node_id"] == "seg02"
        assert ordered == unordered

    def test_ordered_annotation_only_adds_keys_and_never_mutates(self) -> None:
        anchored = chunk(
            "5.2 Setup " + "prose " * 40,
            page=7,
            text_hash="abc123",
            custom_field={"keep": "me"},
        )
        body = chunk("setup body prose " * 20, page=8)
        snapshots = [dict(anchored), dict(body)]

        outs = annotate_chunks([anchored, body], sibling_section_tree(), ordered=True)

        assert [dict(c) for c in (anchored, body)] == snapshots  # inputs untouched
        assert outs[0] is not anchored
        assert outs[1] is not body
        # Existing and unknown keys are preserved; only annotation keys appear.
        assert outs[0]["text_hash"] == "abc123"
        assert outs[0]["custom_field"] == {"keep": "me"}
        assert outs[0]["page"] == 7
        assert outs[1]["node_id"] == "sec05.02"  # sticky inheritance
        assert set(outs[1]) - set(body) <= set(ANNOTATION_PAYLOAD_KEYS)
