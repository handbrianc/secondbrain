"""Structural enhancement: heading detection, TOC parsing, and section classification."""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# HeadingDetector
# ----------------------------------------------------------------------


class HeadingDetector:
    """Detect heading candidates in document chunks using structural heuristics."""

    def __init__(self, min_weight: int = 2) -> None:
        """
        Initialise the detector.

        Args:
            min_weight: Minimum weight threshold to consider a chunk a heading.
        """
        self._min_weight = min_weight

    def is_heading(self, chunk_text: str, font_size: float | None = None) -> bool:
        """
        Return True if *chunk_text* looks like a heading.

        Heuristic:
        - Short line (under 80 characters)
        - No mid-sentence periods
        - Possibly bold/prefix markers (# prefix, etc.)
        - Distinct formatting cues compared to body text
        """
        if not chunk_text:
            return False
        stripped = chunk_text.strip()
        # A heading should not look like a sentence with internal clauses.
        # Basic guard: bare acronyms or very long lines are unlikely headings.
        if len(stripped) >= 80:
            return False
        if stripped.isupper() and len(stripped.split()) > 2:
            # ALL CAPS lines that are long sentences are probably not headings
            return False
        # Simple heuristic: allow if it either starts with a hash prefix
        # or is relatively short and optionally ends with punctuation.
        if stripped.startswith("#"):
            return True
        # No strong signal from plain text alone - delegate to weight().
        return self.weight(chunk_text) >= self._min_weight

    def weight(
        self,
        chunk_text: str,
        element_type: str | None = None,
    ) -> int:
        """
        Compute a heading confidence score.

        Higher score = more confident the chunk is a heading.

        Scoring rules:
        - Starts with ``#`` markdown prefix                     -> +3
        - Shorter than 80 characters                            -> +1
        - Contains "Chapter", "Section", or "Part"              -> +2
        - Already classified as "heading" by upstream parser     -> +5
        - Trailing colon or dash (e.g. ``H1:``, ``-`` suffix)  -> +1
        """
        w = 0
        text = chunk_text.strip()

        if text.startswith("#"):
            w += 3

        if len(text) < 80:
            w += 1

        # Check for structural keywords (case-insensitive)
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("chapter", "section", "part")):
            w += 2

        if element_type == "heading":
            w += 5

        # Trailing punctuation that commonly marks headings
        if text.endswith(":") or text.rstrip().endswith("-"):
            w += 1

        return w


# ----------------------------------------------------------------------
# TOCParser
# ----------------------------------------------------------------------


@dataclass
class TOCEntry:
    """A single entry parsed from a table-of-contents block."""

    level: int
    """1 = top-level chapter, 2 = subsection, 3+ = sub-subsection."""

    number: str
    """Dot-separated section number, e.g. ``"1"``, ``"2.3"``, ``"3.9.11"``."""

    title: str
    """Plain-text title of the entry."""

    page: int | None = None
    """Zero-based page index, or None if not recoverable."""

    char_start: int | None = None
    """Character offset of this entry within the document, or None if unknown."""


class TOCParser:
    """
    Parse table-of-contents chunks extracted by the docling pipeline.

    Methods are designed to operate on dictionaries produced by the
    docling chunker so that the same parsing logic works for both
    live ingestion and offline reprocessing.
    """

    # Regex for dot-delimited section numbers: "3", "3.9", "3.9.11"
    _SECTION_NUM_RE = re.compile(r"(\d+)(?:\.(\d+))+")

    # Leading-dot leaders used in printed ToCs: ".... 3.1"
    _LEADER_STRIP_RE = re.compile(r"^\.{2,}\s*")

    # Roman-numeral page indicators (trailing, possibly with trailing dots/spaces)
    _ROMAN_PAGE_RE = re.compile(
        r"[ivxlcdm]+\.?\s*$",
        re.IGNORECASE,
    )

    # Arabic-page-number trailing markers
    _ARABIC_PAGE_RE = re.compile(r"\d+\s*$")

    def parse(self, toc_chunk: dict[str, Any]) -> list[TOCEntry]:
        """
        Extract structured :class:`TOCEntry` objects from a single TOC block.

        Args:
            toc_chunk: A dictionary representing a TOC page, as emitted by the
                docling chunker. Expected keys include at minimum
                ``text_lines`` (list[str]), with optional ``page_number``.

        Returns:
            Ordered list of :class:`TOCEntry` instances discovered in the chunk.
        """
        entries: list[TOCEntry] = []
        raw_lines: list[str] = toc_chunk.get("text_lines", [])
        raw_page: int | None = toc_chunk.get("page_number")

        for line in raw_lines:
            entry = self._parse_line(line, default_page=raw_page)
            if entry is not None:
                entries.append(entry)

        return entries

    def find_toc_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Filter *chunks* to those that look like TOC pages.

        A chunk is considered a TOC candidate when it exhibits a high density
        of numbered section entries relative to total lines.

        Args:
            chunks: Flat list of chunk dictionaries (as produced by the chunker).

        Returns:
            Subset of *chunks* identified as TOC blocks.
        """
        toc_candidates: list[dict[str, Any]] = []

        for chunk in chunks:
            # Chunks that lack text content cannot be parsed
            if not chunk.get("text_lines"):
                continue

            num_lines = len(chunk["text_lines"])
            num_entries = sum(
                1 for line in chunk["text_lines"]
                if self._is_toc_entry_line(line)
            )
            density = num_entries / num_lines if num_lines else 0

            # Threshold tuned for documents with 3-5 heading levels
            if density >= 0.25:
                toc_candidates.append(chunk)

        return toc_candidates

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_line(
        self, line: str, *, default_page: int | None = None
    ) -> TOCEntry | None:
        """Parse a single line into a TOCEntry, or return None if it isn't one."""
        stripped = line.strip()
        if not stripped:
            return None

        # Strip leader dots
        stripped = self._LEADER_STRIP_RE.sub("", stripped)

        # Attempt to extract section number and title
        m = self._SECTION_NUM_RE.search(stripped)
        if m is None:
            return None

        number = m.group(0)  # e.g. "3.9"

        # Determine nesting depth from dot count
        level = number.count(".") + 1

        # Title follows the section number (may be absent in sparse ToCs)
        after_number = stripped[m.end() :].strip()
        title = after_number.lstrip(". ").rstrip(":. -")

        # Extract page reference (prefer Arabic numerals, fall back to Roman)
        page: int | None = None
        page_match = self._ARABIC_PAGE_RE.search(title)
        if page_match:
            try:
                page = int(page_match.group())
            except ValueError:
                page = None
        elif self._ROMAN_PAGE_RE.search(title):
            # Roman numerals decoded as 0 (decoding is lossy; mark as unknown)
            page = default_page

        # Clean trailing artifacts from title
        title = (
            self._ARABIC_PAGE_RE.sub("", title)
            .replace("\t", " ")
            .strip()
        )

        return TOCEntry(level=level, number=number, title=title, page=page)

    @staticmethod
    def _is_toc_entry_line(line: str) -> bool:
        """Return True if *line* looks like a single ToC entry."""
        stripped = line.strip()
        if not stripped:
            return False
        # Must contain at least one digit and a dot (section numbering)
        if not any(c.isdigit() for c in stripped):
            return False
        return "." in stripped


# ----------------------------------------------------------------------
# SectionClassifier
# ----------------------------------------------------------------------


@dataclass
class SectionAssignment:
    """
    Result of assigning a structural-section label to a chunk.

    Attributes give the chapter and section context so that callers can
    attach stable IDs and titles to individual chunks.
    """

    chapter_id: int | None
    """Numeric chapter identifier derived from the leading TOC number, e.g. 3."""

    chapter_title: str | None
    """Human-readable chapter heading observed in the TOC, if known."""

    section_id: str | None
    """Dot-separated section path, e.g. ``"3.9"``."""

    section_title: str | None
    """Section heading text if present in the TOC."""

    depth: int = 1
    """Nesting depth: 1 = chapter/top-level, 2+ = subsections."""


class SectionClassifier:
    """
    Assign hierarchical *section_id* and *chapter_id* to arbitrary chunks.

    Uses a previously-parsed :class:`TOCEntry` list to determine which
    chapter/section boundaries apply to each ingested chunk.
    """

    def __init__(self, toc_entries: list[TOCEntry]) -> None:
        """
        Initialise the classifier.

        Args:
            toc_entries: Sorted list of TOC entries, typically produced by
                :meth:`TOCParser.parse`.
        """
        self._toc = toc_entries

        # Pre-compute chapter boundaries: map number prefix -> entry index
        # We treat "N" as a chapter and "N.X" as belonging to that chapter
        self._chapter_starts: dict[str, int] = {}
        for idx, entry in enumerate(toc_entries):
            root = entry.number.split(".")[0]
            if root not in self._chapter_starts:
                self._chapter_starts[root] = idx

    def classify(self, chunk: dict[str, Any]) -> SectionAssignment:
        """
        Assign a structural section label to *chunk*.

        Algorithm:
        1. Examine the chunk's own section-number annotation (element_type).
        2. Fall back to scanning backward through *self._toc* to locate the
           nearest preceding entry.
        3. Body chunks (no number) inherit the last-seen heading's assignment.
        4. When a chunk overlaps multiple chapters, it is attributed to the
           nearer one by character position.

        Parameters:
            chunk: Dictionary representing a document chunk. At minimum
                requires ``text`` (str) and ``char_start`` (int) keys.
                May also carry ``element_type``, ``section_number``, etc.

        Returns:
            A :class:`SectionAssignment` describing the hierarchical context.
        """
        char_pos = chunk.get("char_start", 0)

        # --- Step 1: explicit annotation from upstream parser -------------
        elem_type: str | None = chunk.get("element_type")
        section_num: str | None = chunk.get("section_number")

        if isinstance(section_num, str) and section_num.strip():
            return self._assignment_from_number(section_num, elem_type)

        # --- Step 2: infer from TOC by proximity -------------------------
        # Find the closest TOC entry that precedes or covers this chunk position
        closest_idx = self._find_closest_toc_entry(char_pos)
        if closest_idx is not None:
            toc_entry = self._toc[closest_idx]
            return self._assignment_from_toc_entry(toc_entry, closest_idx)

        # --- Step 3: body text without anchors ---------------------------
        # Walk forward in the chunk list to locate the nearest *following*
        # heading and inherit its assignment lazily. Because we lack the full
        # iterator here we return a neutral placeholder.
        #
        # Consumers should perform a second-pass if precise inheritance for
        # unmarked body chunks matters.
        return SectionAssignment(
            chapter_id=None,
            chapter_title=None,
            section_id=None,
            section_title=None,
            depth=1,
        )

    # --------------------------------------------------------------------
    # Private helpers
    # --------------------------------------------------------------------

    def _assignment_from_number(
        self,
        number: str,
        element_type: str | None,
    ) -> SectionAssignment:
        """Build a :class:`SectionAssignment` from a dot-delimited number."""
        parts = number.strip().split(".")
        chapter_id_str = parts[0]
        try:
            chapter_id = int(chapter_id_str)
        except ValueError:
            chapter_id = None

        depth = len(parts)

        # Look up canonical title from TOC if available
        chapter_title: str | None = None
        section_title: str | None = None

        for entry in self._toc:
            if entry.number == number:
                section_title = entry.title
                break
            if entry.number == chapter_id_str:
                chapter_title = entry.title

        return SectionAssignment(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            section_id=number.strip(),
            section_title=section_title,
            depth=depth,
        )

    def _assignment_from_toc_entry(
        self,
        entry: TOCEntry,
        toc_index: int,
    ) -> SectionAssignment:
        """Convert a TOCEntry and its position into a SectionAssignment."""
        parts = entry.number.split(".")
        try:
            chapter_id = int(parts[0])
        except ValueError:
            chapter_id = None

        # Resolve chapter title from the nearest level-1 ancestor
        chapter_title: str | None = None
        if entry.level > 1:
            for prev in reversed(self._toc[:toc_index]):
                if prev.level == 1:
                    chapter_title = prev.title
                    break

        return SectionAssignment(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            section_id=entry.number,
            section_title=entry.title,
            depth=entry.level,
        )

    def _find_closest_toc_entry(self, char_position: int) -> int | None:
        """
        Return the index of the TOC entry whose char span is closest to *char_position*.

        Prefer entries that precede or bracket the position.
        When two entries are equidistant, prefer the earlier one.
        """
        if not self._toc:
            return None

        # Binary search for largest TOC entry.start <= char_position
        lo, hi = 0, len(self._toc) - 1
        best: int | None = None

        while lo <= hi:
            mid = (lo + hi) // 2
            entry_span = getattr(self._toc[mid], "char_start", 0)
            if entry_span <= char_position:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        return best
