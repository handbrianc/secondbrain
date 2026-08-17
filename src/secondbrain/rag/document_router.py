"""Document-level routing for RAG pipeline.

Provides fuzzy document name matching against ingested documents
to scope retrieval to a specific document when the user mentions
a document by name in their query (e.g. "virtual box user manual").
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SIMILARITY_THRESHOLD = 0.3
_REGISTRY_CACHE_TTL = 60.0  # seconds

# Ambiguous single-word document tokens that are too generic to uniquely
# identify a document when they appear alone in a query.  These commonly arise
# when _build_known_names splits a basename into individual tokens; matching on
# them alone would scope to the wrong (or an unintended) source.
_GENERIC_NAME_TOKENS = frozenset(
    {
        "guide",
        "manual",
        "report",
        "book",
        "readme",
        "notes",
        "text",
        "license",
        "changelog",
        "home",
        "faq",
        "intro",
        "summary",
        "contents",
        "overview",
        "misc",
        "draft",
        "final",
        "chapter",
        "section",
        "appendix",
        "figure",
        "table",
    }
)


# Regex patterns for detecting document titles in chunk content
_CHAPTER_TITLE_RE = re.compile(
    r"chapter\s+\d+\s+[-]\s+(.{2,80})",
    re.IGNORECASE,
)
_ABOUT_TITLE_RE = re.compile(
    r"(?:about|introducing|overview of|welcome to)\s+(.{2,80})",
    re.IGNORECASE,
)
_HEADING1_RE = re.compile(
    r"^#{1,3}\s+(.{2,80})",
    re.MULTILINE,
)


def _normalize_name(name: str) -> str:
    """Normalize a document name for fuzzy matching.

    Lowercases, strips common file extensions, replaces separators.
    """
    name = name.lower().strip()
    name = re.sub(r"[_-]", " ", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\.(pdf|docx?|xlsx?|pptx?|txt|md|html?|csv)$", "", name)
    return name.strip()


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _build_known_names(source_files: list[str]) -> dict[str, str]:
    """Build a mapping of normalized document names to source_file paths.

    For each source file path, registers:
    - The full normalized filename (without extension)
    - The basename without extension as a short alias
    - Individual tokens for names with separators (e.g. "virtualbox" from "VirtualBox_UserManual")
    - A compressed (no-space) version for substring matching
    """
    registry: dict[str, str] = {}
    for sf in source_files:
        base = sf.rsplit("/", 1)[-1] if "/" in sf else sf
        base = base.rsplit("\\", 1)[-1] if "\\" in sf else base
        normalized = _normalize_name(base)
        if normalized:
            registry[normalized] = sf
            compressed = normalized.replace(" ", "")
            if compressed and compressed != normalized:
                registry[compressed] = sf
            for token in normalized.split():
                if len(token) >= 3 and token not in registry:
                    registry[token] = sf
        name_no_ext = re.sub(r"\.[^.]+$", "", base).lower().strip()
        if name_no_ext and name_no_ext != normalized:
            registry[name_no_ext] = sf
    return registry


class DocumentRouter:
    r"""Resolves document mentions in user queries to MongoDB source_file paths.

    Maintains a fuzzy-match registry of all ingested document filenames
    extracted from the vector store at construction time (with TTL caching).

    Usage::

        router = DocumentRouter(storage=vector_storage)
        doc_name = router.extract_document_name(
            "tell me about virtual box user manual chapter 3"
        )
        source_file = router.resolve_source_file(doc_name)
        # source_file -> \"/path/to/VirtualBox_UserManual.pdf\"
    """

    def __init__(
        self,
        storage: Any | None = None,
        known_names: dict[str, str] | None = None,
    ) -> None:
        """Initialize the DocumentRouter.

        Args:
            storage: Optional VectorStorage/AsyncVectorStorage instance for
                querying source files from MongoDB. Required unless
                ``known_names`` is provided (for testing).
            known_names: Pre-built name→source_file mapping for testing
                or when storage is not available.
        """
        self._storage = storage
        self._known_names: dict[str, str] = known_names or {}
        self._registry_loaded = known_names is not None
        self._registry_ts: float = 0.0

    @staticmethod
    def _extract_title_aliases(
        source_files: list[str],
        storage: Any,
    ) -> dict[str, str]:
        """Extract content-based title aliases for documents.

        For each ``source_file``, queries the first few chunks for structural
        headings (``"Chapter 1 — About Oracle VirtualBox"``) and adds those
        title keywords to the registry.  Also extracts the first-line title
        from the very first chunk as a fallback.
        """
        aliases: dict[str, str] = {}
        try:
            coll = storage.collection
            for sf in source_files:
                title_keywords: set[str] = set()
                cursor = (
                    coll.find(
                        {"source_file": sf},
                        {"chunk_text": 1},
                    )
                    .sort("page_number", 1)
                    .limit(5)
                )
                docs = list(cursor)

                for doc in docs:
                    text = doc.get("chunk_text", "")
                    # "Chapter 1 — About Oracle VirtualBox"
                    for m in _CHAPTER_TITLE_RE.finditer(text):
                        title = m.group(1).strip()
                        for tok in _normalize_name(title).split():
                            if len(tok) >= 4:
                                title_keywords.add(tok)
                    # "About Oracle VirtualBox" / "Introducing ..."
                    for m in _ABOUT_TITLE_RE.finditer(text):
                        title = m.group(1).strip()
                        for tok in _normalize_name(title).split():
                            if len(tok) >= 4:
                                title_keywords.add(tok)
                    for m in _HEADING1_RE.finditer(text):
                        title = m.group(1).strip()
                        for tok in _normalize_name(title).split():
                            if len(tok) >= 4:
                                title_keywords.add(tok)

                # Fallback: extract keywords from the first ~100 chars of the
                # first chunk.  Catches cases like "PROXMOX VE ADMINISTRATION
                # GUIDE RELEASE 9.1.0" that aren't wrapped in a heading tag.
                if not title_keywords and docs:
                    first_text = docs[0].get("chunk_text", "")
                    prefix = first_text[:100].strip()
                    if prefix:
                        for tok in _normalize_name(prefix).split():
                            if len(tok) >= 4:
                                title_keywords.add(tok)

                # Register meaningful title keywords (excluding generic terms)
                generic = {
                    "chapter",
                    "section",
                    "introduction",
                    "overview",
                    "administration",
                    "release",
                }
                for kw in title_keywords:
                    if kw not in generic and kw not in aliases:
                        aliases[kw] = sf
        except Exception:
            logger.debug("Content-title extraction skipped", exc_info=True)
        return aliases

    def _ensure_registry(self) -> dict[str, str]:
        """Refresh the name registry from storage if the cache has expired."""
        now = time.monotonic()
        if self._registry_loaded and now - self._registry_ts < _REGISTRY_CACHE_TTL:
            return self._known_names
        if self._storage is not None:
            try:
                source_files = self._storage.list_source_files()
                self._known_names = _build_known_names(source_files)
                # Enhance registry with content-derived title keywords
                content_aliases = self._extract_title_aliases(
                    source_files, self._storage
                )
                for name, sf in content_aliases.items():
                    if name not in self._known_names:
                        self._known_names[name] = sf
                self._registry_loaded = True
                self._registry_ts = now
            except Exception:
                logger.warning(
                    "Failed to refresh document registry from storage",
                    exc_info=True,
                )
        else:
            self._registry_loaded = True
            self._registry_ts = now
        return self._known_names

    def extract_document_name(self, query: str) -> str | None:
        """Extract and fuzzy-match a document name from the user query.

        Args:
            query: Raw user query string.

        Returns:
            The matched normalized document name, or None if no match found
            above the similarity threshold.
        """
        registry = self._ensure_registry()
        if not registry:
            return None

        q = _normalize_name(query)
        if not q:
            return None

        # Normalize each token so an in-sentence filename like "index.html"
        # (not at end-of-string, so _normalize_name leaves the extension)
        # still matches its bare-name registry key "index".
        query_tokens = {
            t for word in q.split() for t in _normalize_name(word).split()
        }

        # Phase 1: Jaccard similarity on token sets
        best_name: str | None = None
        best_score = 0.0

        for known_name in registry:
            known_tokens = set(known_name.split())
            overlap = query_tokens & known_tokens
            if not overlap:
                continue
            score = _jaccard_similarity(query_tokens, known_tokens)
            if score > best_score:
                best_score = score
                best_name = known_name

        if best_score >= _DEFAULT_SIMILARITY_THRESHOLD:
            return best_name

        # Phase 1.5: Containment — a document name fully present in the query.
        # Jaccard (Phase 1) penalises a short name buried among other query
        # words (e.g. "summarize index html by chapter" vs. known name "index"),
        # and the Phase-2 substring gate rejects names shorter than 6 chars.
        # When every token of a known name appears in the query the user almost
        # certainly referenced it, so match it here.  Prefer the most specific
        # (most tokens) candidate, and skip ambiguous single generic tokens.
        contained: list[tuple[int, str]] = []
        for known_name in registry:
            known_tokens = set(known_name.split())
            if not known_tokens or not known_tokens <= query_tokens:
                continue
            if len(known_tokens) == 1 and next(iter(known_tokens)) in (
                _GENERIC_NAME_TOKENS
            ):
                continue
            contained.append((len(known_tokens), known_name))
        if contained:
            return max(contained, key=lambda kv: kv[0])[1]

        # Phase 2: Substring / compressed-form fallback
        # Handles cases like "virtualbox" vs "virtual box user manual"
        # where Jaccard has no token overlap.
        # Picks the longest narrow match to avoid matching generic short
        # tokens like "guide" or "admin" that appear in many queries.
        compressed_query = q.replace(" ", "")
        best_name = None
        best_len = 0
        for known_name in registry:
            compressed_known = known_name.replace(" ", "")
            if not compressed_query or not compressed_known:
                continue
            if (
                compressed_query in compressed_known
                or compressed_known in compressed_query
            ):
                mlen = len(compressed_known)
                # Require at least 6 characters to avoid matching generic
                # short tokens (e.g. "guide", "admin") that are unreliable.
                if mlen >= 6 and mlen > best_len:
                    best_len = mlen
                    best_name = known_name

        if best_name is not None:
            return best_name

        return None

    def resolve_source_file(self, doc_name: str | None) -> str | None:
        """Resolve a matched document name to a MongoDB ``source_file`` path.

        Args:
            doc_name: A normalized document name returned by
                :meth:`extract_document_name`.

        Returns:
            The ``source_file`` path string, or None if unknown.
        """
        if doc_name is None:
            return None
        registry = self._ensure_registry()
        normalized = _normalize_name(doc_name)
        return registry.get(normalized)

    def list_available_documents(self) -> list[dict[str, str]]:
        """List all known documents with their display names and source paths.

        Returns:
            List of ``{"name": ..., "source_file": ...}`` dicts sorted by name.
        """
        registry = self._ensure_registry()
        return [
            {"name": name, "source_file": path}
            for name, path in sorted(registry.items())
        ]

    def invalidate_cache(self) -> None:
        """Force a registry refresh on the next access."""
        self._registry_loaded = False
        self._registry_ts = 0.0
