"""Unit tests for the shared numbered-heading forms (heading_forms)."""

from __future__ import annotations

import pytest

from secondbrain.document.heading_forms import (
    capture_title,
    is_list_context,
    looks_like_citation_row,
    match_numbered_heading,
    scan_text,
    trim_title,
)


class TestMatchNumberedHeading:
    def test_bare_dot_chapter_form(self):
        got = match_numbered_heading(
            "9. Krippendorff's Co-Creation Framework for Everyday Things"
        )
        assert got == (
            9,
            None,
            "Krippendorff's Co-Creation Framework for Everyday Things",
        )

    def test_no_dot_rejected_when_dot_required(self):
        # Source-register row: no separating dot -> never a synthesized node.
        assert (
            match_numbered_heading(
                "7 Wikipedia — The Design of Everyday Things (Doet…)",
                require_dot=True,
            )
            is None
        )

    def test_no_dot_accepted_without_requirement(self):
        # The shipped dot-less shape (quoted-phrase spec) stays capturable.
        got = match_numbered_heading(
            '2 First Principles: What "Well-Defined" Actually Means'
        )
        assert got == (2, None, 'First Principles: What "Well-Defined" Actually Means')

    def test_dotted_section_form(self):
        assert match_numbered_heading("7.1 Definitions") == (7, 1, "Definitions")

    def test_section_form_beats_chapter_form(self):
        # "7.1 Definitions" must not be read as chapter 7 titled "1 Definitions".
        got = match_numbered_heading("7.1 Definitions")
        assert got is not None and got[1] == 1 and got[2] == "Definitions"

    def test_two_digit_section(self):
        assert match_numbered_heading("1.23 Installing") == (1, 23, "Installing")

    def test_dot_leader_toc_row_rejected(self):
        assert match_numbered_heading("3. The ISO 9241-210 Standard ....... 4") is None

    def test_trailing_page_number_rejected(self):
        assert match_numbered_heading("7.1 Definitions 4") is None

    def test_overlong_line_rejected(self):
        assert match_numbered_heading("9. " + "word " * 30) is None

    def test_stub_title_rejected(self):
        assert match_numbered_heading("9. X") is None

    def test_lowercase_title_rejected(self):
        assert match_numbered_heading("9. krippendorff's framework") is None

    @pytest.mark.parametrize("line", ["45. Out of range", "0. Zero chapter"])
    def test_chapter_bounds_rejected(self, line):
        assert match_numbered_heading(line) is None

    def test_section_number_bounds_rejected(self):
        assert match_numbered_heading("7.45 Too far") is None

    def test_bare_number_without_title_rejected(self):
        assert match_numbered_heading("9.") is None
        assert match_numbered_heading("9") is None

    def test_inline_prose_never_matches(self):
        # The patterns are line-anchored; mid-sentence mentions never match.
        assert match_numbered_heading("in chapter 7 we discuss structure") is None


class TestScanText:
    def test_offsets_and_line_indices(self):
        text = "Intro body line.\n9. Krippendorff's Framework\nmore body"
        got = scan_text(text)
        assert len(got) == 1
        heading = got[0]
        assert heading.chapter == 9
        assert heading.section is None
        assert heading.line_index == 1
        assert heading.char_offset == len("Intro body line.") + 1
        assert heading.title == "Krippendorff's Framework"

    def test_dotted_and_bare_mixed(self):
        text = "7.1 Definitions\n7.2 From design thinking\ntext"
        got = scan_text(text)
        assert [(h.chapter, h.section) for h in got] == [(7, 1), (7, 2)]

    def test_require_dot_forwarded(self):
        text = "7 Wikipedia — The Design of Everyday Things\n9. Krippendorff"
        got = scan_text(text, require_dot=True)
        assert [h.chapter for h in got] == [9]

    def test_no_matches(self):
        assert scan_text("plain prose\nwithout numbers") == []


class TestCaptureTitle:
    def test_wrapped_title_continues_one_line(self):
        got = capture_title(
            "Krippendorff's Co-Creation Framework for",
            "Everyday Things and Useful Objects",
        )
        assert (
            got
            == "Krippendorff's Co-Creation Framework for Everyday Things and Useful Objects"
        )

    def test_dangling_comma_joins(self):
        # fix-chapter-evidence-fidelity D-3: the join fires only for genuine
        # wrapped headings — a dangling comma end ("… Make,") joins.
        assert (
            capture_title("The Methods Library: Discover, Decide, Make,", "Validate")
            == "The Methods Library: Discover, Decide, Make, Validate"
        )

    def test_dangling_connective_joins(self):
        # Trailing "and" / "for" ends are wrapped headings, not complete ones.
        assert (
            capture_title("The IDEO Field Guide: Mindsets, Phases, and", "Methods")
            == "The IDEO Field Guide: Mindsets, Phases, and Methods"
        )
        assert (
            capture_title("Krippendorff's Semantic Turn: Designing for", "Meaning")
            == "Krippendorff's Semantic Turn: Designing for Meaning"
        )

    def test_single_word_orphan_joins(self):
        # A wrapped heading can leave an orphan word: the first line ends
        # complete but the one-word next line is the title's own tail.
        assert (
            capture_title("Phase-by-Phase Working Table and Common", "Failures")
            == "Phase-by-Phase Working Table and Common Failures"
        )
        assert (
            capture_title("Governance: Telling Real HCD from HCD", "Theater")
            == "Governance: Telling Real HCD from HCD Theater"
        )

    def test_complete_title_never_joins_body_prose(self):
        # The D-3 defect class: complete titles followed by multi-word body
        # prose used to glue ("… Well Usability testing means observing…").
        assert (
            capture_title(
                "Running Usability Testing Well",
                "Usability testing means observing users as they",
            )
            == "Running Usability Testing Well"
        )
        assert (
            capture_title(
                "Where HCD Pays Off — and Where It Doesn't",
                "HCD pays off where the cost of the",
            )
            == "Where HCD Pays Off — and Where It Doesn't"
        )
        assert (
            capture_title(
                "Bridging to Story Mapping (Companion Report)",
                "HCD and agile delivery are",
            )
            == "Bridging to Story Mapping (Companion Report)"
        )
        assert (
            capture_title(
                "Quick-Reference Checklist",
                "Before research (Fundamentals)",
            )
            == "Quick-Reference Checklist"
        )
        assert (
            capture_title(
                "Agentic API-Contract Documentation (OpenAPI",
                "For projects that expose API",
            )
            == "Agentic API-Contract Documentation (OpenAPI"
        )

    def test_single_word_join_still_respects_guards(self):
        # The orphan-word join never bypasses the other continuation guards:
        # a lowercase, bullet, heading, ToC-row, or page-number line stays out
        # even when it is a single word.
        assert capture_title("Working Table and Common", "failures") == (
            "Working Table and Common"
        )
        assert capture_title("Working Table and Common", "- failures") == (
            "Working Table and Common"
        )
        assert capture_title("Working Table and Common", "5. Next Chapter") == (
            "Working Table and Common"
        )
        assert capture_title("Working Table and Common", "Failures ....... 4") == (
            "Working Table and Common"
        )
        assert capture_title("Working Table and Common", "Failures 4") == (
            "Working Table and Common"
        )

    def test_no_next_line(self):
        assert capture_title("A Plain Title", None) == "A Plain Title"

    def test_sentence_terminal_blocks_continuation(self):
        assert (
            capture_title("Chapter Title.", "Continuation prose line")
            == "Chapter Title."
        )

    def test_lowercase_continuation_rejected(self):
        assert (
            capture_title("Title without end", "continuation lowercase")
            == "Title without end"
        )

    def test_continuation_heading_rejected(self):
        assert (
            capture_title("Title without end", "10. Next Chapter Title")
            == "Title without end"
        )

    def test_continuation_bullet_rejected(self):
        assert (
            capture_title("Title without end", "- a list item") == "Title without end"
        )

    def test_continuation_toc_row_rejected(self):
        assert (
            capture_title("Title without end", "3. Standard ....... 4")
            == "Title without end"
        )

    def test_trailing_page_number_continuation_rejected(self):
        assert capture_title("Title without end", "Sub note 4") == "Title without end"

    def test_whitespace_normalized(self):
        assert capture_title("  Spaced   Title  ", None) == "Spaced Title"


class TestTrimTitle:
    def test_short_title_unchanged(self):
        assert trim_title("Short Title") == "Short Title"

    def test_word_boundary_trim(self):
        title = "A Chapter Title That Runs On " + "and ".join(["word"] * 20)
        got = trim_title(title, cap=40)
        assert len(got) < 40
        assert got.endswith("and") or got.split()[-1].isalnum()
        # Never ends mid-word: the next character of the source is a space.
        assert title.startswith(got)
        assert title[len(got)] == " "

    def test_trim_strips_trailing_separator(self):
        title = "One two three four five six seven eight nine ten eleven twelve"
        got = trim_title(title, cap=30)
        assert not got.endswith((" ", ",", ";", ":", "-"))

    def test_trim_moves_to_word_boundary(self):
        # "characters" would be cut mid-word at the cap; the trim falls back
        # to the previous whole word.
        got = trim_title("Exactly thirty characters here", cap=25)
        assert got == "Exactly thirty"


class TestCitationRows:
    def test_register_row_detected(self):
        assert looks_like_citation_row(
            "Wikipedia — The Design of Everyday Things (Doet…)"
        )

    def test_full_citation_with_author_year_detected(self):
        assert looks_like_citation_row(
            "Wikipedia — The Design of Everyday Things (D. Norman, 1988/2013)"
        )

    def test_unclosed_citation_paren_detected(self):
        assert looks_like_citation_row(
            "Wikipedia — The Design of Everyday Things (D. Norman,"
        )

    def test_year_paren_detected(self):
        assert looks_like_citation_row("Field Notes — Practice (1988)")

    def test_prose_parenthetical_not_citation(self):
        assert not looks_like_citation_row(
            "Everyday Design (The Basics) of Things — Continued"
        )

    def test_dash_without_compact_paren_not_citation(self):
        assert not looks_like_citation_row(
            'First Principles: What "Well-Defined" Actually Means'
        )

    def test_no_dash_not_citation(self):
        assert not looks_like_citation_row("9. Krippendorff's Co-Creation Framework")


class TestListContext:
    def test_numbered_cluster_is_list(self):
        lines = ["1. First step", "2. Second step", "3. Third step"]
        assert is_list_context(lines, 1)

    def test_lone_heading_not_list(self):
        lines = ["Intro body text.", "9. Krippendorff's Framework", "More body text."]
        assert not is_list_context(lines, 1)

    def test_register_cluster_is_list(self):
        lines = [
            "5 Norman, D. The Design of Everyday Things",
            "6 ISO 9241-210 Standard",
            "7 Wikipedia — The Design of Everyday Things (Doet…)",
        ]
        assert is_list_context(lines, 2)
