"""Section-bounded retrieval wrapper for semantic search.

Adds section-scopes to filter results to specific book sections when a
structural query like "section 3.9" or "chapter 4 overview" is detected.
For non-structural queries, delegates transparently to the underlying searcher.

Designed to slot into rag/pipeline.py's _iterative_query() dedup gate,
preserving the existing hash-set dedup rather than replacing it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass

__all__ = ["ScopedRetriever"]


class Searcher(Protocol):
    """Structural protocol for semantic search implementations."""

    def search(
        self,
        query: str,
        *,
        top_k: int,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform synchronous semantic search returning flat result dicts."""
        ...

    async def search_async(
        self,
        query: str,
        *,
        top_k: int,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform asynchronous semantic search returning flat result dicts."""
        ...


# ---------------------------------------------------------------------------
# Scope-filter constructors
# ---------------------------------------------------------------------------

_SECTION_NUM_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")
_WILDCARD_CHAPTER_PATTERN = re.compile(r"^(?P<prefix>\d+)\.\*$")


def _build_section_filter(scope: str) -> dict[str, Any] | None:
    """Translate a scope string to a MongoDB filter clause.

    Parameters
    ----------
    scope :
        One of:
        - ``"3.9"``        specific subsection
        - ``"4.*"``        wildcard: all children of chapter 4
        - ``"heading"``    only heading / toc_entry chunks

    Returns
    -------
    A MongoDB query fragment, or ``None`` when no meaningful filter applies.
    """
    if scope == "heading":
        return {"element_type": {"$in": ["heading", "toc_entry"]}}

    # Wildcard chapter expansion  "4.*"  ->  section_id starts with "4."
    wc_match = _WILDCARD_CHAPTER_PATTERN.match(scope)
    if wc_match is not None:
        prefix = wc_match.group("prefix")
        return {"section_id": {"$regex": rf"^{re.escape(prefix)}\."}}

    # Numeric section - allow subsections via exclusive upper bound.
    # "3.9" matches "3.9", "3.9.1", "3.9.2 ..."
    if _SECTION_NUM_PATTERN.match(scope):
        major, *rest = scope.split(".")
        if rest:
            # Non-top-level chapter - compute exclusive upper bound.
            suffix_char = chr(ord(rest[-1][0]) + 1) if rest[-1] else ""
            next_minor = (
                f"{rest[-2]}.{suffix_char}" if len(rest) > 1 else suffix_char
            )
            upper_bound = f"{'.'.join(major for _ in range(len(rest)))}.{next_minor}"
            return {
                "$and": [
                    {"section_id": {"$gte": scope}},
                    {"section_id": {"$lt": upper_bound}},
                ],
            }
        else:
            # Top-level chapter "3" - tolerate bare "3" and "3.x" variants.
            return {"section_id": {"$regex": rf"^{re.escape(scope)}\."}}

    return None


def _apply_scope_filter(
    results: list[dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    """Filter chunk dicts by the parsed section scope.

    Older chunks may lack a ``section_id`` field entirely; such records are
    kept (except for numeric scopes) to avoid silently discarding legacy data.
    """
    if not scope:
        return results

    mongo_filter = _build_section_filter(scope)
    if mongo_filter is None:
        return results

    filtered: list[dict[str, Any]] = []
    for chunk in results:
        meta = chunk.get("metadata", {})
        section_id = chunk.get("section_id", meta.get("section_id"))

        if section_id is None:
            # Degrade gracefully: no section_id field -> old chunk, include it.
            # Exact-numeric "heading" scope is intentionally excluding.
            if scope != "heading":
                filtered.append(chunk)
            continue

        if _matches_filter(str(section_id), mongo_filter):
            filtered.append(chunk)

    return filtered


def _matches_filter(section_id: str, filt: dict[str, Any]) -> bool:
    """Evaluate a compiled filter against a concrete section_id."""
    # Handle $and/$or wrappers
    if "$and" in filt:
        return all(_matches_filter(section_id, sub) for sub in filt["$and"])
    if "$or" in filt:
        return any(_matches_filter(section_id, sub) for sub in filt["$or"])

    # Primitive comparisons
    for op, rhs in filt.items():
        if op == "$regex":
            if isinstance(rhs, str) and not re.search(rhs, section_id):
                return False
        elif op == "$eq":
            if section_id != rhs:
                return False
        elif op == "$gte":
            if section_id < rhs:
                return False
        elif op == "$lt" and section_id >= rhs:
            return False

    return True


# ---------------------------------------------------------------------------
# ScopedRetriever
# ---------------------------------------------------------------------------


class ScopedRetriever:
    """Wraps a Searcher with optional section-bounded filtering.

    Thin decorator around an existing :class:`Searcher` (or any compatible
    object) that adds a ``scope`` parameter to ``search`` /
    ``search_async``.  When ``scope`` is supplied and non-empty, results are
    post-filtered to the matching section before being returned; otherwise the
    call passes through unchanged.

    Intended as an insertion point for the dedup gate inside
    ``rag.pipeline.RAGPipeline._iterative_query()``, allowing it to enforce
    section boundaries alongside the pre-existing hash-set deduplication.

    Parameters
    ----------
    inner :
        Underlying searcher to wrap.
    section_classifier :
        Forward-reference placeholder for a future
        :mod:`~secondbrain.document.structure_extractor.SectionClassifier`.
        Currently unused but accepted to avoid a breaking change when the
        classifier is wired in.

    Examples
    --------
    >>> retriever = ScopedRetriever(inner=Searcher(), section_classifier=None)
    >>> results = retriever.search("main results", top_k=10, scope="3.9")
    """

    __slots__ = ("_inner", "_section_classifier")

    def __init__(
        self,
        inner: Searcher,
        section_classifier: object | None = None,
    ) -> None:
        self._inner = inner
        self._section_classifier = section_classifier

    # ------------------------------------------------------------------
    # search - synchronous
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        scope: str | None = None,
        recency_boost_hours: int = 168,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search with optional section bounding.

        Parameters
        ----------
        query :
            Semantic search string.
        top_k :
            Maximum number of results to return after scoping.
        scope :
            Optional section constraint - see :func:`_build_section_filter`.
        recency_boost_hours :
            Reserved for future use; currently ignored.
        **kwargs :
            Additional forward kwargs passed to the inner searcher.

        Returns
        -------
        List of result dicts, optionally post-filtered to the requested scope.
        """
        raw: list[dict[str, Any]] = self._inner.search(
            query, top_k=top_k, **kwargs
        )

        if not scope:
            return raw

        return _apply_scope_filter(raw, scope)

    # ------------------------------------------------------------------
    # search_async - asynchronous
    # ------------------------------------------------------------------

    async def search_async(
        self,
        query: str,
        *,
        top_k: int = 5,
        scope: str | None = None,
        recency_boost_hours: int = 168,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Async search with optional section bounding.

        Signature mirrors :meth:`search`; see that method for parameter detail.
        """
        raw: list[dict[str, Any]] = await self._inner.search_async(
            query, top_k=top_k, **kwargs
        )

        if not scope:
            return raw

        return _apply_scope_filter(raw, scope)
