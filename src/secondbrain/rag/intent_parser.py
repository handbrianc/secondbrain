"""Intent parser for classifying user query intents in the RAG pipeline.

Provides StructuralIntentParser which replaces the legacy
`_is_enumerate_chapters_query` and `_is_broad_coverage_query` methods
from rag.pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from secondbrain.logging import get_logger

logger = get_logger(__name__)


class QueryIntent(StrEnum):
    """Enumeration of recognized query intent types."""

    CHAPTER_ENUMERATE = "chapter_enumerate"
    """Query asks to enumerate/list chapters (e.g. "what chapters does this have")."""
    SECTION_ENUMERATE = "section_enumerate"
    """Query asks to list sections within a specific chapter (e.g. "list sections in chapter 4")."""
    BROAD_COVERAGE = "broad_coverage"
    """Query asks for comprehensive/overview treatment (e.g. "tell me everything about X")."""
    SPECIFIC_ANSWER = "specific_answer"
    """Query is a focused factual question."""
    LIST_SOURCES = "list_sources"
    """Query asks to enumerate the distinct sources in the store (e.g. "list all sources")."""
    UNKNOWN = "unknown"
    """Intent could not be determined."""


@dataclass
class IntentDecision:
    """Result of intent classification for a user query."""

    intent: QueryIntent
    """Detected intent category."""
    confidence: float
    """Confidence score in [0.0, 1.0]; higher is more confident."""
    target: str | None
    """Extracted target identifier (e.g. "3" for "chapter 3") or None."""
    reason: str
    """Human-readable explanation of why this decision was made."""
    suggested_pipeline: str
    """Recommended pipeline strategy: "structural", "semantic", or "hybrid"."""


# -------------------------------------------------------------------
# Target-extraction regular expressions
# -------------------------------------------------------------------

CHAPTER_NUM_RE = re.compile(r"chapter\s+(\d+)", re.I)
SECTION_NUM_RE = re.compile(r"(?:section\s+)?(\d+(?:\.\d+)+)", re.I)


# -------------------------------------------------------------------
# Confidence thresholds
# -------------------------------------------------------------------

_MIN_CONFIDENCE_THRESHOLD = 0.3


class StructuralIntentParser:
    """Classifier for structurally-scoped user queries.

    Unifies the detection logic previously spread across two pipeline methods:
    - `_is_enumerate_chapters_query`  (now replaced by chapter-enumerate scoring)
    - `_is_broad_coverage_query`       (now replaced by broad-coverage scoring)

    Attributes
    ----------
    CHAPTER_ENUMERATE_TRIGGERS :
        Phrase fragments indicative of chapter-enumeration intent.
    SECTION_ENUMERATE_TRIGGERS :
        Phrase fragments indicative of section-enumeration intent.
    BROAD_COVERAGE_TRIGGERS :
        Phrase fragments indicative of broad/coverage intent.
    """

    CHAPTER_ENUMERATE_TRIGGERS: ClassVar[list[str]] = [
        # NOTE: "summarize" alone is deliberately excluded from this list.
        # It appears in BROAD_COVERAGE_TRIGGERS and queries like
        # "summarize the proxmox admin guide by chapter with details"
        # should NOT trigger chapter enumeration — the user wants an
        # overall summary, not per-chapter breakdown.  Only explicit
        # enumeration phrases ("summarize chapter N", "list all chapters",
        # "each chapter", etc.) should trigger CHAPTER_ENUMERATE.
        "summarize chapter",
        "summarize each",
        "what chapters",
        "what chapters are",
        "list the chapters",
        "list all chapters",
        "all chapters",
        "each chapter",
        "every chapter",
        "chapter structure",
        "how many chapters",
        "outline of",
        "table of contents",
        "sections does this have",
        "what sections",
    ]

    SECTION_ENUMERATE_TRIGGERS: ClassVar[list[str]] = [
        "list sections in",
        "sections of chapter",
        "sections in chapter",
        "what sections does chapter",
        "sub-sections",
    ]

    # NOTE: Specific factual questions ("what is X", "explain X", "describe X",
    # "how does X", "why is X", "tell me about X", ...) are intentionally NOT
    # listed here. They are excluded so they no longer classify as BROAD_COVERAGE
    # and get routed to the heavy structural chapter dump. Instead they fall
    # through to the UNKNOWN / semantic single-shot path, which has the relevance
    # gate (_has_relevant_chunks) and the LLM-knowledge fallback
    # (_handle_no_results) that correctly answers when no relevant docs are found.
    # Only genuinely structural/comprehensive triggers belong here.
    BROAD_COVERAGE_TRIGGERS: ClassVar[list[str]] = [
        "summarize",
        "summarize each",
        "tell me everything",
        "everything about",
        "overview of",
        "give me an overview",
        "comprehensive",
        "complete guide to",
        "all about",
        "summary of",
    ]

    # Triggers that ask to enumerate the distinct sources/documents stored.
    # These are matched against substrings, so broad phrasings ("list the
    # sources you have stored", "all unique sources", "which documents")
    # all fire here.  Deliberately disjoint from CHAPTER/SECTION/BROAD
    # triggers so they never collide with structural or coverage queries.
    LIST_SOURCES_TRIGGERS: ClassVar[list[str]] = [
        "list all sources",
        "list sources",
        "list the sources",
        "list unique sources",
        "list your sources",
        "all unique sources",
        "what sources",
        "what sources do you have",
        "sources do you have",
        "sources that you have",
        "sources you have",
        "sources stored",
        "available sources",
        "list all documents",
        "list documents",
        "list the documents",
        "list your documents",
        "what documents do you have",
        "documents do you have",
        "documents that you have",
        "all documents stored",
        "which documents are stored",
        "list all unique",
    ]

    def __init__(
        self,
        config: object | None = None,
    ) -> None:
        """Initialize the intent parser.

        Parameters
        ----------
        config :
            Optional parser configuration. Currently unused but accepted
            for future extension. Kept isolated to avoid importing
            ``rag.pipeline`` and creating a circular dependency.
        """
        self._cfg = config

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def parse(self, query: str) -> IntentDecision:
        """Classify a query string into an :class:`IntentDecision`.

        Parameters
        ----------
        query :
            Raw user query string.

        Returns
        -------
        IntentDecision
            Structured result with detected intent, confidence, optional
            extracted target, explanation, and recommended pipeline strategy.
        """
        normalized = query.lower().strip()

        chapter_score = self._score_chapter_enum(normalized)
        section_score = self._score_section_enum(normalized)
        broad_score = self._score_broad_coverage(normalized)
        list_score = self._score_list_sources(normalized)

        candidates: list[tuple[float, QueryIntent, str | None, str]] = []

        if list_score >= _MIN_CONFIDENCE_THRESHOLD:
            reason = _build_reason("source listing", list_score, normalized)
            candidates.append(
                (list_score, QueryIntent.LIST_SOURCES, None, reason)
            )

        if chapter_score >= _MIN_CONFIDENCE_THRESHOLD:
            target = _extract_chapter_target(normalized)
            reason = _build_reason("chapter enumeration", chapter_score, normalized)
            candidates.append(
                (chapter_score, QueryIntent.CHAPTER_ENUMERATE, target, reason)
            )

        if section_score >= _MIN_CONFIDENCE_THRESHOLD:
            target = _extract_section_target(normalized)
            reason = _build_reason("section enumeration", section_score, normalized)
            candidates.append(
                (section_score, QueryIntent.SECTION_ENUMERATE, target, reason)
            )

        if broad_score >= _MIN_CONFIDENCE_THRESHOLD:
            target = _extract_chapter_target(normalized)  # e.g. "chapter 3"
            reason = _build_reason("broad coverage", broad_score, normalized)
            candidates.append((broad_score, QueryIntent.BROAD_COVERAGE, target, reason))

        if not candidates:
            return IntentDecision(
                intent=QueryIntent.UNKNOWN,
                confidence=0.0,
                target=None,
                reason="No structural signals exceeded the minimum confidence threshold.",
                suggested_pipeline="semantic",
            )

        def _rank(c: tuple[float, QueryIntent, str | None, str]) -> tuple[bool, float]:
            structural_priority = (
                c[1] == QueryIntent.CHAPTER_ENUMERATE
                and "chapter" in normalized
                and any(k in normalized for k in ("summarize", "overview", "summary"))
            )
            return (structural_priority, c[0])

        best_score, best_intent, best_target, best_reason = max(candidates, key=_rank)
        pipeline = _suggest_pipeline(best_intent, best_target)

        return IntentDecision(
            intent=best_intent,
            confidence=round(best_score, 2),
            target=best_target,
            reason=best_reason,
            suggested_pipeline=pipeline,
        )

    # -----------------------------------------------------------------
    # Per-intent scoring helpers
    # -----------------------------------------------------------------

    def _score_chapter_enum(self, query: str) -> float:
        """Score a lower-case query for chapter-enumeration intent.

        Score factors
        -------------
        - Trigger presence (fraction of known triggers matched)
        - Exact-phrase bonus if a full trigger string is contained verbatim
        """
        return _trigger_score(query, self.CHAPTER_ENUMERATE_TRIGGERS)

    def _score_section_enum(self, query: str) -> float:
        """Score a lower-case query for section-enumeration intent."""
        return _trigger_score(query, self.SECTION_ENUMERATE_TRIGGERS)

    def _score_broad_coverage(self, query: str) -> float:
        """Score a lower-case query for broad-coverage intent."""
        return _trigger_score(query, self.BROAD_COVERAGE_TRIGGERS)

    def _score_list_sources(self, query: str) -> float:
        """Score a lower-case query for source-enumeration intent.

        Unlike the structural scorers (which use fractional overlap), a
        listing query is a hard, disjoint intent: any trigger present means
        the user wants an enumeration. Returning 1.0 on any match keeps the
        confidence above the threshold regardless of how many triggers the
        list grows to, so a single-phrase query (e.g. "list sources") is
        never diluted below detection.
        """
        if any(t in query for t in self.LIST_SOURCES_TRIGGERS):
            return 1.0
        return 0.0


# ---------------------------------------------------------------------------
# Shared scoring primitives
# ---------------------------------------------------------------------------


def _trigger_score(query: str, triggers: list[str]) -> float:
    """Compute a 0.0-1.0 confidence score based on trigger overlap.

    Parameters
    ----------
    query :
        Lower-cased, stripped query string.
    triggers :
        List of trigger phrase fragments to check against ``query``.

    Returns
    -------
    float
        Weighted confidence in [0.0, 1.0].
    """
    if not query:
        return 0.0

    trigger_count = len(triggers)

    hits = sum(1 for t in triggers if t in query)
    if hits == 0:
        return 0.0

    # Fraction of triggers matched gives a baseline score
    fraction = hits / trigger_count

    # Bonus weighting: exact phrase match is the strongest signal
    exact_hit = any(t in query for t in triggers)

    # Combine fraction with a modest exact-match bonus (cap at ~0.9 without exact)
    raw = fraction + (0.25 if exact_hit else 0.0)
    return min(raw, 1.0)


# ---------------------------------------------------------------------------
# Target extraction helpers
# ---------------------------------------------------------------------------


def _extract_chapter_target(query: str) -> str | None:
    """Extract a chapter number from ``query``.

    Returns
    -------
    str | None
        The captured digits as a string (e.g. "3") or None if no match.
    """
    m = CHAPTER_NUM_RE.search(query)
    if m is None:
        return None
    return m.group(1)


def _extract_section_target(query: str) -> str | None:
    """Extract a dotted section identifier from ``query``.

    Handles both bare dotted forms (``3.9.11``) and labelled forms
    (``section 3.9.11``).

    Returns
    -------
    str | None
        The full dotted identifier as a string or None if no match.
    """
    m = SECTION_NUM_RE.search(query)
    if m is None:
        return None
    return m.group(1)


# ---------------------------------------------------------------------------
# Result-builders
# ---------------------------------------------------------------------------


def _build_reason(intent_label: str, confidence: float, query: str) -> str:
    """Construct a human-readable reason string for an intent decision."""
    rounded = round(confidence * 100)
    return f"Query '{query}' classified as {intent_label} with {rounded}% confidence."


def _suggest_pipeline(intent: QueryIntent, target: str | None) -> str:
    """Recommend a pipeline strategy based on detected intent and target."""
    if intent in (
        QueryIntent.CHAPTER_ENUMERATE,
        QueryIntent.SECTION_ENUMERATE,
        QueryIntent.LIST_SOURCES,
    ):
        return "structural"
    if intent is QueryIntent.BROAD_COVERAGE and target is None:
        return "structural"
    if intent is QueryIntent.BROAD_COVERAGE and target is not None:
        return "hybrid"
    return "semantic"
