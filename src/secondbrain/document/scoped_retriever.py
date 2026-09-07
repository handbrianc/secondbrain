"""Section-bounded retrieval wrapper for semantic search.

Adds section-scopes to filter results to specific book sections when a
structural query like "section 3.9" or "chapter 4 overview" is detected.
For non-structural queries, delegates transparently to the underlying searcher.

Designed to slot into rag/pipeline.py's _iterative_query() dedup gate,
preserving the existing hash-set dedup rather than replacing it.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

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
_HEADING_ROLES = ("heading", "toc_entry")


def _build_section_filter(scope: str) -> dict[str, Any] | None:
    """Translate a scope string to a filter clause.

    Parameters
    ----------
    scope :
        One of:
        - ``"3.9"``        specific subsection
        - ``"4.*"``        wildcard: all children of chapter 4

    Returns
    -------
    A query filter fragment, or ``None`` when no meaningful filter applies.
    """
    # Wildcard chapter expansion  "4.*"  ->  section_id starts with "4."
    wc_match = _WILDCARD_CHAPTER_PATTERN.match(scope)
    if wc_match is not None:
        prefix = wc_match.group("prefix")
        return {"section_id": {"$regex": rf"^{re.escape(prefix)}\."}}

    # Numeric section - prefix match (handles subsections).
    # "3.9" matches "3.9", "3.9.1", "3.9.2", ...
    if _SECTION_NUM_PATTERN.match(scope):
        return {"section_id": {"$regex": rf"^{re.escape(scope)}(?:\.|$)"}}

    return None


def _filter_heading_scope(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep chunks whose role fields mark them as heading or toc_entry.

    The role is read from the chunk payload first, then its metadata mapping,
    falling back from ``element_type`` to ``chunk_role`` for chunks written
    before the element_type field existed. Chunks lacking both fields predate
    role tracking entirely and are kept rather than silently dropped.

    Parameters
    ----------
    results :
        Flat chunk dicts as returned by the inner searcher.
    """
    kept: list[dict[str, Any]] = []
    for chunk in results:
        meta = chunk.get("metadata", {})
        role = chunk.get("element_type") or meta.get("element_type")
        if role is None:
            role = chunk.get("chunk_role") or meta.get("chunk_role")
        if role is None or role in _HEADING_ROLES:
            kept.append(chunk)
    return kept


def _apply_scope_filter(
    results: list[dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    """Filter chunk dicts by the parsed section scope.

    Older chunks may lack a ``section_id`` field entirely; such records are
    kept (except for numeric scopes) to avoid silently discarding legacy data.
    The ``heading`` scope is evaluated against role fields instead of
    ``section_id``: chunks whose ``element_type`` (falling back to
    ``chunk_role``) is ``heading`` or ``toc_entry`` are kept, as are chunks
    predating both fields.
    """
    if not scope:
        return results

    if scope == "heading":
        return _filter_heading_scope(results)

    filter_clause = _build_section_filter(scope)
    if filter_clause is None:
        return results

    filtered: list[dict[str, Any]] = []
    for chunk in results:
        meta = chunk.get("metadata", {})
        section_id = chunk.get("section_id", meta.get("section_id"))

        if section_id is None:
            # Degrade gracefully: no section_id field -> old chunk, include it.
            filtered.append(chunk)
            continue

        if _matches_filter({"section_id": str(section_id)}, filter_clause):
            filtered.append(chunk)

    return filtered


def _matches_filter(record: dict[str, Any], filt: dict[str, Any]) -> bool:
    """Evaluate a compiled filter fragment against a chunk field mapping."""
    if "$and" in filt:
        return all(_matches_filter(record, sub) for sub in filt["$and"])
    if "$or" in filt:
        return any(_matches_filter(record, sub) for sub in filt["$or"])

    for field, clause in filt.items():
        value = record.get(field)
        if value is None or not _match_clause(str(value), clause):
            return False

    return True


def _match_clause(value: str, clause: dict[str, Any]) -> bool:
    """Evaluate one field's operator clause against a concrete string value."""
    for op, rhs in clause.items():
        if op == "$regex":
            if isinstance(rhs, str) and not re.search(rhs, value):
                return False
        elif op == "$eq":
            if value != rhs:
                return False
        elif op == "$in":
            if value not in rhs:
                return False
        elif op == "$gte":
            if value < rhs:
                return False
        elif op == "$lt" and value >= rhs:
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
        raw: list[dict[str, Any]] = self._inner.search(query, top_k=top_k, **kwargs)

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
