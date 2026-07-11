"""Unit tests for secondbrain.document.structure_extractor."""

from __future__ import annotations

import pytest

from secondbrain.document.structure_extractor import (
    HeadingDetector,
    SectionAssignment,
    SectionClassifier,
    TOCEntry,
    TOCParser,
)


# ---------------------------------------------------------------------------
# HeadingDetector
# ---------------------------------------------------------------------------


class TestHeadingDetectorWeight:
    """Cover scoring branches in HeadingDetector.weight()."""

    def test_hash_prefix_scored(self) -> None:
        detector = HeadingDetector(min_weight=0)
        long_hash = "# " + "A" * 90
        assert detector.weight(long_hash) > 0

    def test_short_text_scored(self) -> None:
        detector = HeadingDetector(min_weight=0)
        assert detector.weight("Overview of Results") > 0

    def test_long_text_not_scored_short(self) -> None:
        detector = HeadingDetector(min_weight=0)
        long_text = "A" * 100
        assert detector.weight(long_text) == 0

    def test_structural_keywords_scored(self) -> None:
        detector = HeadingDetector(min_weight=0)
        text = "Chapter 3 " + "relevant content " * 10
        assert detector.weight(text, element_type=None) > 0

    def test_keyword_case_insensitive(self) -> None:
        detector = HeadingDetector(min_weight=0)
        text = "CHAPTER 3 " + "overview " * 10
        assert detector.weight(text, element_type=None) > 0

    def test_element_type_heading_large_score(self) -> None:
        detector = HeadingDetector(min_weight=0)
        text = "Analysis of financial statements " * 5
        w = detector.weight(text, element_type="heading")
        assert w == 5

    def test_trailing_colon_scored(self) -> None:
        detector = HeadingDetector(min_weight=0)
        text = "Discussion of key terms " * 3 + "Conclusion:"
        assert detector.weight(text, element_type=None) > 0

    def test_trailing_dash_scored(self) -> None:
        detector = HeadingDetector(min_weight=0)
        text = "Important notes " * 3 + "Summary -"
        assert detector.weight(text, element_type=None) > 0

    def test_combined_signals(self) -> None:
        detector = HeadingDetector(min_weight=0)
        w = detector.weight("# Chapter 1:", element_type=None)
        assert w == 7

    def test_min_weight_threshold_veto(self) -> None:
        detector = HeadingDetector(min_weight=5)
        text = "Item 1:"
        w = detector.weight(text, element_type=None)
        assert detector.is_heading(text) is False


class TestHeadingDetectorIsHeading:
    """Cover is_heading() branches."""

    def test_empty_string_false(self) -> None:
        detector = HeadingDetector()
        assert detector.is_heading("") is False

    def test_none_arg_false(self) -> None:
        detector = HeadingDetector()
        assert detector.is_heading("") is False

    def test_hash_prefix_true_overrides_threshold(self) -> None:
        detector = HeadingDetector(min_weight=999)
        assert detector.is_heading("# Appendix") is True

    def test_allcaps_long_not_heading(self) -> None:
        detector = HeadingDetector()
        text = "THIS IS A VERY LONG SENTENCE IN ALL CAPS WITHOUT A CLEAR HEADING SIGNAL FOR TESTING"
        assert len(text) >= 80
        assert detector.is_heading(text) is False

    def test_short_uppercase_two_words_not_rejected(self) -> None:
        detector = HeadingDetector()
        text = "CHAPTER NOTES"
        assert len(text) < 80
        assert detector.is_heading(text) is True


# ---------------------------------------------------------------------------
# TOCParser
# ---------------------------------------------------------------------------


class TestTOCParserParseLine:
    """Cover parse() for TOC entry formats."""

    def test_parses_single_level(self) -> None:
        parser = TOCParser()
        entries = parser.parse({"text_lines": ["1.1 Introduction"], "page_number": 0})
        assert len(entries) == 1
        assert entries[0].level == 2
        assert entries[0].number == "1.1"
        assert entries[0].title == "Introduction"
        assert entries[0].page is None

    def test_parses_multilevel_sections(self) -> None:
        parser = TOCParser()
        entries = parser.parse(
            {"text_lines": ["3.9 Financial Statements", "3.9.11 Notes"], "page_number": 5}
        )
        # "3.9" → number.count('.')+1 = 2; "3.9.11" → count('.')+1 = 3
        assert entries[0].level == 2
        assert entries[0].number == "3.9"
        assert entries[1].level == 3
        assert entries[1].number == "3.9.11"
        assert entries[1].title == "Notes"
        assert entries[1].page is None

    def test_parses_leader_dot_format(self) -> None:
        parser = TOCParser()
        entries = parser.parse({"text_lines": [".... 2.3 Analysis  15"], "page_number": 1})
        assert entries[0].number == "2.3"
        assert "...." not in entries[0].title

    def test_extracts_arabic_page(self) -> None:
        parser = TOCParser()
        entries = parser.parse(
            {"text_lines": ["4.2 Risk Factors  42"], "page_number": None}
        )
        assert entries[0].page == 42
        assert "42" not in entries[0].title

    def test_non_toc_line_skipped(self) -> None:
        parser = TOCParser()
        entries = parser.parse(
            {"text_lines": ["This is body text, not a heading."], "page_number": 0}
        )
        assert len(entries) == 0

    def test_missing_text_lines_empty(self) -> None:
        parser = TOCParser()
        assert parser.parse({}) == []

    def test_whitespace_lines_skipped(self) -> None:
        parser = TOCParser()
        entries = parser.parse({"text_lines": ["   ", ""], "page_number": 0})
        assert entries == []


class TestTOCParserFindTocChunks:
    """Cover find_toc_chunks() density threshold."""

    def test_high_density_returns_chunk(self) -> None:
        parser = TOCParser()
        chunk = {
            "text_lines": [
                "1. First", "body", "2. Second", "more body",
                "3. Third", "more body", "4. Fourth",
            ]
        }
        candidates = parser.find_toc_chunks([chunk])
        assert len(candidates) == 1

    def test_low_density_excluded(self) -> None:
        parser = TOCParser()
        chunk = {
            "text_lines": [
                "1. First",
                "lots of body text here",
                "lots more body text here",
                "lots more body text here",
                "even more body content here",
            ]
        }
        candidates = parser.find_toc_chunks([chunk])
        assert len(candidates) == 0

    def test_no_text_lines_excluded(self) -> None:
        parser = TOCParser()
        assert parser.find_toc_chunks([{}]) == []

    def test_multiple_chunks_filters(self) -> None:
        parser = TOCParser()
        toc = {"text_lines": ["1. Ch1", "2. Ch2", "3. Ch3"]}
        body = {"text_lines": ["regular paragraph content here"]}
        candidates = parser.find_toc_chunks([toc, body])
        assert len(candidates) == 1
        assert candidates[0] is toc


class TestTOCParserIsTocEntryLine:
    """Cover _is_toc_entry_line()."""

    def test_true_for_dotted_number(self) -> None:
        assert TOCParser._is_toc_entry_line("3.9 Financial") is True

    def test_false_for_plain_text(self) -> None:
        assert TOCParser._is_toc_entry_line("This is body text.") is False

    def test_false_for_digits_no_dot(self) -> None:
        assert TOCParser._is_toc_entry_line("Page 42") is False

    def test_false_for_empty(self) -> None:
        assert TOCParser._is_toc_entry_line("") is False


# ---------------------------------------------------------------------------
# SectionClassifier
# ---------------------------------------------------------------------------


class TestSectionClassifierClassify:
    """Cover classify() routing."""

    @pytest.fixture
    def entries_with_positions(self) -> list[TOCEntry]:
        return [
            TOCEntry(level=1, number="1", title="Intro", page=0, char_start=0),
            TOCEntry(level=1, number="2", title="Financials", page=10, char_start=500),
            TOCEntry(level=2, number="2.1", title="Revenue", page=10, char_start=600),
            TOCEntry(level=2, number="2.2", title="Costs", page=15, char_start=1100),
            TOCEntry(level=1, number="3", title="Risks", page=20, char_start=1600),
        ]

    def test_explicit_section_number_short_circuit(
        self, entries_with_positions: list[TOCEntry]
    ) -> None:
        classifier = SectionClassifier(entries_with_positions)
        chunk = {"char_start": 9999, "section_number": "2.1", "text": "Revenue"}
        result = classifier.classify(chunk)
        assert result.section_id == "2.1"
        assert result.chapter_id == 2
        assert result.depth == 2

    def test_body_chunk_after_last_entry_gets_last(
        self, entries_with_positions: list[TOCEntry]
    ) -> None:
        classifier = SectionClassifier(entries_with_positions)
        chunk = {"char_start": 5000, "text": "Endmatter"}
        result = classifier.classify(chunk)
        # char_position 5000 > all char_start values → binary search finds last entry
        assert result.section_id == "3"
        assert result.chapter_id == 3

    def test_body_chunk_between_entries(
        self, entries_with_positions: list[TOCEntry]
    ) -> None:
        classifier = SectionClassifier(entries_with_positions)
        # char_start=700 after 2.1(600) but before 2.2(1100) → closest ≤ 700 is 2.1
        chunk = {"char_start": 700, "text": "Between sections 2.1 and 2.2"}
        result = classifier.classify(chunk)
        assert result.section_id == "2.1"
        assert result.chapter_id == 2

    def test_empty_toc_neutral(self) -> None:
        classifier = SectionClassifier([])
        chunk = {"char_start": 100, "text": "Floating body"}
        result = classifier.classify(chunk)
        assert result.chapter_id is None
        assert result.section_id is None


class TestSectionClassifierAssignmentFromNumber:
    """Cover _assignment_from_number()."""

    def test_chapter_level(self) -> None:
        classifier = SectionClassifier([])
        result = classifier._assignment_from_number("3", "heading")
        assert result.chapter_id == 3
        assert result.section_id == "3"
        assert result.depth == 1

    def test_deeply_nested(self) -> None:
        classifier = SectionClassifier([])
        result = classifier._assignment_from_number("4.7.2.1", None)
        assert result.chapter_id == 4
        assert result.section_id == "4.7.2.1"
        assert result.depth == 4

    def test_invalid_number(self) -> None:
        classifier = SectionClassifier([])
        result = classifier._assignment_from_number("x.y.z", None)
        assert result.chapter_id is None
        assert result.section_id == "x.y.z"

    def test_whitespace_trimmed(self) -> None:
        classifier = SectionClassifier([])
        result = classifier._assignment_from_number("  2.1  ", None)
        assert result.section_id == "2.1"