"""Role-change regression tests for the chunker (task 7, lane 1b).

Pins the contract points of design §7 / §9 trap 1:

* the section-numbered → ``body`` downgrade is gone: dotted headings
  classify as ``heading`` on both the title and the statistical path
  (production callers compute ``is_likely_title`` with a dot-rejecting
  inline heuristic, so dotted titles always take the statistical path);
* single-segment gate (refinement): the statistical-path dotted→heading
  guard applies ONLY to single segments — merged multi-segment openers
  (title + body accumulated by the merge policy) keep ``body`` so
  chapter-content consumers (summarizer.py:380,399) lose no content;
* the chunk TEXT streams are byte-identical before/after the role change —
  the merge policy never consults roles, so ``text_hash`` dedup keeps every
  stored point valid.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import pytest

from secondbrain.document import Segment
from secondbrain.document import chunker as chunker_module
from secondbrain.document.chunker import chunk_segments, classify_chunk_role

pytestmark = pytest.mark.unit

CHUNK_SIZE = 120
OVERLAP = 20


def _seg(text: str, page: int = 1) -> Segment:
    return {"text": text, "page": page}


def legacy_classify_chunk_role(
    text: str,
    seg_count: int,
    total_segs: int,
    is_likely_title: bool,
    *,
    is_merged_segment: bool = False,
    source_text: str | None = None,
) -> str:
    """The pre-task-7 classifier (downgrade + no statistical section check).

    Accepts — and ignores — ``is_merged_segment`` so the production call
    shape (``chunk_segments`` now passes merge provenance) keeps working:
    the legacy behavior predates the merge-provenance gate.
    """
    if is_likely_title:
        pos = seg_count / max(total_segs, 1)
        if pos < 0.025:
            return "navigation"
        if re.match(r"\d+\.\d+(\.\d+)?\s", text):
            return "body"
        return "heading"

    pos = seg_count / max(total_segs, 1)
    if pos < 0.025:
        return "navigation"

    total = len(text)
    if total == 0:
        return "body"
    alpha = sum(c.isalpha() for c in text)
    char_density = alpha / total
    dot_chain_density = text.count(" . ") / total
    if dot_chain_density > 0.055:
        return "toc_entry"
    if char_density < 0.48:
        return "caption"
    return "body"


BODY_TEXT = (
    "The autostart service launches configured agents when the system "
    "boots and restarts them after failures. Configuration lives under "
    "etc autostart and is reloaded on change without a daemon restart. "
)


def fixture_segments() -> list[Segment]:
    """A mixed document: dotted headings, body, TOC dots, caption, footer.

    The trailing "11.20" segment ends the document, so the merge policy
    flushes it alone — a single dotted-led chunk (the only shape the
    dotted→heading guard applies to after the refinement).
    """
    return [
        _seg("Chapter 11 Services", page=1),
        _seg(BODY_TEXT * 2, page=2),
        _seg("11.18 Configuring the Autostart Service", page=3),
        _seg(BODY_TEXT * 2, page=4),
        _seg("11.19 Diagnostics . . . . . . . . . . . . . . . . . 402", page=5),
        _seg("Figure 3: autostart retry curve", page=6),
        _seg(BODY_TEXT, page=7),
        _seg("11.20 Rollback procedure", page=8),
    ]


class TestClassifyChunkRoleSectionNumbers:
    """The dotted-heading role fix (task 7)."""

    def test_dotted_title_on_statistical_path_is_heading(self) -> None:
        # is_likely_title=False is what production callers pass for dotted
        # text: their inline title heuristic rejects the dot in the number.
        assert (
            classify_chunk_role(
                "11.18 Configuring the Autostart Service", 5, 100, False
            )
            == "heading"
        )

    def test_dotted_title_on_title_path_is_heading(self) -> None:
        # The former downgrade (→ "body") is removed.
        assert (
            classify_chunk_role("11.18 Configuring the Autostart Service", 5, 100, True)
            == "heading"
        )

    def test_navigation_still_wins_in_the_leading_sliver(self) -> None:
        assert classify_chunk_role("11.18 Configuring", 0, 100, False) == "navigation"
        assert classify_chunk_role("11.18 Configuring", 0, 100, True) == "navigation"

    def test_plain_title_still_heading(self) -> None:
        assert classify_chunk_role("Overview of services", 5, 100, True) == "heading"

    @pytest.mark.parametrize(
        "text",
        [
            "11.18 Configuring the Autostart Service\n" + BODY_TEXT,
            "11.18 Configuring the Autostart Service " + BODY_TEXT,
            "11.18 This is prose, not a heading.",
        ],
    )
    def test_unmerged_page_with_dotted_opener_keeps_body(self, text: str) -> None:
        assert classify_chunk_role(text, 5, 100, False) == "body"

    def test_split_page_opener_uses_full_segment_evidence(self) -> None:
        heading = "11.18 Configuring the Autostart Service"
        assert (
            classify_chunk_role(
                heading, 5, 100, False, source_text=heading + "\n" + BODY_TEXT
            )
            == "body"
        )

    def test_native_page_leading_chunk_keeps_body(self) -> None:
        chunks = chunk_segments(
            [
                _seg(BODY_TEXT * 2),
                _seg("11.18 Configuring the Autostart Service\n" + BODY_TEXT * 3, 2),
            ],
            70,
            0,
        )
        opener = next(c for c in chunks if c["text"].startswith("11.18"))
        assert opener["chunk_role"] == "body"

    def test_statistical_classes_unchanged_for_non_dotted_text(self) -> None:
        assert classify_chunk_role("a . b . c . " * 20, 5, 100, False) == "toc_entry"
        assert classify_chunk_role("12345 67890 " * 20, 5, 100, False) == "caption"
        assert classify_chunk_role("Plain body prose. " * 20, 5, 100, False) == "body"


class TestTextStreamByteIdentity:
    """chunk text/page streams are identical with the legacy vs new classifier."""

    @pytest.mark.parametrize("chunk_size,overlap", [(120, 20), (4096, 200), (37, 5)])
    def test_streams_identical_to_legacy_classifier(
        self, monkeypatch: pytest.MonkeyPatch, chunk_size: int, overlap: int
    ) -> None:
        segments = fixture_segments()

        monkeypatch.setattr(
            chunker_module, "classify_chunk_role", legacy_classify_chunk_role
        )
        legacy_chunks = chunk_segments(segments, chunk_size, overlap)
        legacy_stream = [(c["text"], c["page"]) for c in legacy_chunks]

        monkeypatch.setattr(chunker_module, "classify_chunk_role", classify_chunk_role)
        new_chunks = chunk_segments(segments, chunk_size, overlap)
        new_stream = [(c["text"], c["page"]) for c in new_chunks]

        assert legacy_chunks, "fixture must produce chunks"
        assert new_stream == legacy_stream

    def test_roles_actually_change_on_dotted_openers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The invariance above is meaningful: roles DO change somewhere.

        After the single-segment gate: the MERGED 11.18 opener keeps ``body``
        under both classifiers (no content churn for summarizer-style
        filters); the SINGLE trailing 11.20 chunk flips ``body`` → ``heading``
        (the intended task-7 change survives for lone dotted headings).
        """
        segments = fixture_segments()

        monkeypatch.setattr(
            chunker_module, "classify_chunk_role", legacy_classify_chunk_role
        )
        legacy_chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)
        legacy_roles = {c["text"]: c["chunk_role"] for c in legacy_chunks}
        monkeypatch.setattr(chunker_module, "classify_chunk_role", classify_chunk_role)
        new_chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)
        new_roles = [c["chunk_role"] for c in new_chunks]

        assert new_roles != list(legacy_roles.values())
        for chunk, role in zip(new_chunks, new_roles, strict=True):
            if chunk["text"].startswith("11.18"):
                # Merged opener: dotted-led but multi-segment → stays "body",
                # identical to the legacy classifier (no role churn).
                assert role == "body"
                assert legacy_roles[chunk["text"]] == "body"
            if chunk["text"].startswith("11.20"):
                # Single segment: the guard applies.
                assert role == "heading"
                assert legacy_roles[chunk["text"]] == "body"

    def test_merge_input_independent_of_roles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The merge policy never consults roles: its input is role-free."""
        real_merge = chunker_module._merge_segments
        merge_inputs: list[list[Any]] = []

        def spying_merge(segments: Sequence[Segment]) -> list[Any]:
            merge_inputs.append([dict(segment) for segment in real_merge(segments)])
            return real_merge(segments)

        monkeypatch.setattr(chunker_module, "_merge_segments", spying_merge)

        monkeypatch.setattr(
            chunker_module, "classify_chunk_role", legacy_classify_chunk_role
        )
        chunk_segments(fixture_segments(), CHUNK_SIZE, OVERLAP)
        monkeypatch.setattr(chunker_module, "classify_chunk_role", classify_chunk_role)
        chunk_segments(fixture_segments(), CHUNK_SIZE, OVERLAP)

        assert len(merge_inputs) == 2  # merge ran once per chunk_segments call
        assert merge_inputs[0] == merge_inputs[1]


class TestMergedOpenerSingleSegmentGate:
    """The refinement: the dotted→heading guard sees only single segments.

    ``_merge_segments`` records merge provenance on each produced segment
    (``merged=True`` when ≥2 raw segments were joined); ``chunk_segments``
    passes it as ``is_merged_segment``. Merged openers (dotted title + body)
    fall through to the statistical path → ``body`` as before the task-7
    role fix, so summarizer.py's chapter-content filter loses no chunks.
    """

    def test_merged_opener_direct_is_body(self) -> None:
        assert (
            classify_chunk_role(
                "11.18 Configuring the Autostart Service The autostart service",
                5,
                100,
                False,
                is_merged_segment=True,
            )
            == "body"
        )

    def test_single_segment_direct_is_heading(self) -> None:
        # Explicit single-segment form of the statistical-path gate.
        assert (
            classify_chunk_role(
                "11.18 Configuring the Autostart Service",
                5,
                100,
                False,
                is_merged_segment=False,
            )
            == "heading"
        )

    def test_merged_opener_end_to_end_is_body_and_role_stable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dotted title merged with body classifies 'body' — as pre-fix."""
        # A preceding segment gives the opener a non-zero position (the
        # leading-sliver navigation heuristic would otherwise decide first).
        segments = [
            _seg("Intro paragraph for positioning.", page=1),
            _seg("11.18 Configuring the Autostart Service", page=2),
            _seg(BODY_TEXT * 2, page=2),
        ]
        chunks = chunk_segments(segments, 4096, 200)
        openers = [c for c in chunks if c["text"].startswith("11.18")]
        assert openers, "the merged opener must produce a chunk"
        assert all(c["chunk_role"] == "body" for c in openers)

        # Role stability: the legacy classifier returns 'body' for the same
        # text — the refinement introduces no churn for merged openers.
        monkeypatch.setattr(
            chunker_module, "classify_chunk_role", legacy_classify_chunk_role
        )
        legacy_roles = {
            c["text"]: c["chunk_role"] for c in chunk_segments(segments, 4096, 200)
        }
        assert all(legacy_roles[c["text"]] == "body" for c in openers)

    def test_single_dotted_chunk_end_to_end_is_heading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A lone dotted heading (no body joined) classifies 'heading'."""
        segments = [
            _seg("Chapter 11 Services", page=1),
            _seg("11.18 Configuring the Autostart Service", page=2),
        ]
        chunks = chunk_segments(segments, 4096, 200)
        dotted = [c for c in chunks if c["text"].startswith("11.18")]
        assert len(dotted) == 1
        assert dotted[0]["chunk_role"] == "heading"

        # The legacy classifier says 'body' for the same text: the guard is
        # the only difference (text streams are byte-identical either way).
        monkeypatch.setattr(
            chunker_module, "classify_chunk_role", legacy_classify_chunk_role
        )
        legacy_chunks = chunk_segments(segments, 4096, 200)
        legacy_dotted = [c for c in legacy_chunks if c["text"].startswith("11.18")]
        assert legacy_dotted[0]["chunk_role"] == "body"
        assert legacy_dotted[0]["text"] == dotted[0]["text"]
