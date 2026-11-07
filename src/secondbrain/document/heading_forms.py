"""Shared numbered-heading recognition and title extraction.

Single owner of the numbered-heading forms used on both sides of the
ingest/query boundary — ingest-side structure capture (synthesis of headings
the parser missed, position-aware chunk annotation) and query-time chapter
guards (roster-title hygiene) — so the two sides cannot drift apart.

The forms mirror the guards the existing chapter scanners already enforce
(``_detect_chapter_openings`` and the bucket marker): line-initial numbers,
a bounded heading-line length, dot-leader ToC-row rejection, trailing
page-number rejection, and the 1..30 chapter bound. On top of the per-line
match this module owns title capture (line-boundary with one bounded
continuation line, taken only when the first line ends dangling or the next
line is a single word — titles never glue across arbitrary body lines),
word-boundary trimming (never mid-word), the citation-row shape guard
(source-register entries are not chapter headings), and the list-context
check (a cluster of numbered lines is a list, not headings).

Pure stdlib: no pipeline, storage, or config imports.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "NumberedHeading",
    "capture_title",
    "is_list_context",
    "looks_like_citation_row",
    "match_numbered_heading",
    "scan_text",
    "trim_title",
]

# Chapter numbers are bounded exactly like every existing chapter scanner
# (bucket guard, _detect_chapter_openings): 1..30.
CHAPTER_MIN = 1
CHAPTER_MAX = 30

# A heading line is short; a longer "N. ..." line is prose that merely starts
# with a number (same bound as the bucket marker's line cap).
MAX_HEADING_LINE_CHARS = 120

# The bare chapter form needs a real title, not a stub (same minimum as the
# title line in _detect_chapter_openings); a dotted section line needs any
# non-space text (same minimum as the bucket marker's shape).
MIN_CHAPTER_TITLE_CHARS = 4

# Dot-leader runs mark flattened ToC rows; a line ENDING in a bare number is
# a ToC row's trailing page (digits inside the title text are fine).
_DOT_LEADER_RE = re.compile(r"\.{2,}")
_PAGE_SUFFIX_RE = re.compile(r"\d+\s*$")

# Bare chapter form: line-initial number, optional separating dot, then
# title text. ``require_dot`` (synthesis mode) demands the dot so register
# rows ("7 Wikipedia — ...") never synthesize a tree node.
_CHAPTER_RE = re.compile(r"^(\d{1,2})(\.?)\s*(\S.*?)\s*$")

# Dotted section form: line-initial "N.M" with a word boundary after the
# second group, then optional title text. Tried BEFORE the chapter form so
# "7.1 Definitions" is never read as chapter 7 titled "1 Definitions".
_SECTION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\b\s*(\S.*?)\s*$")

# Sentence-terminal punctuation that ends a title (no continuation line is
# taken after it). Closing quotes/brackets after the punctuation still count
# as terminal.
_SENTENCE_END_RE = re.compile(r"[.!?;:][\"'”’)\]]?\s*$")  # noqa: RUF001

# A wrapped title's first line ends dangling: a comma, an open parenthetical
# or bracket, a dash, an ampersand, or a slash invites the one continuation
# line. A complete title ("… Testing Well", "… (Companion Report)") ends in
# none of these and takes no continuation line — body lines begin
# capitalized and would glue into the title.
_DANGLING_END_RE = re.compile(r"(?:[,\[(/&]|[-–—])\s*$")  # noqa: RUF001

# Trailing connective words that mark a dangling title end ("… Designing
# for" / "… Mindsets, Phases, and"). Lowercase only: a capitalized final
# word is a title word, not a connective.
_DANGLING_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "but",
        "by",
        "for",
        "from",
        "in",
        "into",
        "nor",
        "of",
        "on",
        "onto",
        "or",
        "the",
        "their",
        "to",
        "upon",
        "via",
        "vs",
        "with",
    }
)

# List bullets a continuation line may start with (never title text).
_BULLET_RE = re.compile(r"^(?:[-*•·]|\(?\d+[.)]\s)\s*")

# Citation shape: a spaced en/em dash inside the captured title (source
# registers list "Source — Title (Abbr)" rows; real chapter titles in this
# corpus do not carry a spaced dash right after a bare number).
_CITATION_DASH_RE = re.compile(r"\s[—–]\s")  # noqa: RUF001


@dataclass(frozen=True)
class NumberedHeading:
    """One numbered-heading line found by :func:`scan_text`.

    Attributes
    ----------
    chapter:
        The chapter number (1..30) the line names.
    section:
        The section number for dotted ``N.M`` lines, else ``None``.
    title:
        The raw rest-of-line title text (not continued, not trimmed).
    line_index:
        Index of the line within the scanned text.
    char_offset:
        Character offset of the line's start within the scanned text.
    """

    chapter: int
    section: int | None
    title: str
    line_index: int
    char_offset: int


def match_numbered_heading(
    line: str, *, require_dot: bool = False
) -> tuple[int, int | None, str] | None:
    """Match one line against the numbered-heading forms.

    The dotted section form is tried first, then the bare chapter form, so a
    ``7.1 Definitions`` line is never read as chapter 7 titled
    ``1 Definitions``. A line that fails any guard (length, number bounds,
    dot-leader, trailing page number, title minimums, bare-form
    capitalization) yields ``None`` — a line that could never open a chapter
    also cannot be synthesized from.

    Parameters
    ----------
    line:
        One candidate line (stripped by the caller or not; matching strips).
    require_dot:
        When ``True`` the bare chapter form demands the separating dot
        (synthesis mode: "9. Krippendorff's ..." qualifies, "7 Wikipedia ..."
        does not). Dotted ``N.M`` lines are unaffected.

    Returns
    -------
    tuple[int, int | None, str] | None
        ``(chapter, section, raw_title)`` for the first form that matches
        with all guards passing, else ``None``.
    """
    text = line.strip()
    if not text or len(text) > MAX_HEADING_LINE_CHARS:
        return None

    section_match = _SECTION_RE.match(text)
    if section_match:
        chapter = int(section_match.group(1))
        section = int(section_match.group(2))
        title = section_match.group(3).strip()
        if not (CHAPTER_MIN <= chapter <= CHAPTER_MAX):
            return None
        if not (CHAPTER_MIN <= section <= CHAPTER_MAX):
            return None
        if _DOT_LEADER_RE.search(text) or _PAGE_SUFFIX_RE.search(text):
            return None
        return (chapter, section, title)

    chapter_match = _CHAPTER_RE.match(text)
    if chapter_match:
        dot = chapter_match.group(2)
        if require_dot and not dot:
            return None
        chapter = int(chapter_match.group(1))
        title = chapter_match.group(3).strip()
        if not (CHAPTER_MIN <= chapter <= CHAPTER_MAX):
            return None
        if len(title) < MIN_CHAPTER_TITLE_CHARS:
            return None
        # Real chapter titles start capitalized (same rule as
        # _detect_chapter_openings' title-line check); digit- or
        # lowercase-leading stubs are list items or prose.
        if not title[0].isupper():
            return None
        if _DOT_LEADER_RE.search(text) or _PAGE_SUFFIX_RE.search(text):
            return None
        return (chapter, None, title)
    return None


def scan_text(text: str, *, require_dot: bool = False) -> list[NumberedHeading]:
    """Scan multi-line text for numbered-heading lines with positions.

    Parameters
    ----------
    text:
        The chunk or page text to scan.
    require_dot:
        Forwarded to :func:`match_numbered_heading`.

    Returns
    -------
    list[NumberedHeading]
        Every qualifying line in reading order, carrying its line index and
        character offset so callers can reason about position within the
        text (e.g. first-half vs second-half anchoring).
    """
    found: list[NumberedHeading] = []
    offset = 0
    for line_index, line in enumerate(text.split("\n")):
        match = match_numbered_heading(line, require_dot=require_dot)
        if match is not None:
            chapter, section, title = match
            found.append(
                NumberedHeading(
                    chapter=chapter,
                    section=section,
                    title=title,
                    line_index=line_index,
                    char_offset=offset,
                )
            )
        offset += len(line) + 1
    return found


def _ends_dangling(title: str) -> bool:
    """Return True when *title* ends in a state that invites continuation.

    A wrapped heading's first line ends dangling: with a trailing comma, an
    open parenthetical or bracket, a dash, an ampersand, a slash, or a
    trailing lowercase connective word ("… Mindsets, Phases, and" /
    "… Designing for"). A complete title ("… Testing Well", "… It Doesn't",
    "… (Companion Report)") is not dangling and takes no continuation line,
    so a following body line — which begins capitalized — cannot glue into
    the title.

    Args:
        title: The heading line's captured title text.

    Returns
    -------
        True when the one bounded continuation line may be considered.
    """
    text = title.rstrip()
    if not text:
        return False
    if _DANGLING_END_RE.search(text):
        return True
    word = re.search(r"[A-Za-z']+$", text)
    return bool(word and word.group(0).islower() and word.group(0) in _DANGLING_WORDS)


def _is_single_word(line: str) -> bool:
    """Return True when *line* is one whitespace-delimited word.

    A wrapped heading's orphan word ("… Working Table and Common" +
    "Failures", "… from HCD" + "Theater") is a title continuation even
    though the first line ends complete. A body line is never a single
    word.

    Args:
        line: The stripped candidate continuation line.

    Returns
    -------
        True when the line carries exactly one token.
    """
    return bool(line) and " " not in line


def capture_title(line: str, next_line: str | None) -> str:
    """Capture a heading title at line boundaries with bounded continuation.

    The title is the heading line's own text; exactly one continuation line
    may be joined (wrapped printed headings), and only when the heading line
    itself ends dangling — a trailing comma, dash, open parenthetical, or
    connective word ("… Mindsets, Phases, and" + "Methods") — or the next
    line is a single word ("… Working Table and Common" + "Failures"), and
    the next line is not itself a heading, a bullet, a dot-leader ToC row,
    or a trailing-page-number row. A complete title followed by multi-word
    body prose ("… Testing Well" + "Usability testing means…") never takes a
    continuation line, so body lines never glue into a title.

    Parameters
    ----------
    line:
        The heading line's title text (already extracted from the number by
        the caller).
    next_line:
        The raw line following the heading line, or ``None``.

    Returns
    -------
    str
        The whitespace-normalized title, possibly with one continuation
        line joined by a single space.
    """
    title = " ".join(line.split())
    if not next_line:
        return title
    if _SENTENCE_END_RE.search(title):
        return title
    nxt = next_line.strip()
    if not nxt:
        return title
    if not nxt[0].isupper():
        return title
    if _BULLET_RE.match(nxt):
        return title
    if match_numbered_heading(next_line) is not None:
        return title
    if _DOT_LEADER_RE.search(nxt) or _PAGE_SUFFIX_RE.search(nxt):
        return title
    if not (_ends_dangling(title) or _is_single_word(nxt)):
        return title
    return f"{title} {' '.join(nxt.split())}"


def trim_title(title: str, cap: int = 80) -> str:
    """Trim a captured title at a word boundary.

    A title within *cap* characters is returned whitespace-normalized and
    unchanged; a longer title is cut back to the last whole word before the
    cap (never mid-word), with trailing separator punctuation stripped.

    Parameters
    ----------
    title:
        The captured title.
    cap:
        Maximum kept length (same 80-character budget the legacy regex
        class applied, now applied on a word boundary).

    Returns
    -------
    str
        The trimmed title.
    """
    squashed = " ".join(title.split())
    if len(squashed) <= cap:
        return squashed
    cut = squashed[:cap]
    # Keep the last whole word fully inside the cap.
    space = cut.rfind(" ")
    if space <= 0:
        return squashed
    trimmed = cut[:space].rstrip()
    return trimmed.rstrip(" ,;:-–—/(")  # noqa: RUF001


def looks_like_citation_row(title: str) -> bool:
    """Return True for source-register citation rows shaped like titles.

    A register entry reads "Wikipedia — The Design of Everyday Things (D.
    Norman, 1988/2013)" (often line-wrapped so the parenthetical arrives
    unclosed): a spaced en/em dash separator plus a parenthetical that is a
    citation — a compact abbreviation with no inner spaces ("(Doet…)"), a
    comma- or four-digit-year-bearing note ("(D. Norman, 1988/2013)"), or
    one left unclosed at the title's end ("... (D. Norman,"). Real chapter
    titles with a prose parenthetical ("... (The Basics)") stay capturable.

    Parameters
    ----------
    title:
        The captured title text.

    Returns
    -------
    bool
        ``True`` when the title carries the citation shape.
    """
    if not _CITATION_DASH_RE.search(title):
        return False
    if re.search(r"\([^)]*$", title):
        return True
    for match in re.finditer(r"\(([^)]*)\)", title):
        inner = match.group(1)
        if not inner:
            continue
        if " " not in inner.strip():
            return True
        if "," in inner or re.search(r"\b\d{4}\b", inner):
            return True
    return False


def is_list_context(lines: Sequence[str], index: int) -> bool:
    """Return True when the line at *index* sits inside a numbered list.

    Two or more OTHER numbered-heading-shaped lines within a ±3-line window
    mark a list or register cluster (step lists, source registers), not a
    lone chapter heading. The check is context for the caller: a heading
    line itself still matches; the caller decides what the context means.

    Parameters
    ----------
    lines:
        The text's lines.
    index:
        Index of the candidate line.

    Returns
    -------
    bool
        ``True`` when the surrounding window carries ≥2 other numbered
        lines.
    """
    window = lines[max(0, index - 3) : index + 4]
    others = 0
    for offset, line in enumerate(window):
        line_index = max(0, index - 3) + offset
        if line_index == index:
            continue
        if match_numbered_heading(line) is not None:
            others += 1
    return others >= 2
