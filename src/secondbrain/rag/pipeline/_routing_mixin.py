"""Chunk routing/page-boundary helpers for the RAG pipeline."""

from __future__ import annotations

import asyncio
import itertools
import logging
import re
from typing import Any

from secondbrain.conversation import ConversationSession
from secondbrain.document.fast_text import footer_page_offset
from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.rag.pipeline._text_quality import _FUNCTION_WORDS

logger = logging.getLogger(__name__)

_PAGE_REF_RE = re.compile(r"\bpage\s+(\d{1,4})\b", re.IGNORECASE)


# Leading "[ N ]" stub inserted by the fast-PDF extractor for the printed page
# number; it is extraction noise, not page content, so it is stripped from
# verbatim page output.
_PAGE_MARKER_RE = re.compile(r"^\[\s*\d{1,4}\s*\]\s*")


# A whole line that is just "[ N ]" — the printed-page-number stub may appear on
# its own line (e.g. under a section heading) rather than at the chunk start.
_PAGE_STUB_LINE_RE = re.compile(r"^\s*\[\s*\d{1,4}\s*\]\s*$", re.MULTILINE)


# A whole line shaped "N / total" — the LaTeX-stamped printed-page footer
# extracted as a standalone navigation chunk.  Verification noise like the
# bracket stub above, so it is stripped from verbatim page output too.
_PAGE_FOOTER_LINE_RE = re.compile(r"^\s*\d{1,4}\s*/\s*\d{1,4}\s*$", re.MULTILINE)


def _boundary_overlap(prev: str, nxt: str) -> int:
    """Longest k such that ``prev[-k:] == nxt[:k]`` (collapse chunk overlap)."""
    max_k = min(len(prev), len(nxt))
    for k in range(max_k, 0, -1):
        if prev[-k:] == nxt[:k]:
            return k
    return 0


class _RoutingMixin(_RAGPipelineState):
    """Document routing, source-filter, and query-intent helpers."""

    # Definitional query shapes ("what is X", "define X", "what does X mean").
    # Fired only in the GENERIC retrieval paths (query/query_async/
    # _generic_one_shot) — the structural paths have their own machinery.
    _DEFINITION_QUERY_RE = re.compile(
        r"^\s*(?:what|who)\s+(?:is|are|was|were)\b(?!\s+on\s+page\b)"
        r"|\bwhat\s+does\s+[a-z0-9\- ]{2,60}\bmean\b"
        r"|\b(?:define|definition of|meaning of|explain)\b",
        re.IGNORECASE,
    )
    # Opener-adjacent body chunks are canonical definition sites in manuals;
    # this is the cap on how many extras a single union may add.
    _DEFINITION_MAX_EXTRA = 6

    @classmethod
    def _is_definition_query(cls, query: str) -> bool:
        """Return True for definitional queries ("what is X", "define X").

        The page-lookup shape ("what is on page 5") is excluded by the
        pattern itself, so the page-query branch is unaffected.
        """
        return bool(cls._DEFINITION_QUERY_RE.search(query))

    @staticmethod
    def _definition_query_keywords(query: str) -> set[str]:
        """Return significant query terms for the lexical eligibility gate."""
        return {
            w
            for w in re.findall(r"[a-z0-9][a-z0-9\-]*", query.lower())
            if len(w) >= 3 and w not in _FUNCTION_WORDS
        }

    def _union_opener_chunks(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        source_filter: str | None,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Union similarity results with chapter-opener body chunks.

        Definitional queries lose cosine contests against heading-like
        chunks: a 272-char definition paragraph scores below titles
        ("Proxmox VE Firewall" 0.867 vs the actual definition 0.792 for
        "What is Proxmox VE?"), because embeddings compress title semantics
        into the query's subspace.  A manual declares where its definitions
        live — the body chunks immediately following each chapter-opener
        heading pair (banner + title) — so recall them deterministically
        instead of hoping similarity finds them.

        Eligibility is a lexical gate (chunk shares a significant query
        keyword), not a similarity floor: structurally fetched chunks carry
        no similarity score, and the query terms must appear in the
        definition text for the recall to be on-topic.  Union is additive —
        the ranking of similarity hits is never disturbed; extras are
        appended with the structural-collection score convention (0.5, the
        same value the chapter bucket collector assigns), capped at
        _DEFINITION_MAX_EXTRA, deduped by 512-char text prefix.
        """
        if not chunks or not self._is_definition_query(query):
            return chunks
        keywords = self._definition_query_keywords(query)
        if not keywords:
            return chunks
        storage = getattr(self._searcher, "storage", None)
        if storage is None or not hasattr(storage, "find_structural_chunks"):
            return chunks

        if source_filter:
            sources = [source_filter]
        else:
            sources = list(
                dict.fromkeys(
                    str(c.get("source_file")) for c in chunks if c.get("source_file")
                )
            )[:3]
        extra: list[dict[str, Any]] = []
        try:
            for src in sources:
                openers = list(
                    storage.find_structural_chunks(
                        chunk_roles=["heading"],
                        source_prefix=src,
                    )
                )
                opener_pages = self._chapter_opener_pages(openers)
                if not opener_pages:
                    continue
                for c in storage.get_body_chunks(source_file=src):
                    if len(extra) >= self._DEFINITION_MAX_EXTRA:
                        break
                    if int(c.get("page_number") or 0) not in opener_pages:
                        continue
                    text_lower = (c.get("chunk_text") or "").lower()
                    if not any(k in text_lower for k in keywords):
                        continue
                    extra.append({**c, "score": 0.5, "definition_recall": True})
        except Exception as exc:
            logger.warning(
                "Opener-chunk union skipped (structure fetch failed): %s", exc
            )
            return chunks
        if not extra:
            return chunks
        return self._dedupe_by_text_hash([*chunks, *extra])

    @staticmethod
    def _chapter_opener_pages(openers: list[dict[str, Any]]) -> set[int]:
        """Return the pages carrying a chapter-opener heading pair.

        Docling splits each opener into a banner heading chunk ("Chapter N")
        followed by a title heading chunk on the same page; body chunks
        between that pair and the next section heading are the chapter's
        definition region.  A page counts as an opener page when a banner
        heading and a following non-banner heading share it.
        """
        opener_pages: set[int] = set()
        ordered = sorted(
            openers,
            key=lambda c: (
                int(c.get("page_number") or 0),
                int(c.get("page_pos") or 0),
            ),
        )
        banner_re = re.compile(r"^Chapter\s+\d+$", re.IGNORECASE)
        for prev, cur in itertools.pairwise(ordered):
            prev_page = int(prev.get("page_number") or 0)
            if prev_page != int(cur.get("page_number") or 0):
                continue
            if banner_re.fullmatch(
                (prev.get("chunk_text") or "").strip()
            ) and not banner_re.fullmatch((cur.get("chunk_text") or "").strip()):
                opener_pages.add(prev_page)
        return opener_pages

    # Heading chunks crowd the result set: embedding models score short
    # title-like strings ("Proxmox VE Firewall") above body prose for
    # name-shaped queries, so the top-k fills with headings that name topics
    # instead of chunks that explain them.  Keep the highest-scored few and
    # cap the rest so body content survives in the context.
    _MAX_HEADING_CHUNKS = 2

    @staticmethod
    def _apply_heading_diversity(
        chunks: list[dict[str, Any]],
        max_headings: int | None = None,
    ) -> list[dict[str, Any]]:
        """Cap heading-role chunks in a result set, preserving the first ones.

        The first *max_headings* heading chunks (in the caller's ranking
        order) are kept; later heading-role chunks are dropped — unless the
        result set is ALL headings, where capping would empty the context.
        """
        if max_headings is None:
            max_headings = _RoutingMixin._MAX_HEADING_CHUNKS
        heading_idx = [
            i for i, c in enumerate(chunks) if c.get("chunk_role") == "heading"
        ]
        if len(heading_idx) <= max_headings:
            return chunks
        if len(heading_idx) == len(chunks):
            return chunks
        drop = set(heading_idx[max_headings:])
        return [c for i, c in enumerate(chunks) if i not in drop]

    def _get_document_router(self) -> DocumentRouter:
        """Return the DocumentRouter, creating it lazily if needed."""
        if self._document_router is None:
            try:
                self._document_router = DocumentRouter(
                    storage=self._searcher.storage,
                )
            except Exception:
                self._document_router = DocumentRouter()
        return self._document_router

    def _resolve_source_filter(self, query: str) -> str | None:
        """Resolve a user query to a source_file filter if a doc is named.

        Returns a source_file path string or None if no document is referenced.
        """
        router = self._get_document_router()
        doc_name = router.extract_document_name(query)
        if doc_name is not None:
            return router.resolve_source_file(doc_name)
        return None

    def _scoped_search_query(self, query: str) -> str:
        """Return *query* with the router-resolved source reference removed.

        Scoped retrieval (``source_filter`` set) is already keyed to one
        document, so the document-name tokens in the query add no retrieval
        signal — but they pollute the query embedding (a path such as
        "/Users/.../Tampa International Airport.m4a") and depress its
        similarity against the document's own chunks. Removing the resolved
        source reference yields a cleaner embed. This is pure string work on
        the router's TTL-cached registry (the resolve just happened in the same
        flow), and prompts, results, and fallbacks keep the ORIGINAL query.

        Args:
            query: Raw user query string (or the chat-rewritten query).

        Returns:
            The query with the matched source reference replaced by a single
            space and whitespace collapsed, the original query when no name
            or matching reference is found, and the original query when
            stripping would leave nothing to embed.
        """
        router = self._get_document_router()
        doc_name = router.extract_document_name(query)
        if not doc_name:
            return query

        source_file = router.resolve_source_file(doc_name)
        patterns: list[str] = []
        if source_file:
            path_parts = re.split(r"[/\\]", source_file)
            patterns.extend(
                (
                    r"[/\\]".join(re.escape(part) for part in path_parts),
                    re.escape(path_parts[-1]),
                )
            )

        # Prefer the stored path or filename, which retains the exact original
        # reference including separators and extension. Fall back to the
        # normalized alias with word boundaries to avoid removing substrings
        # from unrelated words (for example, "meta" from "metadata").
        match = next(
            (
                found
                for pattern in patterns
                if (
                    found := re.search(
                        rf"(?<!\w){pattern}(?!\w)", query, flags=re.IGNORECASE
                    )
                )
            ),
            None,
        )
        if match is None:
            alias_parts = re.split(r"[\s_-]+", doc_name)
            alias_pattern = r"[\s_-]+".join(re.escape(part) for part in alias_parts)
            match = re.search(
                rf"(?<!\w){alias_pattern}(?!\w)", query, flags=re.IGNORECASE
            )
        if match is None:
            return query

        stripped = query[: match.start()] + " " + query[match.end() :]
        stripped = " ".join(stripped.split())
        # Fall back to the original when stripping would leave nothing to embed.
        return stripped if stripped.strip() else query

    # ------------------------------------------------------------------
    # Page-number lookup ("what is on page N")
    # ------------------------------------------------------------------

    def _answer_page_query(self, query: str) -> dict[str, Any] | None:
        """Return the verbatim text of the requested printed page, else ``None``.

        A page-number query is an exact lookup: resolve the printed page to its
        chunks and return the page text as-is. No LLM is invoked, so the output
        is the raw, complete page text with no commentary, excerpts, or truncation.
        Returns ``None`` for any query without a page reference, so the caller
        falls back to the normal semantic path and non-page queries are unaffected.
        """
        chunks = self._page_query_chunks(query)
        if chunks is None:
            return None
        if not chunks:
            return self._page_not_found(query)
        return {
            "answer": self._stitch_page_text(chunks),
            "query": query,
            "sources": chunks,
        }

    @staticmethod
    def _stitch_page_text(chunks: list[dict[str, Any]]) -> str:
        """Return the page's verbatim text by stitching *chunks* in order.

        Removes each chunk's leading ``[ N ]`` extraction stub and collapses the
        small boundary overlap between consecutive chunks so the result reads as
        a single, clean page rather than overlapping slices.
        """
        parts: list[str] = []
        for c in chunks:
            text = (c.get("chunk_text") or c.get("text") or "").strip()
            if not text:
                continue
            marker = _PAGE_MARKER_RE.match(text)
            if marker:
                text = text[marker.end() :].strip()
            if _PAGE_STUB_LINE_RE.search(text) or _PAGE_FOOTER_LINE_RE.search(text):
                text = "\n".join(
                    line
                    for line in text.splitlines()
                    if not _PAGE_STUB_LINE_RE.match(line)
                    and not _PAGE_FOOTER_LINE_RE.match(line)
                ).strip()
            if not text:
                continue
            parts.append(text)
        if not parts:
            return ""
        result = parts[0]
        for nxt in parts[1:]:
            k = _boundary_overlap(result, nxt)
            result += nxt[k:] if k else "\n" + nxt
        return result

    def _page_query_chunks(self, query: str) -> list[dict[str, Any]] | None:
        """Resolve a page-reference query to its chunks, or ``None`` to skip.

        Returns ``None`` when the query has no page reference (or the backend
        cannot do a page lookup) so the caller falls back to semantic search;
        returns ``[]`` when a referenced page has no matching chunks.

        The lookup tries, in order: the trusted ``printed_page`` stamp
        (bracket-marker or footer-derived), the "N / total" footer offset,
        and finally the PDF's physical page index only if the selected source
        has no trusted printed-page stamps at all.
        """
        printed = self._printed_page_from_query(query)
        if printed is None:
            return None
        storage = getattr(self._searcher, "storage", None)
        if storage is None or not hasattr(storage, "find_chunks"):
            return None
        source = self._resolve_source_filter(query)
        try:
            found = list(storage.find_chunks(source_file=source, printed_page=printed))
            if not found:
                found = self._footer_offset_lookup(storage, source, printed)
            if not found and not self._has_printed_page_index(storage, source):
                found = self._physical_page_lookup(storage, source, printed)
            found = self._expand_page_chunks(storage, source, found)
        except Exception as exc:  # pragma: no cover - backend-dependent
            logger.warning(
                "Page lookup failed; falling back to semantic search: %s", exc
            )
            return None
        return [dict(c) for c in found]

    @staticmethod
    def _has_printed_page_index(storage: Any, source: str | None) -> bool:
        """Return whether the selected source has any trusted printed-page stamps."""
        chunks = storage.find_chunks(source_file=source, with_text=False)
        return any(chunk.get("printed_page") is not None for chunk in chunks)

    def _physical_page_lookup(
        self,
        storage: Any,
        source: str | None,
        printed: int,
    ) -> list[dict[str, Any]]:
        """Last-resort page lookup against the physical PDF page index.

        Fires only after both the printed-page stamp and the footer offset
        missed and the selected source has no trusted printed-page stamps.
        The requested number is then interpreted as the file's Nth page.
        Chunks are tagged with ``page_lookup_fallback: "physical"`` so
        answers can disclose that the number was read as a physical index
        rather than a printed one.
        """
        try:
            found = list(storage.find_chunks(source_file=source, page_number=printed))
        except Exception:
            return []
        for c in found:
            c.setdefault("page_lookup_fallback", "physical")
        return found

    def _footer_offset_lookup(
        self,
        storage: Any,
        source: str | None,
        printed: int,
    ) -> list[dict[str, Any]]:
        """Translate a printed-page request through the "N / total" footer offset.

        Documents ingested before footer stamping existed (or extracted by an
        engine that emits no ``[ N ]`` markers) carry their printed index only
        as footer text ("78 / 634" navigation chunks).  When the direct
        ``printed_page`` lookup misses, derive the print-to-physical offset
        from those footers here and return the matching physical page's
        chunks, so the answer is page text rather than "not found".  The
        offset is trusted only when it is consistent (>= 80 % agreement over
        at least three distinct footer pages); a unique physical page number
        is looked up, and equally-printed physical pages pick the first match.
        """
        try:
            nav_chunks = list(
                storage.find_structural_chunks(
                    chunk_roles=["navigation"], source_prefix=source
                )
            )
        except Exception:
            return []
        nav_texts: dict[int, str] = {}
        for c in nav_chunks:
            physical = int(c.get("page_number") or 0)
            if physical > 0:
                nav_texts[physical] = c.get("chunk_text") or ""
        offset = footer_page_offset(nav_texts)
        if offset is None:
            return []
        physical_page = printed + offset
        try:
            found = list(
                storage.find_chunks(source_file=source, page_number=physical_page)
            )
        except Exception:
            return []
        if not found:
            return []
        for c in found:
            c.setdefault("page_lookup_offset", offset)
        return found

    @staticmethod
    def _printed_page_from_query(query: str) -> int | None:
        """Return the printed page number referenced in *query*, or ``None``."""
        match = _PAGE_REF_RE.search(query)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _expand_page_chunks(
        self,
        storage: Any,
        source: str | None,
        primary: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Broaden a page lookup to the whole physical page(s).

        ``printed_page`` is derived per-chunk from a ``[ N ]`` marker, so only the
        first chunk of a page carries it while the page's continuation chunks
        (same physical ``page_number``, no marker) are omitted. Expand to every
        chunk sharing the marker chunk's physical page so the full printed page
        is returned instead of the marker-bearing slice.
        """
        if not primary:
            return primary
        page_nums = {
            int(c["page_number"]) for c in primary if c.get("page_number") is not None
        }
        if not page_nums or not hasattr(storage, "find_chunks"):
            return primary
        try:
            full = storage.find_chunks(
                source_file=source, page_number=sorted(page_nums)
            )
        except Exception:  # pragma: no cover - backend-dependent
            return primary
        by_id: dict[str, Any] = {}
        for c in primary:
            by_id[c.get("chunk_id", id(c))] = c
        for c in full:
            by_id.setdefault(c.get("chunk_id", id(c)), c)
        merged = list(by_id.values())
        # Order within a page by the ingest ``page_pos``. Chunks lacking it
        # (pre-reingest legacy data) sort last, in their returned order.
        return sorted(
            merged,
            key=lambda c: (
                int(c.get("page_number") or -1),
                int(c["page_pos"]) if c.get("page_pos") is not None else 10**9,
            ),
        )

    def _page_not_found(self, query: str) -> dict[str, Any]:
        """Graceful answer when a referenced printed page has no chunks."""
        return {
            "answer": (
                "The available documents do not contain a page matching that "
                "number in their printed page index."
            ),
            "query": query,
            "sources": [],
        }

    async def _answer_page_query_async(self, query: str) -> dict[str, Any] | None:
        """Async twin of :meth:`_answer_page_query`.

        Resolves a "what is on page N" query to its printed-page chunks and
        returns the page text verbatim (no LLM). ``find_chunks`` is a synchronous
        storage call, so it runs via ``asyncio.to_thread`` to keep the event loop
        responsive.
        """
        chunks = await asyncio.to_thread(self._page_query_chunks, query)
        if chunks is None:
            return None
        if not chunks:
            return self._page_not_found(query)
        return {
            "answer": self._stitch_page_text(chunks),
            "query": query,
            "sources": chunks,
        }

    def _list_sources_result(self, query: str) -> dict[str, Any]:
        """Build a deterministic answer enumerating ALL distinct sources.

        Routes around vector search on purpose: semantic search is bounded by
        ``top_k`` and relevance, so it would silently drop sources as the
        corpus grows. A native ``distinct`` aggregation returns every unique
        source regardless of database size.

        Returns a result dict whose "answer" is a numbered enumeration of the
        source files (no LLM call, no embedding generation).
        """
        try:
            source_files: list[str] = list(self._searcher.list_source_files())
        except Exception as e:
            logger.warning("list_source_files failed: %s: %s", type(e).__name__, e)
            return {
                "answer": "I couldn't list the stored sources right now. Please try again.",
                "query": query,
                "list_sources": True,
            }

        source_files = sorted({s for s in source_files if s}, key=str.lower)

        if not source_files:
            return {
                "answer": (
                    "I don't have any documents stored yet. "
                    "Ingest some with `secondbrain ingest <path>` first."
                ),
                "query": query,
                "list_sources": True,
            }

        plural = "source" if len(source_files) == 1 else "sources"
        lines = [f"I found {len(source_files)} unique {plural}:"]
        lines.extend(f"  {i}. {s}" for i, s in enumerate(source_files, 1))
        return {
            "answer": "\n".join(lines),
            "query": query,
            "list_sources": True,
        }

    def _rewrite_query_with_history(
        self,
        query: str,
        session: ConversationSession,
    ) -> str:
        """Rewrite query using conversation history.

        Args:
            query: Current user query.
            session: ConversationSession with history.

        Returns:
            Rewritten query or original if rewriter not available.

        Example:
            >>> session = ConversationSession.create("test", storage)
            >>> pipeline._rewrite_query_with_history("What about it?", session)
            "What about it?"  # No rewriter, returns original
        """
        if self._rewriter is None:
            return query

        history = session.get_history(limit=self._context_window)
        if not history:
            return query

        try:
            return self._rewriter.rewrite_query(query, history)
        except Exception as e:
            logger.warning("Query rewriting failed: %s: %s", type(e).__name__, e)
            return query
