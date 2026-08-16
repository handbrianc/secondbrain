"""Pure helpers and constants for the RAG pipeline."""

import logging
import re

logger = logging.getLogger(__name__)


def filter_chapters_by_target(
    chapters_to_cover: list[tuple[int, str, str]],
    good_title_nums: set[int],
    target: str | None,
) -> tuple[list[tuple[int, str, str]], set[int]]:
    """Scope *chapters_to_cover* to only the chapter matching *target*."""
    if target is not None and chapters_to_cover:
        try:
            target_num = int(target)
            chapters_to_cover = [
                (m, s, t) for m, s, t in chapters_to_cover if m == target_num
            ]
            good_title_nums = {n for n in good_title_nums if n == target_num}
        except (ValueError, TypeError):
            logger.warning(
                "Invalid chapter target '%s' — falling back to full enumeration",
                target,
            )
    return chapters_to_cover, good_title_nums


BROAD_COVERAGE_TRIGGERS: frozenset[str] = frozenset(
    [
        "all",
        "every",
        "each",
        "summarize each",
        "summary of each",
        "list every",
        "list all sections",
        "list all chapters",
        "brief on each",
        "overview of all",
        "give me an overview",
        "comprehensive summary",
    ]
)

CHAPTER_ENUMERATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chapter", re.I),
    re.compile(r"\bch\.?\s*\d+\b", re.I),
    re.compile(
        r"(?<!\w)(\d{1,2})\s*\.{1,3}(?:intro|overview|summary|introduction)",
        re.I,
    ),
]

ENUMERATE_CHAPTER_SIGNALS: frozenset[str] = frozenset(
    [
        "all",
        "every",
        "each",
        "list",
        "summarize",
        "overview",
        "summary",
        "give me",
        "enumerate",
    ]
)
