"""Chapter bucket label integrity: identity, guard, roster note, wrapper.

Covers the ``chapter-label-integrity`` change end to end at the unit level,
plus the query-time roster hygiene of ``fix-chapter-evidence-fidelity``
(designs D5/D6):

- ``_StructureMixin._chunk_section_marker`` (design D3-r2) reads a bucket
  chunk's chapter identity from its own payload in a fixed priority order,
  first hit wins: the ingest-time structured fields ``section_id`` /
  ``chapter_id`` / ``heading_path`` first (no page floor -- they are
  ingest-time evidence), then the heading-shaped ``N.M`` text marker with
  its own front-matter page floor (``_BUCKET_MARKER_MIN_PAGE``: only the
  title/ToC pages 1-2 are skipped, design D5) plus the dot-leader and
  trailing-page guards of ``_detect_chapter_openings``.  It is a module-level
  staticmethod, callable without instantiating the pipeline.
- ``_derive_chapter_numbers`` pass 2 (design D6) captures roster titles at
  line boundaries: a numbered line with no title on its own line never
  matches (B2-r1 on-line anchor) except the shipped banner carve-out (B2-r2:
  a number line directly above a dotted ``N.M`` section heading keeps the
  chapter, title-less, via the same dotted-section guard), at most one
  continuation line joins the heading line, the 80-char budget cuts at a
  word boundary, source-register citation rows are rejected without
  consuming the seen slot, and the first-word article ban carries the
  D6-r3 carve-out (dot-shaped, colon-bearing "The …" titles claim their
  chapter; license/boilerplate headers stay rejected).
- ``_generate_multi_chapter_summary``'s pre-loop guard pass (design D2/D4)
  reassigns chunks whose identity names a rostered chapter, drops chunks
  whose identity names an unrostered one, extends the empty-bucket
  placeholder with a deterministic reason line (design D5), and leaves
  clean buckets -- and therefore the stored-tree path -- byte-identical.
- The roster-gap coverage note (design D5) names the chapter numbers a
  partial enumeration did not locate, streamed through the same ``_on_chunk``
  channel as the chapter headings so streamed == stored byte-identically.
- ``_generate_multi_chapter_summary_with_coverage`` (design D1-r2) runs the
  guard once over the full roster before its per-chapter delegations,
  emits the placeholder plus reason line for guard-emptied chapters itself,
  and appends the coverage note exactly once for the whole overview.

Funnel and wrapper tests drive the real generator with hand-rolled provider
doubles and a streaming capture, mirroring ``test_pipeline_streaming_guards.py``
/ ``test_pipeline_fallbacks.py``; no mocks at the domain layer.
"""

from __future__ import annotations

from typing import Any

from secondbrain.document import heading_forms
from secondbrain.rag.pipeline._fallback_mixin import (
    _GUARD_DROPPED_NOTE,
    _GUARD_REASSIGNED_NOTE,
    _ROSTER_COVERAGE_NOTE,
)
from secondbrain.rag.pipeline._structure_mixin import _StructureMixin
from tests.unit.rag.test_pipeline_streaming_guards import (
    _PLAUSIBLE,
    _CallbackCapture,
    _make_pipeline,
    _StreamedProvider,
)


def _marker_chunk(text: str, page: int = 100) -> dict[str, Any]:
    """Body-chunk double for the marker extractor (page defaults past the floor)."""
    return {"chunk_text": text, "page_number": page, "source_file": "a.pdf"}


class TestChunkSectionMarker:
    """D3 heading-shaped ``N.M`` extraction with the chapter-opener guards."""

    def test_positive_heading_line_extracts_prefix(self) -> None:
        chunk = _marker_chunk("7.1 Walking skeleton overview\nBody prose follows.")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_marker_on_second_line_after_page_marker(self) -> None:
        # Magazine-style openings put the heading one line after the printed
        # page marker ("[ 591 ]"), exactly the shape _detect_chapter_openings
        # recovers -- the marker must be found there too.
        chunk = _marker_chunk("[ 591 ]\n7.1 Walking skeleton overview")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_marker_on_second_line_after_plain_prose(self) -> None:
        chunk = _marker_chunk("Carried-over paragraph text.\n7.2 Next heading here")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_dot_leader_toc_row_rejected(self) -> None:
        chunk = _marker_chunk("7.1 Walking skeleton . . . . . . . . 591")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_trailing_bare_page_number_rejected(self) -> None:
        # A line ENDING in a bare number is ToC-row-like even without a
        # dot-leader run; digits inside the heading text are fine.
        chunk = _marker_chunk("7.1 Walking skeleton overview 591")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_inline_prose_mention_not_matched(self) -> None:
        # Line-anchored shape: prose that merely mentions a chapter number
        # ("in chapter 7 we discuss") or an inline "7.1" never matches.
        for text in (
            "in chapter 7 we discuss the walking skeleton and related ideas",
            "The design in chapter 7.1 walks through the build step by step.",
        ):
            assert _StructureMixin._chunk_section_marker(_marker_chunk(text)) is None

    def test_numbered_list_item_shape_not_matched(self) -> None:
        # A list step carries no second digit group, so the N.M shape itself
        # rejects it (design D3: the pattern is line-anchored at N.M).
        chunk = _marker_chunk("1. Walk through the setup steps carefully now")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_front_matter_pages_below_floor_skipped(self) -> None:
        # fix-chapter-evidence-fidelity D5: the marker's front-matter floor
        # dropped from page < 20 to page < 3 -- only the title/ToC pages 1-2
        # are skipped now (the dot-leader and trailing-page guards carry the
        # real noise defense).  _detect_chapter_openings' own page < 20 skip
        # is unchanged.
        for page in (1, 2):
            chunk = _marker_chunk("7.1 Walking skeleton overview", page=page)
            assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_page_10_marker_applies(self) -> None:
        # Page 10 sits above the floor: the heading-shaped marker applies
        # where the old page < 20 floor would have skipped it.
        chunk = _marker_chunk("7.1 Walking skeleton overview", page=10)
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_page_2_dot_leader_row_still_refused(self) -> None:
        # A page-2 ToC row stays refused: the dot-leader guard carries the
        # noise defense at any page (see the page-100 twin above), so the
        # lowered floor does not let ToC rows through.
        chunk = _marker_chunk("7.1 Walking skeleton . . . . . . . . 591", page=2)
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_no_marker_chunk_returns_none(self) -> None:
        chunk = _marker_chunk("Plain body prose with no heading-shaped opening.")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_bare_number_without_heading_text_rejected(self) -> None:
        # The pattern requires a non-space after the N.M prefix, so a bare
        # "7.1" line (a page stub) is not a heading.
        assert _StructureMixin._chunk_section_marker(_marker_chunk("7.1")) is None

    def test_out_of_range_prefix_rejected(self) -> None:
        # Chapter numbers stay in the module-wide 1..30 range.
        chunk = _marker_chunk("45.2 Far outside the chapter range")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_overlong_line_rejected(self) -> None:
        # Wrapped prose longer than any real heading is not one, no matter
        # how its first line begins (_BUCKET_MARKER_MAX_HEADING_CHARS).
        chunk = _marker_chunk("7.1 " + "word " * 40)
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_missing_fields_tolerated(self) -> None:
        # Defensive mirrors of _detect_chapter_openings: absent/None fields
        # read as unpageable, markerless body chunks.
        assert _StructureMixin._chunk_section_marker({}) is None
        assert (
            _StructureMixin._chunk_section_marker(
                {"chunk_text": None, "page_number": 100}
            )
            is None
        )


def _structured_chunk(page: int = 100, **fields: Any) -> dict[str, Any]:
    """Bucket chunk double: explicit identity fields + markerless text default."""
    base: dict[str, Any] = {
        "chunk_text": "Plain body prose with no heading-shaped opening.",
        "page_number": page,
        "source_file": "a.pdf",
    }
    base.update(fields)
    return base


class TestStructuredIdentityPriority:
    """D3-r2: structured payload identity wins over the text-marker fallback."""

    def test_dotted_section_id_prefix(self) -> None:
        chunk = _structured_chunk(section_id="7.1")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_bare_section_id(self) -> None:
        chunk = _structured_chunk(section_id="11")
        assert _StructureMixin._chunk_section_marker(chunk) == 11

    def test_multi_level_section_id_skipped_not_guessed(self) -> None:
        # The whole value must be a dotted/bare number: "7.1.3" is neither,
        # so the id is skipped rather than guessed from a prefix.
        chunk = _structured_chunk(section_id="7.1.3")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_out_of_range_section_id_skipped(self) -> None:
        # Chapter numbers stay in the module-wide 1..30 range; an id outside
        # it is not an identity hit.
        chunk = _structured_chunk(section_id="45")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_structured_identity_ignores_page_floor(self) -> None:
        # The ingest-time fields are evidence, not ToC-row text: they apply
        # at any page, including BELOW the marker floor (page 2; D3-r2/D5).
        chunk = _structured_chunk(page=2, section_id="7.1")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_numeric_chapter_id_values_and_strings(self) -> None:
        assert (
            _StructureMixin._chunk_section_marker(_structured_chunk(chapter_id="7"))
            == 7
        )
        assert (
            _StructureMixin._chunk_section_marker(_structured_chunk(chapter_id=9)) == 9
        )

    def test_slug_chapter_id_falls_to_heading_path(self) -> None:
        # docling slugs are not chapter numbers; the next field in priority
        # order speaks (the live report's chunk shape).
        chunk = _structured_chunk(
            chapter_id="ch-story-mapping-for-epics-best-practices-f",
            heading_path="Chapter 7 — Prioritization and Release Slicing",
        )
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_slug_chapter_id_falls_to_text_marker(self) -> None:
        chunk = _structured_chunk(
            chapter_id="ch-story-mapping-for-epics-best-practices-f",
            chunk_text="7.2 Walking skeleton overview\nProse follows here.",
        )
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_heading_path_prefix(self) -> None:
        chunk = _structured_chunk(
            heading_path="Chapter 7 — Prioritization and Release Slicing"
        )
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_heading_path_is_case_sensitive(self) -> None:
        # Only the ingest-captured "Chapter N" heading shape speaks; a
        # lowercase prose opening does not re-identify a chunk.
        chunk = _structured_chunk(heading_path="chapter 7 — Prioritization")
        assert _StructureMixin._chunk_section_marker(chunk) is None

    def test_section_id_beats_conflicting_chapter_id(self) -> None:
        chunk = _structured_chunk(section_id="7.1", chapter_id="9")
        assert _StructureMixin._chunk_section_marker(chunk) == 7

    def test_chapter_id_beats_conflicting_heading_path(self) -> None:
        chunk = _structured_chunk(chapter_id="9", heading_path="Chapter 3 — Other")
        assert _StructureMixin._chunk_section_marker(chunk) == 9

    def test_no_identity_at_all_returns_none(self) -> None:
        chunk = _structured_chunk()
        assert _StructureMixin._chunk_section_marker(chunk) is None


def _bucket_chunk(cid: str, text: str, page: int = 100, **extra: Any) -> dict[str, Any]:
    """Bucket chunk double with a stored-style ``chunk_id`` and real page.

    ``extra`` carries optional ingest-time identity fields (``section_id``,
    ``chapter_id``, ``heading_path``) for the structured-identity tests.
    """
    return {
        "chunk_id": cid,
        "chunk_text": text,
        "page_number": page,
        "source_file": "a.pdf",
        **extra,
    }


def _snapshot(
    buckets: dict[int, list[dict[str, Any]]],
) -> dict[int, list[dict[str, Any]]]:
    """Caller-state snapshot: the guard must never mutate the input."""
    return {k: [dict(c) for c in v] for k, v in buckets.items()}


def _chapter_entries(texts: list[str]) -> list[tuple[int, str, str]]:
    """Run ``_derive_chapter_numbers`` over hand-built one-page chunks.

    Each text becomes one ``a.pdf`` chunk in list order (first-wins claims
    follow that order); the roster entries ``(number, source, title)`` come
    back sorted by number.  The texts carry no appendix candidates, so the
    provider is never called.
    """
    provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
    pipeline = _make_pipeline(provider)
    chunks = [
        {"chunk_text": text, "source_file": "a.pdf", "page_number": 100 + i}
        for i, text in enumerate(texts)
    ]
    entries, _chapter_level_nums, _appendix_entries = pipeline._derive_chapter_numbers(
        chunks
    )
    return entries


class TestRosterTitleHygiene:
    """D6 roster-title capture: line-bound join, word-boundary trim, citation guard."""

    def test_register_row_rejected_and_real_heading_claims_chapter(self) -> None:
        # "7 Wikipedia — ..." is a source-register row, not a chapter
        # heading: the citation-shape guard (spaced dash + compact
        # abbreviation parenthetical) rejects it WITHOUT consuming the seen
        # slot, so the real "7. ..." heading line elsewhere still titles
        # chapter 7.
        entries = _chapter_entries(
            [
                "7 Wikipedia — The Design of Everyday Things (DET)\n"
                "Premise and reception prose follows.\n",
                "7. IDEO Field Guide mindsets and methods",
            ]
        )
        assert entries == [(7, "a.pdf", "IDEO Field Guide mindsets and methods")]

    def test_no_cross_line_title_gluing(self) -> None:
        # D-3: a complete heading line takes NO continuation line — body
        # prose never glues into the title (the old capture joined the first
        # uppercase-starting body line of any non-sentence-terminal title).
        # A wrapped heading (dangling comma end) joins exactly ONE
        # continuation line, never the second (the old \s title class crossed
        # lines up to its 80-char cap).
        entries = _chapter_entries(
            [
                "3. Building the artifact registry\n"
                "First body line starts here with words.\n"
                "Second body line never joins the title.\n"
            ]
        )
        assert entries == [(3, "a.pdf", "Building the artifact registry")]
        wrapped = _chapter_entries(
            [
                "3. Building the artifact registry,\n"
                "One wrapped continuation joins here.\n"
                "Second body line never joins the title.\n"
            ]
        )
        assert wrapped == [
            (
                3,
                "a.pdf",
                "Building the artifact registry, One wrapped continuation joins here",
            )
        ]

    def test_lowercase_continuation_never_joins(self) -> None:
        # capture_title only joins an uppercase-starting continuation line; a
        # lowercase body line stays out of the title.
        entries = _chapter_entries(
            ["4. Working with artifacts\nand more lowercase prose follows here.\n"]
        )
        assert entries == [(4, "a.pdf", "Working with artifacts")]

    def test_word_boundary_trim(self) -> None:
        # The 80-char budget now cuts at a word boundary (trim_title) instead
        # of the old mid-word class cut ("... (Documenting the platfo").
        entries = _chapter_entries(
            [
                "12. Agentic documentation workflows for API contract teams "
                "(Documenting the platform)\n"
            ]
        )
        assert entries == [
            (
                12,
                "a.pdf",
                "Agentic documentation workflows for API contract teams (Documenting the",
            )
        ]

    def test_real_register_row_rejected_and_real_heading_claims_chapter(self) -> None:
        # The live hcd-report register shape: the parenthetical arrives
        # line-wrapped and UNCLOSED ("... (D. Norman,"), so the shared
        # module's v2 citation guard rejects the row without consuming the
        # seen slot and the real "7. ..." heading line elsewhere still titles
        # chapter 7.
        entries = _chapter_entries(
            [
                "7 Wikipedia — The Design of\n"
                "Everyday Things (D. Norman,\n"
                "1988/2013)\n"
                "Premise and reception prose follows.\n",
                "7. IDEO Field Guide mindsets and methods",
            ]
        )
        assert entries == [(7, "a.pdf", "IDEO Field Guide mindsets and methods")]

    def test_empty_marker_run_before_footer_claims_nothing(self) -> None:
        # Docling's empty list-marker run above a running footer ("1. ⏎ …
        # N. ⏎" then "Human-Centered Design — Best Practices Report Page 4
        # of 25"): the on-line anchor refuses every marker line (no title on
        # its own line) and the footer carries no leading number, so the
        # shape claims no chapter at all (it used to fabricate chapters
        # 3/4/5/6 with footer titles).  The text ends at the footer line,
        # exactly the real chunk shape.
        entries = _chapter_entries(
            [
                "[3].\n"
                "1. \n"
                "2. \n"
                "3. \n"
                "4. \n"
                "5. \n"
                "6. \n"
                "Human-Centered Design — Best Practices Report Page 4 of 25\n"
            ]
        )
        assert entries == []
        # B2-r2: the banner carve-out's separator spans blank lines, but the
        # footer is still no title source — a blank line between the last
        # marker and the footer changes nothing because the footer never
        # opens with the dotted N.M shape the carve-out requires.
        entries = _chapter_entries(
            [
                "1. \n"
                "2. \n"
                "3. \n"
                "4. \n"
                "5. \n"
                "6. \n"
                "\n"
                "Human-Centered Design — Best Practices Report Page 4 of 25\n"
            ]
        )
        assert entries == []

    def test_banner_number_above_dotted_section_keeps_chapter_title_less(
        self,
    ) -> None:
        # B2-r2 banner carve-out (orchestrator option A): the shipped shape
        # "1⏎1.1 Central Management" — a chapter banner dropped onto its own
        # line directly above its dotted section heading — captures the
        # section text, and the dotted-section guard records the chapter
        # title-less exactly as v1's cross-line capture did.  A footer line
        # or another empty marker as the next line never qualifies.
        entries = _chapter_entries(["1\n1.1 Central Management\n"])
        assert entries == [(1, "a.pdf", "")]
        # Adjacent marker run + footer stays dead even with a dotted line
        # elsewhere in the chunk: the carve-out needs the dotted heading
        # directly under the number line, not merely present.
        entries = _chapter_entries(
            [
                "1. \n"
                "2. \n"
                "3. \n"
                "4. \n"
                "5. \n"
                "6. \n"
                "Human-Centered Design — Best Practices Report Page 4 of 25\n"
                "2.1 Unrelated Section\n"
            ]
        )
        assert entries == []

    def test_dot_shaped_colon_the_title_claims_chapter(self) -> None:
        # D6-r3 "the"-carve-out: the real hcd-report ch7 heading — dot-shaped
        # "7. The …" with a colon in the title — claims chapter 7 (the
        # article ban would have rejected it collaterally; with the register
        # row citation-rejected this heading is the only claim candidate
        # left, and losing it shrank the legacy roster 6..21 → 8..21).
        entries = _chapter_entries(
            ["7. The IDEO Field Guide: Mindsets, Phases, and\nMethods\n"]
        )
        assert entries == [
            (7, "a.pdf", "The IDEO Field Guide: Mindsets, Phases, and Methods")
        ]

    def test_dotless_the_title_stays_rejected(self) -> None:
        # The carve-out is dot-gated: a dot-less "N The X: Y" shape (like the
        # source-register rows) keeps the article ban even with a colon.
        entries = _chapter_entries(["7 The IDEO Field Guide: Mindsets, Phases\n"])
        assert entries == []

    def test_dot_shaped_the_without_colon_stays_rejected(self) -> None:
        # The carve-out is colon-gated: the license/boilerplate header shape
        # ("1. The Project Gutenberg eBook of Alice…") carries no colon, so
        # it stays rejected exactly as before.
        entries = _chapter_entries(["1. The Project Gutenberg eBook of Alice\n"])
        assert entries == []

    def test_register_cluster_rejected_list_context(self) -> None:
        # A source-register cluster of numbered rows (list context per
        # heading_forms.is_list_context) titles no chapter, and a real
        # heading after the cluster still claims its number: the citation
        # guard rejects every row without consuming the seen slot.
        cluster = (
            "7 Wikipedia — The Design of Everyday Things (DET)\n"
            "8 Wikipedia — The Semantic Turn (SEM)\n"
            "9 Norman — Design and everyday cognition (DEC)\n"
        )
        entries = _chapter_entries(
            [cluster + "7. IDEO Field Guide mindsets and methods\n"]
        )
        assert entries == [(7, "a.pdf", "IDEO Field Guide mindsets and methods")]
        assert heading_forms.is_list_context(cluster.split("\n"), 0)
        assert heading_forms.is_list_context(cluster.split("\n"), 1)


class TestBucketGuardReassignment:
    """The pre-loop guard pass reassigns or drops marker-mismatched chunks."""

    def test_foreign_marker_moves_to_rostered_chapter(self) -> None:
        # The treeless-report shape: chapter 6's detected page range yields
        # chunks whose own headings read 7.x; chapter 7 is rostered.
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        ch6 = _bucket_chunk(
            "c6", "7.1 Walking skeleton overview\nThe walking skeleton paces the build."
        )
        ch7 = _bucket_chunk(
            "c7",
            "7.2 Masking tape resistance\nMasking tape models the unknowns.",
            page=110,
        )
        buckets = {6: [ch6], 7: [ch7]}
        before = _snapshot(buckets)
        answer = pipeline._generate_multi_chapter_summary(
            [6, 7], buckets, {6: "Setup", 7: "Walkthrough"}
        )
        # Chapter 6 was emptied by the guard: its heading shows the existing
        # placeholder note extended with the D5 reason line naming chapter 7.
        assert "Chapter 6 — Setup" in answer
        assert "No document content was retrieved" in answer
        assert _GUARD_REASSIGNED_NOTE.format(targets="7") in answer, answer
        # The reassigned chunk is summarized under chapter 7's heading: it
        # reached chapter 7's one reduce call (and there is no chapter-6 call
        # at all -- the placeholder costs no LLM work).
        assert len(provider.stream_calls) == 1
        assert "Walking skeleton" in provider.stream_calls[0]["prompt"]
        assert "Masking tape" in provider.stream_calls[0]["prompt"]
        assert "Chapter 7 — Walkthrough" in answer
        assert _PLAUSIBLE in answer
        # Streamed == stored, byte for byte.
        assert capture.text == answer
        # The guard operates on a working copy: caller state is untouched.
        assert buckets == before

    def test_unrostered_marker_dropped_not_mislabeled(self) -> None:
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        foreign = _bucket_chunk(
            "cx", "12.4 Appendix roster recap\nAppendix prose lives here.", page=120
        )
        own = _bucket_chunk(
            "c7",
            "7.2 Masking tape resistance\nMasking tape models the unknowns.",
            page=110,
        )
        buckets = {6: [foreign], 7: [own]}
        before = _snapshot(buckets)
        answer = pipeline._generate_multi_chapter_summary(
            [6, 7], buckets, {6: "Setup", 7: "Walkthrough"}
        )
        # The marker names chapter 12, which is not rostered: the chunk is
        # dropped and the emptied bucket shows the drop-variant reason line.
        assert "Chapter 6 — Setup" in answer
        assert "No document content was retrieved" in answer
        assert _GUARD_DROPPED_NOTE in answer, answer
        # The foreign chunk reached no summary prompt at all.
        assert len(provider.stream_calls) == 1
        assert "Appendix roster" not in provider.stream_calls[0]["prompt"]
        assert "Chapter 7 — Walkthrough" in answer
        assert capture.text == answer
        assert buckets == before

    def test_self_identifying_marker_stays_in_place(self) -> None:
        # A marker naming the chunk's own chapter (or no marker at all) keeps
        # the bucket intact: the guard is threshold-free, not a veto.
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        own = _bucket_chunk("c7", "7.2 Masking tape resistance\nProse follows here.")
        markerless = _bucket_chunk(
            "c7b", "Plain body prose without any heading-shaped opening.", page=101
        )
        buckets = {7: [own, markerless]}
        before = _snapshot(buckets)
        answer = pipeline._generate_multi_chapter_summary([7], buckets, {7: "Tape"})
        assert "Chapter 7 — Tape" in answer
        assert _PLAUSIBLE in answer
        assert "No document content was retrieved" not in answer
        # Both chunks reached the one (non-streaming) reduce call, in bucket
        # order: on_chunk=None routes the reduce through generate().
        assert len(provider.generate_calls) == 1
        prompt = provider.generate_calls[0]["prompt"]
        assert "Masking tape" in prompt
        assert "Plain body prose" in prompt
        assert buckets == before


class TestBucketGuardCleanIdentity:
    """Clean buckets are byte-identical to the pre-guard behaviour."""

    def test_self_identifying_markers_match_marker_free_shape(self) -> None:
        # Same overview, two bucket shapes the pre-guard code treated
        # identically: chunks whose markers all self-identify (default page
        # 100) vs. marker-free twins (no N.M-shaped line at any page).
        # If the guard is a true no-op on clean buckets the transcripts must
        # be byte-identical.
        marked = {
            6: [_bucket_chunk("c6", "6.1 Setup overview\nSetup prose text here.")],
            7: [
                _bucket_chunk(
                    "c7",
                    "7.1 Walkthrough overview\nWalkthrough prose text here.",
                    page=110,
                )
            ],
        }
        plain = {
            6: [_bucket_chunk("c6", "Setup prose text here.", page=19)],
            7: [_bucket_chunk("c7", "Walkthrough prose text here.", page=19)],
        }
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        marked_before = _snapshot(marked)
        answer_marked = pipeline._generate_multi_chapter_summary(
            [6, 7], marked, {6: "Setup", 7: "Walkthrough"}
        )
        plain_pipeline = _make_pipeline(
            _StreamedProvider(generate_responses=[_PLAUSIBLE, _PLAUSIBLE]),
            on_chunk=None,
        )
        answer_plain = plain_pipeline._generate_multi_chapter_summary(
            [6, 7],
            {k: list(v) for k, v in plain.items()},
            {6: "Setup", 7: "Walkthrough"},
        )
        assert answer_marked == answer_plain
        # No spurious placeholders or notes on a clean roster (1 gap would
        # fire, but chapters 6 and 7 are only two -- the note is gated off).
        assert "No document content was retrieved" not in answer_marked
        assert "Coverage note" not in answer_marked
        # Each marker-bearing chunk stayed in its own bucket's window stream.
        assert len(provider.stream_calls) == 2
        assert "Setup overview" in provider.stream_calls[0]["prompt"]
        assert "Walkthrough overview" in provider.stream_calls[1]["prompt"]
        assert "Walkthrough" not in provider.stream_calls[0]["prompt"]
        assert marked == marked_before


class TestRosterCoverageNote:
    """The enumeration acknowledges roster gaps instead of passing as complete."""

    @staticmethod
    def _run(keys: list[int]) -> str:
        """Drive the generator over one-chapter buckets with a canned provider."""
        provider = _StreamedProvider(
            script=[(_PLAUSIBLE, None)],
            generate_responses=[_PLAUSIBLE] * len(keys),
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        buckets = {
            n: [
                _bucket_chunk(
                    f"c{n}",
                    f"Body prose for chapter {n} with several words.",
                    page=100 + n,
                )
            ]
            for n in keys
        }
        return pipeline._generate_multi_chapter_summary(
            keys, buckets, {n: f"Title {n}" for n in keys}
        )

    def test_roster_starting_above_one_gets_note(self) -> None:
        # The treeless-report shape: 6-15 detected, chapters 1-5 not located.
        answer = self._run(list(range(6, 16)))
        assert _ROSTER_COVERAGE_NOTE.format(missing="1\u20135") in answer
        # The note is the overview's last block.
        assert answer.rstrip().endswith("chapters listed above.")

    def test_internal_gap_gets_note(self) -> None:
        answer = self._run([1, 2, 4])
        assert _ROSTER_COVERAGE_NOTE.format(missing="3") in answer

    def test_multi_run_gaps_collapse_to_en_dash_ranges(self) -> None:
        # Missing 1,2,3,4,5,8 renders as "1\u20135, 8", not a bare list.
        answer = self._run([6, 7, 9])
        assert _ROSTER_COVERAGE_NOTE.format(missing="1\u20135, 8") in answer

    def test_contiguous_roster_stays_silent(self) -> None:
        answer = self._run([1, 2, 3, 4, 5])
        assert "Coverage note" not in answer

    def test_small_roster_with_gap_stays_silent(self) -> None:
        # Fewer than _ROSTER_NOTE_MIN_CHAPTERS chapters: single-chapter and
        # small-document paths own their output shape; no note.
        answer = self._run([2, 3])
        assert "Coverage note" not in answer

    def test_streamed_blocks_equal_returned_transcript(self) -> None:
        # The note streams through _on_chunk like the headings, so the stored
        # answer is byte-identical to what the reader watched.
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        keys = [6, 7, 9]
        buckets = {
            n: [
                _bucket_chunk(
                    f"c{n}", f"Body prose {n} with several words.", page=100 + n
                )
            ]
            for n in keys
        }
        answer = pipeline._generate_multi_chapter_summary(
            keys, buckets, {n: f"Title {n}" for n in keys}
        )
        assert capture.text == answer
        assert _ROSTER_COVERAGE_NOTE.format(missing="1\u20135, 8") in answer
        # The note went out on the content channel as the final block.
        assert capture.text.endswith("chapters listed above.")


class TestCoverageWrapperGuardIntegration:
    """D1-r2: the legacy wrapper guards once over the full roster.

    The live legacy overview delegates one chapter per call with a
    single-key roster; these tests drive
    ``_generate_multi_chapter_summary_with_coverage`` directly with a
    streaming capture (the funnel is exercised through it), with healthy
    windows everywhere (``window_compositions={}``) so the guard and note
    behavior is the only variable.
    """

    def test_full_roster_reassignment_through_wrapper(self) -> None:
        # The live report's shape: chapter 6's detected range yields chunks
        # that self-identify as chapter 7, chapter 7's as chapter 8, and
        # chapter 8's detected range is empty (no caller-side bucket at all).
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        buckets = {
            6: [
                _bucket_chunk(
                    "c6a", "Walking skeleton prose lives here.", chapter_id="7"
                ),
                _bucket_chunk(
                    "c6b", "More walking skeleton prose here.", chapter_id="7"
                ),
            ],
            7: [
                _bucket_chunk("c7", "Release slicing prose lives here.", chapter_id="8")
            ],
        }
        titles = {6: "Setup", 7: "Walkthrough", 8: "Slicing"}
        before = _snapshot(buckets)
        answer = pipeline._generate_multi_chapter_summary_with_coverage(
            [6, 7, 8], buckets, titles, {}
        )
        # Chapter 6 was emptied by the guard: the wrapper (not the funnel)
        # emits the placeholder with the D5 reason line naming chapter 7.
        assert "Chapter 6 — Setup" in answer
        assert "No document content was retrieved" in answer
        assert _GUARD_REASSIGNED_NOTE.format(targets="7") in answer, answer
        # The reassigned content is summarized under the chapter it names --
        # chapter 7's own chunk moved on to chapter 8 in the same sweep.
        assert "Chapter 7 — Walkthrough" in answer
        assert "Walking skeleton" in provider.stream_calls[0]["prompt"]
        assert "Chapter 8 — Slicing" in answer
        assert "Release slicing" in provider.stream_calls[1]["prompt"]
        # Nothing was dropped and nothing was summarized twice: two funnel
        # delegations (the placeholder chapter costs no LLM call).
        assert len(provider.stream_calls) == 2
        assert _GUARD_DROPPED_NOTE not in answer
        assert answer.count("No document content was retrieved") == 1
        # Exactly one roster note for the whole overview (roster 6-8 misses 1-5).
        assert answer.count("Coverage note:") == 1
        assert _ROSTER_COVERAGE_NOTE.format(missing="1\u20135") in answer
        # Streamed == stored, byte for byte, through the wrapper too.
        assert capture.text == answer
        # The wrapper's guard operates on a working copy: caller state is
        # untouched.
        assert buckets == before

    def test_exactly_one_coverage_note_despite_delegation(self) -> None:
        # The live roster: 6-15 detected, chapters 1-5 not located.  Each
        # chapter is delegated its own funnel call (single-key roster, below
        # the note's minimum size), yet exactly one note appears.
        keys = list(range(6, 16))
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        buckets = {
            n: [_bucket_chunk(f"c{n}", f"Body prose for chapter {n}.", page=100 + n)]
            for n in keys
        }
        answer = pipeline._generate_multi_chapter_summary_with_coverage(
            keys, buckets, {n: f"Title {n}" for n in keys}, {}
        )
        assert answer.count("Coverage note:") == 1
        assert _ROSTER_COVERAGE_NOTE.format(missing="1\u20135") in answer
        assert answer.rstrip().endswith("chapters listed above.")
        # Every chapter really was delegated its own funnel call.
        assert len(provider.stream_calls) == len(keys)
        assert capture.text == answer

    def test_contiguous_roster_no_note_through_wrapper(self) -> None:
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        keys = [1, 2, 3]
        buckets = {
            n: [_bucket_chunk(f"c{n}", f"Body prose for chapter {n}.", page=100 + n)]
            for n in keys
        }
        answer = pipeline._generate_multi_chapter_summary_with_coverage(
            keys, buckets, {n: f"Title {n}" for n in keys}, {}
        )
        assert "Coverage note" not in answer
        assert "No document content was retrieved" not in answer
        assert _PLAUSIBLE in answer
        assert capture.text == answer

    def test_guard_dropped_content_placeholder_through_wrapper(self) -> None:
        # Chapter 6's only chunk self-identifies as chapter 12, which no
        # delegation's roster includes: the wrapper-level guard drops it and
        # the wrapper emits the placeholder with the drop-variant reason.
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        buckets = {
            6: [
                _bucket_chunk(
                    "cx",
                    "12.4 Appendix roster recap\nAppendix prose lives here.",
                    page=120,
                )
            ],
            7: [_bucket_chunk("c7", "Body prose for chapter seven.", page=110)],
            8: [_bucket_chunk("c8", "Body prose for chapter eight.", page=130)],
        }
        before = _snapshot(buckets)
        answer = pipeline._generate_multi_chapter_summary_with_coverage(
            [6, 7, 8],
            buckets,
            {6: "Setup", 7: "Walkthrough", 8: "Slicing"},
            {},
        )
        assert "Chapter 6 — Setup" in answer
        assert "No document content was retrieved" in answer
        assert _GUARD_DROPPED_NOTE in answer, answer
        assert _GUARD_REASSIGNED_NOTE not in answer
        # The dropped chunk reached no summary prompt; ch7/ch8 were delegated.
        assert len(provider.stream_calls) == 2
        assert "Appendix roster" not in provider.stream_calls[0]["prompt"]
        assert "Appendix roster" not in provider.stream_calls[1]["prompt"]
        assert capture.text == answer
        assert buckets == before

    def test_pre_guard_empty_chapter_keeps_verbatim_placeholder(self) -> None:
        # A chapter whose detected range was empty before the guard keeps
        # the funnel-driven placeholder verbatim -- no reason line, since
        # the guard took nothing from it.
        provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        buckets = {
            1: [_bucket_chunk("c1", "Body prose for chapter one.", page=100)],
            # Chapter 2: no caller-side bucket at all -- its range was empty.
            3: [_bucket_chunk("c3", "Body prose for chapter three.", page=120)],
        }
        answer = pipeline._generate_multi_chapter_summary_with_coverage(
            [1, 2, 3],
            buckets,
            {1: "Opening", 2: "Missing", 3: "Closing"},
            {},
        )
        assert "Chapter 2 — Missing" in answer
        assert "No document content was retrieved" in answer
        assert _GUARD_DROPPED_NOTE not in answer
        assert _GUARD_REASSIGNED_NOTE not in answer
        # Two summaries were delegated; the empty chapter cost no LLM call.
        assert len(provider.stream_calls) == 2
        assert capture.text == answer

    def test_clean_wrapper_transcript_unchanged_by_guard(self) -> None:
        # Two bucket shapes the guard must treat identically: chunks that
        # all self-identify vs. chunks with no identity fields at all.  The
        # transcripts must be byte-identical, with no note and no
        # placeholder anywhere.
        marked = {
            1: [_bucket_chunk("c1", "1.1 Setup overview\nSetup prose here.", page=100)],
            2: [
                _bucket_chunk("c2", "2.1 Middle overview\nMiddle prose here.", page=110)
            ],
            3: [_bucket_chunk("c3", "3.1 End overview\nEnd prose here.", page=120)],
        }
        plain = {
            1: [_bucket_chunk("c1", "Setup prose here.", page=100)],
            2: [_bucket_chunk("c2", "Middle prose here.", page=110)],
            3: [_bucket_chunk("c3", "End prose here.", page=120)],
        }
        titles = {1: "Setup", 2: "Middle", 3: "End"}
        marked_provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        marked_capture = _CallbackCapture()
        marked_pipeline = _make_pipeline(marked_provider, on_chunk=marked_capture)
        answer_marked = marked_pipeline._generate_multi_chapter_summary_with_coverage(
            [1, 2, 3], marked, titles, {}
        )
        plain_provider = _StreamedProvider(script=[(_PLAUSIBLE, None)])
        plain_capture = _CallbackCapture()
        plain_pipeline = _make_pipeline(plain_provider, on_chunk=plain_capture)
        answer_plain = plain_pipeline._generate_multi_chapter_summary_with_coverage(
            [1, 2, 3], plain, titles, {}
        )
        assert answer_marked == answer_plain
        assert "Coverage note" not in answer_marked
        assert "No document content was retrieved" not in answer_marked
        # Each self-identifying chunk stayed in its own chapter's window.
        assert len(marked_provider.stream_calls) == 3
        assert "Setup overview" in marked_provider.stream_calls[0]["prompt"]
        assert "End overview" in marked_provider.stream_calls[2]["prompt"]
        assert marked_capture.text == answer_marked
        assert plain_capture.text == answer_plain
