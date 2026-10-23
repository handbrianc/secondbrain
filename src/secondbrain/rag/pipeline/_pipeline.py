"""RAG pipeline core: construction and the iterative query engine.

``RAGPipeline`` composes the cohesive helper mixins (formatting,
structure, fallback, routing, orchestration) and owns construction plus
the chapter-aware ``_iterative_query`` engine. Split out of the former
2450-line ``__init__`` so the package ``__init__`` stays a thin facade.
"""

from __future__ import annotations

import logging
import re
import statistics
import time
from typing import Any, cast

from secondbrain.config import config
from secondbrain.conversation import QueryRewriter
from secondbrain.document.fast_text import footer_page_offset
from secondbrain.document.scoped_retriever import ScopedRetriever
from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.intent_parser import QueryIntent, StructuralIntentParser
from secondbrain.rag.interfaces import LocalLLMProvider, StreamingCallback
from secondbrain.rag.pipeline._constants import (
    filter_chapters_by_target,
    strip_document_filenames,
)
from secondbrain.rag.pipeline._fallback_mixin import _FallbackMixin
from secondbrain.rag.pipeline._formatting_mixin import _FormattingMixin
from secondbrain.rag.pipeline._orchestration import _OrchestrationMixin
from secondbrain.rag.pipeline._routing_mixin import _RoutingMixin
from secondbrain.rag.pipeline._structure_mixin import _StructureMixin
from secondbrain.rag.security_filter import SecurityFilter
from secondbrain.search import Searcher
from secondbrain.utils.perf_monitor import metrics
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)

# An explicit structural target in the query ("chapter 5", "section 2.3",
# "part 1") keeps the legacy chapter path even for anthology-shaped
# documents: per-part routing answers target-less broad-coverage summaries
# only (add-anthology-aware-chapter-summarization; targeted drill-down inside
# an anthology is a follow-up, and targeted queries stay protected by the
# chapter-range agreement gate).
_QUERY_TARGET_RE = re.compile(
    r"\b(?:chapter|section|part)\s+\d+\b|\b\d+\.\d+\b",
    re.IGNORECASE,
)


class RAGPipeline(
    _FormattingMixin,
    _StructureMixin,
    _FallbackMixin,
    _RoutingMixin,
    _OrchestrationMixin,
):
    """Orchestrates retrieval and generation for conversational RAG.

    Inherits cohesive helper-method mixins; public entry points live on
    ``_OrchestrationMixin`` (``_orchestration.py``).
    """

    def __init__(
        self,
        searcher: Searcher,
        llm_provider: LocalLLMProvider,
        rewriter: QueryRewriter | None = None,
        top_k: int | None = None,
        context_window: int = 5,
        on_chunk: StreamingCallback | None = None,
    ) -> None:
        """Initialize RAG pipeline with components.

        Args:
            searcher: Searcher instance for semantic search.
            llm_provider: LocalLLMProvider for generation.
            rewriter: QueryRewriter for context-aware queries (optional).
            top_k: Number of chunks to retrieve (default: 5).
            context_window: Messages to keep in context (default: 5 per spec).

        Example:
            >>> searcher = Searcher()
            >>> # llm_provider = get_llm_provider()  # Get your configured provider
            >>> pipeline = RAGPipeline(searcher, llm_provider, top_k=10)
        """
        self._searcher = searcher
        self._scoper = ScopedRetriever(inner=self._searcher)  # type: ignore[arg-type]
        self._llm_provider = llm_provider
        self._rewriter = rewriter
        self._top_k = top_k if top_k is not None else config().default_top_k
        self._context_window = context_window
        self._config = config()
        self._intent_parser = StructuralIntentParser(self._config)
        self._security_filter = SecurityFilter()
        self._on_chunk = on_chunk
        # Lazily-initialized DocumentRouter for document-scoped retrieval.
        # Created on first use so that the pipeline can be constructed without
        # a running vector store connection (e.g. during CLI help / --version).
        self._document_router: DocumentRouter | None = None

    def _iterative_query(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        """Handle broad-coverage queries via iterative structural traversal.

        Instead of one-shot top-k similarity, walks document structure
        by probing TOC/section elements and querying per-section ranges,
        then deduplicates across iterations.

        Args:
            query: Original user query.
            top_k: Number of chunks to aim for overall.
            show_sources: Whether to include sources in response.

        Returns:
            dict with 'answer', 'query', 'sources' (if show_sources).
        """
        # 1. Probe document structure for TOC/chapter chunks via chunk_role
        structure_chunks = self._probe_document_structure(
            top_k=400,
            source_filter=source_filter,
        )
        if not structure_chunks:
            # Fall back to generic one-shot if no structure found
            return self._generic_one_shot(
                query,
                top_k,
                show_sources,
                source_filter=source_filter,
            )

        intent_decision = self._intent_parser.parse(query)

        # When enumerating a single chapter, boost top_k so the bucket
        # collection captures enough breadth across the page range
        # instead of saturating on the first few pages.
        if (
            intent_decision.intent == QueryIntent.CHAPTER_ENUMERATE
            and intent_decision.target is not None
        ):
            top_k = max(top_k, 40)

        # 2a. Branch: chapter-enumeration query — per-chapter keyword search
        # If the user asked for a specific section (e.g. "section 11.33"),
        # extract the chapter number ("11") and enumerate that chapter.
        enum_target = intent_decision.target
        raw_section_target: str | None = None
        if enum_target is None and intent_decision.intent in (
            QueryIntent.BROAD_COVERAGE,
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
        ):
            # BROAD_COVERAGE only extracts "chapter N" targets, not
            # "section 11.33".  Check the raw query for a section number —
            # but strip filename mentions first, so a version suffix such as
            # "pve-admin-guide-9.1.pdf" cannot masquerade as a "section 9.1"
            # target and silently narrow a whole-book request to chapter 9.
            query_no_files_ = strip_document_filenames(query)
            sec_m = re.search(r"(\d+(?:\.\d+)+)", query_no_files_)
            if sec_m:
                enum_target = sec_m.group(1)
                raw_section_target = enum_target  # preserve before truncation
        if enum_target and "." in enum_target:
            enum_target = enum_target.split(".")[0]
        # Also catch broad-coverage queries with section numbers like
        # "summarize section 11.33" — route through chapter enumeration
        # for precise page-range retrieval instead of the generic search.
        has_section_target = enum_target is not None and intent_decision.intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
            QueryIntent.SECTION_ENUMERATE,
        )
        if has_section_target or intent_decision.intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
        ):
            chapters_to_cover, good_title_nums, appendix_entries = (
                self._derive_chapter_numbers(structure_chunks)
            )
            # Keep the full (un-filtered) chapter set for boundary anchoring: a
            # target chapter's end page is bounded by the NEXT chapter's start, so
            # the next chapter's start must also be title-anchored (not left to
            # the noisy section-number scan that sets spurious early boundaries).
            full_chapters = list(chapters_to_cover)

            # Scope to specific target chapter when one is specified (e.g. "chapter 11")
            chapters_to_cover, good_title_nums = filter_chapters_by_target(
                chapters_to_cover,
                good_title_nums,
                enum_target,
            )
            if enum_target is not None:
                appendix_entries = []

            if chapters_to_cover:
                storage = self._searcher.storage
                try:
                    # Use explicit source_filter if provided (from DocumentRouter),
                    # otherwise pick the source with the most body chunks.
                    if source_filter:
                        src = source_filter
                    else:
                        sources_set = {entry[1] for entry in chapters_to_cover}
                        src = max(
                            (s for s in sources_set),
                            key=lambda s: storage.count_chunks(s, "body"),
                        )
                except Exception:
                    logger.warning(
                        "Storage unavailable for chapter enumeration, "
                        "falling back to generic search",
                        exc_info=True,
                    )
                    return self._generic_one_shot(
                        query, top_k, show_sources, source_filter=source_filter
                    )

                # Pre-populate chapter_first_pg from reliable CHAPTER_N_RE titles
                # (e.g. "Chapter 5 Importing...") so SEC_HEADER_RE doesn't overwrite
                # them with section-number false matches (e.g. "5.1 Running a VM"
                # which is actually a section of a different chapter).
                # BARE_CHAPTER_RE titles (e.g. "5 Working with VMs") are NOT included
                # here — they're less reliable and may conflict with other chapters.
                chapter_first_pg: dict[int, int] = {}
                # Front-matter "about this book" pages describe every chapter
                # in prose ("Chapter 9 , AI Cloud Platforms for IoT , introduces
                # ...").  In books extracted without heading/toc_entry chunks
                # these body-role sentences are the only "Chapter N" matches,
                # and anchoring on them pinned chapters to the front-matter page
                # their description sits on — collapsing the chapter's page
                # range to that single page and starving its content bucket.
                # Collect (chapter -> description page) once; every scan below
                # refuses to anchor a chapter on its description page.
                desc_pages = self._front_matter_desc_pages(structure_chunks)
                # License/colophon pages (GFDL/GNU) carry numbered all-caps
                # headings that mimic chapter openers — no scan may anchor on them.
                boiler_pages_ = self._boilerplate_pages(structure_chunks)
                # Body chunks grouped by page feed two consumers: the
                # section-heading evidence tier below (its ±1 pin adjustment
                # and its ToC-like page classification) and the ToC-like
                # page set the digit scans skip.  Fetched once here instead
                # of after the anchor pass so the evidence tier — which must
                # run FIRST — can use it.
                dot_leader_ = re.compile(r"\.{2,}")
                body_all_ = cast(
                    list[dict[str, Any]],
                    list(
                        storage.get_body_chunks(
                            src,
                            limit=None,
                        )
                    ),
                )
                body_by_page_: dict[int, list[dict[str, Any]]] = {}
                for body_c_ in body_all_:
                    body_by_page_.setdefault(
                        int(body_c_.get("page_number") or 0), []
                    ).append(body_c_)
                # Dot-leader-dense body pages are printed ToCs: the
                # section-number and loose-digit scans below must never pin
                # from them (defense in depth — the evidence tier performs
                # the same classification with the page's heading chunks
                # included).  Classified from body chunks only, matching
                # what these scans see.
                toc_like_pages_ = {
                    pg_
                    for pg_, pg_chunks_ in body_by_page_.items()
                    if self._dot_leader_page(pg_chunks_)
                }
                # Labeled-docling books (element_type migration): docling drops
                # the "Chapter N" banner, strips section numbers from headings,
                # and leaves ToC/covers pages as body chunks — the scans below
                # then fail or misfire, and Phase 2's loose digit scan pins
                # chapters to front-matter pages (empty/wrong chapter buckets).
                # The chapter titles themselves ARE heading chunks on the real
                # opening pages, so anchor on them FIRST — before the body-title
                # scan below — and let that scan only fill chapters the anchors
                # left unset (a heading anchor can never be overridden by a
                # spurious body-page match).  Every later scan still skips
                # chapters already pre-populated here.
                try:
                    heading_all_ = list(
                        cast(
                            list[dict[str, Any]],
                            storage.find_structural_chunks(
                                chunk_roles=["heading"], source_prefix=src
                            ),
                        )
                    )
                except Exception:
                    logger.warning(
                        "Heading-chunk fetch failed for %s; skipping "
                        "heading-title anchoring",
                        src,
                        exc_info=True,
                    )
                    heading_all_ = []
                # Anthology routing (add-anthology-aware-chapter-
                # summarization): a compilation of sub-reports that each
                # restart their own section numbering cannot be represented
                # by the single monotone chapter map the machinery below
                # derives — every stage misfires on it (see the change's
                # design.md forensic record).  When the multi-signal detector
                # claims this document and the query carries no explicit
                # structural target, enumerate the document PER PART and
                # return before any roster/pinning work; a targeted query
                # keeps the legacy path and its gate protection.  Detection
                # that fails the per-part scale check continues to the legacy
                # path silently (debug-logged inside the enrichment).
                if _QUERY_TARGET_RE.search(query) is None:
                    detected_parts_ = self._detect_anthology_parts(heading_all_, src)
                    if detected_parts_ is not None:
                        total_pages_ = max(body_by_page_, default=0)
                        anthology_parts_ = self._enrich_anthology_parts(
                            detected_parts_,
                            body_by_page_,
                            heading_all_,
                            total_pages_,
                        )
                        if anthology_parts_ is not None:
                            with trace_operation("rag_generation_iterative") as span:
                                if span:
                                    span.set_attribute("rag.iterative_mode", True)
                                    span.set_attribute("rag.enumeration_mode", True)
                                    span.set_attribute(
                                        "rag.anthology_parts",
                                        len(anthology_parts_),
                                    )
                                answer = self._generate_anthology_summary(
                                    anthology_parts_
                                )
                            return {"answer": answer, "query": query}
                        logger.debug(
                            "Anthology detection fired for %s but the "
                            "per-part scale check failed; continuing with "
                            "the legacy chapter path",
                            src,
                        )
                # Tier 0 — section-heading evidence pins.  Each chapter's
                # first numbered section heading (``N.1``) is the strongest
                # start-page signal: it survives even when the banner/title
                # heading was dropped, and it sits on (or one page beside)
                # the true opener.  These pins are PROVISIONAL (±1 page):
                # exact ToC evidence — listing rows or recovered run-on rows
                # resolved through a validated printed→stored offset — may
                # replace them; the fuzzy anchors and every later digit scan
                # keep their fill-only semantics and never override.
                provisional_pins_: set[int] = set()
                evidence_pin_pg_: dict[int, int] = {}
                # RAW first-section evidence, kept unfiltered for the
                # chapter-range agreement gate below: evidence_pin_pg_ only
                # keeps pins that fit the monotone window, and on an
                # anthology the window is exactly the wrong model — the
                # cross-namespace pins (part I.1's §1 heading pinning global
                # ch1, part I.2's §1 pinning global ch2, …) collide and the
                # filter collapses them to a single survivor, leaving the
                # gate nothing to compare.  The calibrated metric
                # (baselines.json "gate_divergence", design.md §3) is computed
                # from this raw _section_heading_pins output — 18/18 and
                # 19/19 for the corpus books, 2/8 for the compilation.
                # Legacy behavior is untouched: only the gate reads the raw
                # map; evidence_pin_pg_ keeps its window-filtered semantics
                # for the ToC-override/runon-offset logic below.
                evidence_pins_all_: dict[int, int] = self._section_heading_pins(
                    full_chapters,
                    src,
                    heading_all_,
                    boiler_pages=boiler_pages_,
                    body_chunks_by_page=body_by_page_,
                )
                for ev_ch_, ev_pg_ in sorted(evidence_pins_all_.items()):
                    if not self._pin_fits_window(chapter_first_pg, ev_ch_, ev_pg_):
                        continue
                    chapter_first_pg[ev_ch_] = ev_pg_
                    provisional_pins_.add(ev_ch_)
                    evidence_pin_pg_[ev_ch_] = ev_pg_
                    logger.debug(
                        "Provisional evidence pin for chapter %d at page %d "
                        "via its N.1 section heading",
                        ev_ch_,
                        ev_pg_,
                    )
                anchor_titles_: dict[int, str] = {}
                for an_ch, an_pg in self._heading_title_anchors(
                    full_chapters,
                    src,
                    heading_all_,
                    blocked_pages=desc_pages,
                    boiler_pages=boiler_pages_,
                    titles_out=anchor_titles_,
                ).items():
                    chapter_first_pg.setdefault(an_ch, an_pg)
                # Title-anchored detection: the numbered chapter-title heading
                # (e.g. "13 Troubleshooting", "12 Customizing Oracle VirtualBox") is
                # the single most reliable chapter-start signal.  Section-number
                # scanning below (SEC_HEADER_RE / BARE_CHAPTER_RE) mistakes TOC
                # dot-leader entries and in-body cross-references (e.g. "see 15.16")
                # for chapter starts, pinning chapters to the wrong page — especially
                # for books whose chapters are numbered without the word "Chapter"
                # (so they are invisible to CHAPTER_N_RE).  Find each chapter's
                # title heading on a body page (skipping TOC dot-leader lines) and
                # pre-populate, so the noisy scans cannot override it.
                for tn_ in full_chapters:
                    tn, ts_, tt_ = tn_
                    # Detected titles often carry a printed-page artifact,
                    # trailing ("The pandas I/O System 79") or embedded before
                    # the next ToC line's text ("Title 147 How ma"); strip
                    # both so the anchor matches the real heading.
                    tt_ = re.sub(r"\s+\d{1,4}\s*$", "", tt_)
                    tt_ = re.split(r"\s+\d{1,4}\s+", tt_)[0].rstrip(" .:;-")
                    if ts_ != src or not tt_ or len(tt_) < 4:
                        continue
                    # Join title fragments with \s* instead of \s+: the docling-
                    # parse space regression glues words together, so the spaced
                    # body opener ("5 Cluster Manager") must match the glued
                    # roster title ("ClusterManager") AND the glued body ToC row
                    # ("5 ClusterManager 58") must match the spaced roster
                    # title — zero-width \s* covers both directions.  Fully
                    # glued CamelCase tokens carry no space to relax, so they
                    # are split at the lower→upper boundaries ("ClusterManager"
                    # → Cluster/Manager) and the fragments joined with \s*;
                    # spaced tokens pass through unsplit.
                    title_chars_ = re.sub(r"\s+", "", tt_)
                    title_pattern_ = r"\s*".join(
                        re.escape(char_) for char_ in title_chars_
                    )
                    anchor_ = re.compile(
                        rf"(?:^|\n)\s*{tn}\.?\s*" + rf"(?P<title>{title_pattern_})",
                        re.IGNORECASE,
                    )
                    for bc_ in body_all_:
                        if int(bc_.get("page_number") or 0) in boiler_pages_:
                            continue
                        btext_ = bc_.get("chunk_text", "")
                        bm_ = anchor_.search(btext_)
                        if not bm_:
                            continue
                        ble_ = btext_.find("\n", bm_.end())
                        brest_ = btext_[bm_.end() : ble_ if ble_ != -1 else len(btext_)]
                        # Flattened-ToC lines read "Title 43 Next Entry …": after
                        # the title comes a printed page reference, then the next
                        # entry's text.  A real opener's line ends with prose, so
                        # any remainder starting with a number is a ToC artifact.
                        brest_lead_ = brest_.strip()
                        if dot_leader_.search(brest_) or (
                            brest_lead_ and brest_lead_[0].isdigit()
                        ):
                            continue
                        # Cross-reference prose ("... Working with VMs on
                        # page 89") names a chapter from a foreign page —
                        # mirror the section scan's on-page refusal so the
                        # body-title pass cannot anchor there either.
                        if re.search(
                            r"\bon\s+page\s+\d+",
                            btext_[bm_.end() : bm_.end() + 60],
                            re.IGNORECASE,
                        ):
                            continue
                        if tn not in chapter_first_pg:
                            chapter_first_pg[tn] = int(bc_.get("page_number") or 0)
                            anchor_titles_[tn] = re.sub(
                                r"\s+", " ", bm_.group("title")
                            ).strip()
                        break
                # Monotonic-window validation of every pin collected by the
                # heading-anchor and body-title passes: chapter opening pages
                # must strictly increase with chapter number (same open-interval
                # contract as _pin_fits_window).  Conflicting pins are resolved
                # in one maximal-monotone pass (_select_monotone_pins): the
                # largest consistent subset survives.  A single false pin
                # therefore drops itself instead of cascade-rejecting the real
                # pins above it (the previous highest-numbered-violator loop
                # let a license caption kill chapters 7-20 one scan at a
                # time).  Dropped chapters fall to the later scan tiers and
                # the ToC reconciliation.
                chapter_first_pg = self._select_monotone_pins(chapter_first_pg)

                # Spaced-title backfill.  When the docling-parse space
                # regression glued the ToC row, the roster title reads
                # "GraphicalUser Interface" while the heading anchor matched
                # the intact opener spelling ("Graphical User Interface") —
                # the anchors only match because the comparison squashes
                # whitespace.  Replacing the glued roster title with the
                # opener's spaced spelling repairs the display
                # ("Chapter 4 — Graphical User Interface") without touching
                # any differently-worded title, so it is gated on the two
                # forms being the same text modulo whitespace.  Surviving
                # chapters only: a pin the monotone pass dropped is gone for
                # good and must not gain a roster title as a side effect.
                for ch_ in chapter_first_pg:
                    spaced_ = anchor_titles_.get(ch_)
                    if not spaced_:
                        continue
                    spaced_title_ = spaced_.strip()
                    ct_idx_ = next(
                        (
                            i
                            for i, ct in enumerate(chapters_to_cover)
                            if ct[0] == ch_ and ct[1] == src
                        ),
                        None,
                    )
                    if ct_idx_ is None:
                        continue
                    old_ = chapters_to_cover[ct_idx_][2]
                    spaced_norm_ = re.sub(r"\s+", " ", spaced_title_).strip()
                    old_norm_ = re.sub(r"\s+", " ", old_).strip()
                    if re.sub(r"\s+", "", spaced_norm_) != re.sub(
                        r"\s+", "", old_norm_
                    ):
                        spaced_title_ = re.sub(
                            rf"^(?:chapter\s*)?{ch_}(?:\.\d+)?[\s:.\-\u2013\u2014]*",
                            "",
                            spaced_,
                            flags=re.IGNORECASE,
                        ).strip()
                        spaced_norm_ = re.sub(r"\s+", " ", spaced_title_).strip()
                    if re.sub(r"\s+", "", spaced_norm_) != re.sub(
                        r"\s+", "", old_norm_
                    ) or len(spaced_norm_) <= len(old_norm_):
                        # Same safeguard as every other repair path: only the
                        # glued-vs-spaced spellings of ONE title may swap, and
                        # only toward the more-spaced form.
                        continue
                    chapters_to_cover[ct_idx_] = (ch_, src, spaced_title_)
                    good_title_nums.add(ch_)
                    logger.debug(
                        "Backfilled spaced chapter title for %d from its "
                        "opener heading",
                        ch_,
                    )

                # Front-matter ToC-listing reconciliation.  When the printed
                # ToC parses with enough roster coverage, chapters the heading
                # and body scans left unpinned are pinned at their printed ToC
                # page plus a median print-to-scan offset, and unpinned roster
                # chapters the parse neither lists nor mentions are phantoms
                # and die.  A row mentioned without a parseable page is
                # ambiguous and keeps its chapter; pins confirmed by the
                # earlier passes are never overridden and never killed.
                toc_killed_: set[int] = set()
                toc_roster_ = {ct[0] for ct in chapters_to_cover if ct[1] == src}
                # Multi-source probes return every book's front matter;
                # without this scope another book's ToC rows would inflate
                # the coverage gate and feed phantom-kill evidence for the
                # selected book.
                src_chunks_ = [
                    c for c in structure_chunks if c.get("source_file") == src
                ]
                toc_listings_, toc_mentions_ = self._toc_listing_pages(
                    src_chunks_, desc_pages, toc_roster_
                )
                if toc_listings_:
                    for toc_ch_ in sorted(toc_roster_):
                        if toc_ch_ in chapter_first_pg:
                            continue
                        if toc_ch_ in toc_listings_ or toc_ch_ in toc_mentions_:
                            if toc_ch_ not in toc_listings_:
                                logger.debug(
                                    "Kept chapter %d for %s: ambiguous ToC "
                                    "mention without a parseable page",
                                    toc_ch_,
                                    src,
                                )
                            continue
                        toc_killed_.add(toc_ch_)
                        chapters_to_cover = [
                            ct
                            for ct in chapters_to_cover
                            if ct[0] != toc_ch_ or ct[1] != src
                        ]
                        good_title_nums.discard(toc_ch_)
                        logger.debug(
                            "Dropped phantom roster chapter %d for %s: absent "
                            "from the front-matter ToC parse",
                            toc_ch_,
                            src,
                        )
                    toc_offsets_ = [
                        chapter_first_pg[anch_ch_] - toc_listings_[anch_ch_][1]
                        for anch_ch_ in chapter_first_pg
                        if anch_ch_ in toc_listings_
                    ]
                    if toc_offsets_:
                        toc_offset_ = int(statistics.median(toc_offsets_))
                        logger.debug(
                            "ToC listing offset spread for %s: min=%d max=%d "
                            "median=%d over %d anchored chapters",
                            src,
                            min(toc_offsets_),
                            max(toc_offsets_),
                            toc_offset_,
                            len(toc_offsets_),
                        )
                        for toc_ch_, (toc_title_, toc_printed_) in sorted(
                            toc_listings_.items()
                        ):
                            # Exact printed-page evidence replaces a
                            # provisional section-heading pin (±1); pins from
                            # anchors/scans stay untouchable.
                            if toc_ch_ in chapter_first_pg and (
                                toc_ch_ not in provisional_pins_
                            ):
                                continue
                            if toc_ch_ not in good_title_nums:
                                continue
                            toc_derived_ = toc_printed_ + toc_offset_
                            # Front matter never anchors: a small or negative
                            # median offset must not park a pin below the book
                            # body, violating the floor every other scan
                            # enforces.
                            if toc_derived_ < 10:
                                logger.debug(
                                    "Rejected chapter %d ToC pin @%d: below "
                                    "the front-matter floor",
                                    toc_ch_,
                                    toc_derived_,
                                )
                                continue
                            toc_lo_pg_ = max(
                                (
                                    pg_
                                    for ch_, pg_ in chapter_first_pg.items()
                                    if ch_ < toc_ch_
                                ),
                                default=None,
                            )
                            toc_hi_pg_ = min(
                                (
                                    pg_
                                    for ch_, pg_ in chapter_first_pg.items()
                                    if ch_ > toc_ch_
                                ),
                                default=None,
                            )
                            if (
                                toc_lo_pg_ is not None and toc_lo_pg_ >= toc_derived_
                            ) or (
                                toc_hi_pg_ is not None and toc_derived_ >= toc_hi_pg_
                            ):
                                logger.debug(
                                    "Rejected chapter %d ToC pin @%d violating "
                                    "monotonic window (lower=%s, upper=%s)",
                                    toc_ch_,
                                    toc_derived_,
                                    toc_lo_pg_,
                                    toc_hi_pg_,
                                )
                                continue
                            chapter_first_pg[toc_ch_] = toc_derived_
                            logger.debug(
                                "Pinned chapter %d (%s) at page %d via "
                                "front-matter ToC listing (printed %d + offset %d)",
                                toc_ch_,
                                toc_title_,
                                toc_derived_,
                                toc_printed_,
                                toc_offset_,
                            )

                # Run-on ToC row recovery.  Flattened ToCs merge consecutive
                # rows into one body chunk ("... 134 Proxmox Cluster File
                # System (pmxcfs) 136 6.1 POSIX ..."), so chapters whose row
                # only exists mid-run-on (PVE ch6 — its opener banner carries
                # no title) have neither a roster title nor a pin.  Split the
                # run-ons from early-page chunks into per-row shapes the
                # listing parser can read, then store recovered (title,
                # printed page) pairs for the title-less roster chapters.
                # The trigger also covers TITLED but still-unpinned chapters:
                # the docling space regression glues a roster title without
                # deleting it (PVE ch6 "QEMU/KVM Virtual Machines" came
                # through glued), so an empty-title probe misses the very
                # chapter the recovery exists for — and chapters carrying a
                # provisional evidence pin, whose exact ToC row can refine
                # the ±1 pin to the printed opener page.
                runon_rows_: dict[int, tuple[str, int]] = {}
                titleless_now_ = {
                    ct[0] for ct in chapters_to_cover if ct[1] == src and not ct[2]
                }
                unpinned_roster_ = {
                    ct[0]
                    for ct in chapters_to_cover
                    if ct[1] == src
                    and ct[0] in good_title_nums
                    and ct[0] not in chapter_first_pg
                }
                if titleless_now_ or unpinned_roster_ or provisional_pins_:
                    runon_rows_ = self._recovered_runon_toc_rows(structure_chunks, src)
                if runon_rows_:
                    # Fill roster titles first (display correctness), then
                    # pin through the footer offset when the ToC-printed
                    # page and the book's footer index agree.  A chapter
                    # whose glued roster title squash-equals the recovered
                    # row title gets the row's SPACED spelling too — same
                    # rule as the opener-heading backfill above.
                    for ch, (_title, _printed) in sorted(runon_rows_.items()):
                        ct_idx_ = next(
                            (
                                i
                                for i, ct in enumerate(chapters_to_cover)
                                if ct[0] == ch and ct[1] == src
                            ),
                            None,
                        )
                        if ct_idx_ is None:
                            continue
                        old_title_ = chapters_to_cover[ct_idx_][2]
                        new_title_ = runon_rows_[ch][0]
                        replace_ = not old_title_ or (
                            # Same replace rule as the opener-heading
                            # backfill: only a glued-vs-spaced spelling of
                            # the SAME title may swap, and only toward the
                            # more-whitespace (spaced) form.
                            re.sub(r"\s+", "", new_title_)
                            == re.sub(r"\s+", "", old_title_)
                            and len(re.sub(r"\s+", " ", new_title_))
                            > len(re.sub(r"\s+", " ", old_title_))
                        )
                        if replace_:
                            chapters_to_cover[ct_idx_] = (ch, src, new_title_)
                            good_title_nums.add(ch)
                    footer_offset_ = None
                    try:
                        # Nav footer chunks carry chunk_role "navigation" —
                        # get_body_chunks() returns only chunk_role "body", so
                        # on real storage this fetch yielded an empty map and
                        # footer_page_offset() returned None (the run-on pin
                        # silently no-oped for every chapter; the unit harness
                        # hid it because its stub get_body_chunks ignores the
                        # role).  Probe the body stream first (the unit double
                        # serves nav chunks there and has no role filter), and
                        # fall back to find_structural_chunks — which ORs
                        # element_type/chunk_role and matches real nav chunks —
                        # when the body stream carries none.
                        nav_texts_: dict[int, str] = {}
                        for nav_c in storage.get_body_chunks(src, limit=None):
                            if nav_c.get("chunk_role") == "navigation" or (
                                nav_c.get("element_type") == "navigation"
                            ):
                                nav_texts_[int(nav_c.get("page_number") or 0)] = (
                                    nav_c.get("chunk_text") or ""
                                )
                        if not nav_texts_:
                            for nav_c in storage.find_structural_chunks(
                                chunk_roles=["navigation"], source_prefix=src
                            ):
                                if nav_c.get("source_file") != src:
                                    continue
                                nav_texts_[int(nav_c.get("page_number") or 0)] = (
                                    nav_c.get("chunk_text") or ""
                                )
                        footer_offset_ = footer_page_offset(nav_texts_)
                    except Exception:
                        footer_offset_ = None
                    # Evidence-validated offset fallback (footer-less books):
                    # when the nav footers cannot vote, recovered ToC rows
                    # still carry exact printed pages and the section-heading
                    # evidence pins locate the same chapters.  The offset is
                    # the strict-majority vote of (pin - printed) over rows
                    # whose evidence pin still stands — using the pin page,
                    # not the raw heading page, so the ±1 rule folds into
                    # the offset.  No strict majority → no pins from this
                    # fallback.
                    runon_offset_ = footer_offset_
                    if runon_offset_ is None:
                        standing_ev_ = {
                            ev_ch_: ev_pg_
                            for ev_ch_, ev_pg_ in evidence_pin_pg_.items()
                            if chapter_first_pg.get(ev_ch_) == ev_pg_
                        }
                        offset_votes_: dict[int, int] = {}
                        for v_ch_, (_v_title, v_printed_) in runon_rows_.items():
                            if v_ch_ in standing_ev_:
                                v_off_ = standing_ev_[v_ch_] - v_printed_
                                offset_votes_[v_off_] = offset_votes_.get(v_off_, 0) + 1
                        if offset_votes_:
                            top_votes_ = max(offset_votes_.values())
                            leaders_ = [
                                v_off_
                                for v_off_, v_cnt_ in offset_votes_.items()
                                if v_cnt_ == top_votes_
                            ]
                            # Strict majority: at least two agreeing rows and
                            # no other offset tying the leader.
                            if top_votes_ >= 2 and len(leaders_) == 1:
                                runon_offset_ = leaders_[0]
                                logger.debug(
                                    "Run-on ToC offset fallback for %s: %d "
                                    "(%d agreeing evidence rows)",
                                    src,
                                    runon_offset_,
                                    top_votes_,
                                )
                    for ch, (title, printed) in sorted(runon_rows_.items()):
                        # Exact ToC evidence may replace a provisional
                        # section-heading pin; anchor/scan pins keep
                        # fill-only semantics.
                        if ch in chapter_first_pg and ch not in provisional_pins_:
                            continue
                        if ch not in (
                            titleless_now_ | unpinned_roster_ | provisional_pins_
                        ):
                            continue
                        if runon_offset_ is None:
                            continue
                        physical = printed + runon_offset_
                        if physical < 10:
                            continue
                        if not self._pin_fits_window(chapter_first_pg, ch, physical):
                            continue
                        chapter_first_pg[ch] = physical
                        logger.debug(
                            "Pinned chapter %d (%s) at page %d via run-on "
                            "ToC row (printed %d + offset %d)",
                            ch,
                            title,
                            physical,
                            printed,
                            runon_offset_,
                        )
                ch_n = re.compile(
                    r"(?:Chapter\s+(\d+)\s*[:\-]?\s*|(?:Module|Lesson)\s+(\d+)"
                    r"\s*[:\-]\s*)(.{2,60})",
                    re.IGNORECASE,
                )
                # Slide decks are extracted without heading/toc roles — every
                # slide is real content, so an early "Module 1"/"Module 2"
                # heading (page <10) is genuine, not a TOC entry.  Keep the
                # TOC-page guard for manuals, which do carry heading/toc roles.
                is_deck = not any(
                    c.get("chunk_role") in ("heading", "toc_entry")
                    for c in structure_chunks
                )
                for sc in structure_chunks:
                    txt = sc.get("chunk_text", "")
                    pg = sc.get("page_number", 0)
                    role = sc.get("chunk_role", "")
                    # Reject TOC page numbers (typically < 10) — a chapter_n_re
                    # match on page 3 is almost certainly a TOC entry, not the
                    # actual chapter start page. Without this guard, Phase 1's
                    # sec_header_re body-chunk scan would find the wrong start.
                    if pg < 10 and not is_deck:
                        continue
                    # TOC / front-structure chunks list every chapter on one
                    # page (dot-leader "Chapter N" captions) and are never the
                    # real opening of a chapter.  Some books carry no heading /
                    # toc_entry roles (front matter is tagged "caption" or
                    # "navigation"), so is_deck becomes True and the pg<10 guard
                    # above is skipped — rejecting these roles keeps that
                    # protection.
                    if role in ("toc_entry", "caption", "navigation"):
                        continue
                    if pg in boiler_pages_:
                        continue
                    for nm in ch_n.finditer(txt):
                        ch = int(nm.group(1) or nm.group(2))
                        if ch in good_title_nums and ch not in chapter_first_pg:
                            # "Chapter N," (comma right after the number) is a
                            # preface / cross-reference summary sentence
                            # (e.g. "Chapter 4, The pandas I/O System, shows …"),
                            # NOT a chapter-opening heading.  Matching those pins
                            # every chapter to a front-matter page and starves the
                            # real chapter of its page range.  Real headings use a
                            # colon, period, or plain space after the number.
                            if re.match(r"Chapter\s+\d+,", nm.group(0), re.IGNORECASE):
                                continue
                            if desc_pages.get(ch) == pg:
                                # The description sentence sits on a front-
                                # matter page and never marks the real chapter
                                # start (see desc_pages above).
                                continue
                            if not self._pin_fits_window(chapter_first_pg, ch, pg):
                                continue
                            chapter_first_pg[ch] = pg

                # Scan body chunks for magazine-style chapter openings (bare
                # number + title, e.g. ML4T).  These are body-role, invisible to
                # the heading/TOC structure probe, so without them a chapter that
                # never gets a reliable start page is unbounded and the next
                # chapter's content leaks into its bucket.
                for open_n, open_pg in self._detect_chapter_openings(body_all_).items():
                    if (
                        open_n not in chapter_first_pg
                        and open_n not in toc_killed_
                        and open_pg not in boiler_pages_
                        and self._pin_fits_window(chapter_first_pg, open_n, open_pg)
                    ):
                        chapter_first_pg[open_n] = open_pg

                # Phase 1: find chapter start pages from body chunk subsection headers like "1.1 " or "11.1.1 "
                # Use \b (word boundary) + search() instead of ^ + match() because docling
                # often embeds section numbers in the middle of paragraph text rather than
                # at the start of a chunk (e.g. "... features. 11.1 CPU Hot-Plugging ...").
                # NOTE: chapters already in chapter_first_pg (from ch_n above) are
                # skipped — their pages are more reliable.
                sec_header_re = re.compile(r"\b(\d+)\.\d+(?:\.\d+)?\s")
                # Parallel scan for letter-prefixed section numbers (e.g. "A.1", "B.2.3")
                # to detect appendix labels from actual document body content.  This is the
                # most universal approach — works for any document regardless of TOC format.
                appendix_sec_re = re.compile(r"\b([A-Za-z])\.\d+\s")
                appendix_labels_found: set[str] = set()
                for chunk in storage.get_body_chunks(src, limit=None):
                    txt = chunk.get("chunk_text", "")[:150]
                    page = chunk.get("page_number") or 0
                    if page in boiler_pages_:
                        continue
                    if page in toc_like_pages_:
                        # Dot-leader ToC pages list every chapter's sections;
                        # their "N.1" shapes are references, never openers.
                        continue

                    # Detect appendix labels from body section numbering
                    am = appendix_sec_re.search(txt)
                    if am:
                        appendix_labels_found.add(am.group(1).upper())

                    m = sec_header_re.search(txt)
                    if m:
                        ch = int(m.group(1))
                        if 1 <= ch <= 30 and ch not in chapter_first_pg:
                            if ch in toc_killed_:
                                continue
                            if desc_pages.get(ch) == page:
                                continue
                            # Skip cross-references like "9.2 Virtual
                            # Networking Hardware on page 144" which
                            # appear on pages belonging to OTHER chapters.
                            after_txt = txt[m.end() : m.end() + 60]
                            has_on_page = bool(
                                re.search(r"\bon\s+page\s+\d+", after_txt)
                            )
                            if has_on_page:
                                continue
                            if not self._pin_fits_window(chapter_first_pg, ch, page):
                                continue
                            chapter_first_pg[ch] = page
                            if len(chapter_first_pg) >= 25:
                                break

                # Phase 2: post-loop targeted scan for chapters known to exist but not yet found
                # Only scans up to max(chapters_to_cover) + 1 to avoid phantom chapters
                missing = [
                    n
                    for n in range(
                        1, max({ct[0] for ct in chapters_to_cover}, default=0) + 1
                    )
                    if n not in chapter_first_pg
                ]
                # License-caption placeholders carry no real title; the loose
                # digit rescue below would pin them to any in-text digit
                # ("6 Devices ...").  Phase-3 interpolation between the real
                # neighbors owns those chapters instead.
                titleless_roster_ = {
                    ct[0] for ct in chapters_to_cover if ct[1] == src and not ct[2]
                }
                missing = [n for n in missing if n not in titleless_roster_]
                if missing:
                    for chunk in storage.get_body_chunks(src, limit=None):
                        txt = chunk.get("chunk_text", "")[:150]
                        pg2 = int(chunk.get("page_number") or 0)
                        if pg2 in boiler_pages_:
                            continue
                        if pg2 in toc_like_pages_:
                            # Same defense as the section scan: printed-ToC
                            # pages carry every chapter's number somewhere.
                            continue
                        # Ordering note: this tier runs AFTER the run-on ToC
                        # row recovery above, whose `ch not in chapter_first_pg`
                        # guard already excludes chapters that recovery pinned
                        # (its `missing` list is rebuilt from chapter_first_pg).
                        # PVE ch6: recovery pins the printed-136 row at physical
                        # 158 BEFORE this scan matches a loose "6" ("Proxmox VE
                        # 6.2, ...") on real ch5 content @134 — the wrong pin is
                        # therefore unreachable, and no extra guard is needed
                        # here (a rescue firing before recovery would need one).
                        for ch_num in list(missing):
                            if desc_pages.get(ch_num) == pg2:
                                continue
                            pat = re.compile(rf"\b{ch_num}\D")
                            # Front matter never anchors: same floor as the scan above.
                            if (
                                pg2 >= 10
                                and pat.search(txt)
                                and self._pin_fits_window(chapter_first_pg, ch_num, pg2)
                            ):
                                chapter_first_pg[ch_num] = pg2
                                missing.remove(ch_num)
                        if not missing:
                            break

                # Merge appendix labels detected from body section numbering
                # into appendix_entries (from _derive_chapter_numbers).
                seen_appendix_labels: set[str] = {al[0] for al in appendix_entries}
                for label in sorted(appendix_labels_found):
                    if label not in seen_appendix_labels:
                        seen_appendix_labels.add(label)
                        appendix_entries.append((label, src, f"Appendix {label}"))

                # Phase 3: interpolate page numbers for chapters still missing.
                # Interpolate over the FULL src roster (minus ToC-verified
                # phantoms), not just the target-filtered set: a title-less
                # middle chapter (PVE 9.1 ch6) splits the pin map into
                # disjoint runs, and the consecutive-run trim below then
                # discards the target's pins.  Boundary chapters are needed
                # even when untargeted — a target's end page is the next
                # chapter's start page.
                # Only interpolates chapters known to exist (from
                # _derive_chapter_numbers); hardcoded 1-21 would create
                # phantom chapters for shorter docs.
                full_src_nums_ = {
                    ct[0]
                    for ct in full_chapters
                    if ct[1] == src and ct[0] not in toc_killed_
                }
                for n in sorted(full_src_nums_):
                    if n in chapter_first_pg:
                        continue
                    before = max([k for k in chapter_first_pg if k < n], default=None)
                    after = min([k for k in chapter_first_pg if k > n], default=None)
                    bp = chapter_first_pg[before] if before is not None else None
                    ap = chapter_first_pg[after] if after is not None else None
                    if bp is not None and ap is not None:
                        # A midpoint equal to bp (gap <= 1) duplicates that
                        # anchor pin instead of splitting the range.
                        if ap - bp >= 2:
                            chapter_first_pg[n] = (bp + ap) // 2
                    elif bp is not None:
                        chapter_first_pg[n] = bp + 1
                    elif ap is not None and ap > 1:
                        chapter_first_pg[n] = ap - 1

                # Drop stragglers (e.g. ch24 after ch18) via long-consecutive-run
                sorted_chs = sorted(chapter_first_pg)
                if sorted_chs:
                    runs: list[list[int]] = [[sorted_chs[0]]]
                    for i in range(1, len(sorted_chs)):
                        if sorted_chs[i] - sorted_chs[i - 1] == 1:
                            runs[-1].append(sorted_chs[i])
                        else:
                            runs.append([sorted_chs[i]])
                    # The run filter must never discard a run carrying a
                    # roster chapter: after Phase-3 full-roster interpolation
                    # the map should be gapless, but a chapter whose
                    # interpolation was refused still splits the runs — and
                    # dropping the SHORTER run once deleted five correct
                    # pins (1-5) because one chapter (PVE ch6) lost its
                    # title heading.  Merge runs that contain roster
                    # chapters into the longest run; stray pins outside the
                    # roster still die.
                    main_run = max(runs, key=len)
                    main_set = set(main_run)
                    for run in runs:
                        if run is main_run:
                            continue
                        if full_src_nums_ & set(run):
                            main_set |= set(run)
                    chapter_first_pg = {
                        k: v for k, v in chapter_first_pg.items() if k in main_set
                    }
                # Drop chapters with duplicate first-word (≥ 6 chars).
                # "VBoxManage CLI Reference" and "VBoxManage Command Reference"
                # both start with "VBoxManage" → ch19 excluded from unique_nums.
                # Derive the surviving set from the FULL src roster: in
                # single-target mode the filtered roster holds only the target,
                # and sec_buffer = max_unique + 3 would then delete the
                # boundary pins (ch_next, …) that end the target's page range,
                # letting the next chapters' pages leak into its bucket.
                seen_first: set[str] = set()
                unique_nums: set[int] = set()
                for ct in full_chapters:
                    if ct[1] != src or len(ct[2]) < 3:
                        continue
                    fw = ct[2].lower().split()[0]
                    if len(fw) >= 6 and fw in seen_first:
                        continue
                    seen_first.add(fw)
                    unique_nums.add(ct[0])
                if unique_nums:
                    max_unique = max(unique_nums)
                    # NOTE: sec_buffer = max_unique + 3 assumes sequential chapter
                    # numbering (no gap >3 between any two mapped chapters).
                    # If chapter numbers jump e.g. ch1→ch11→ch25 and ch11 is the
                    # only target, Pass 1 drops ch25 (>14), leaving ch11 as the
                    # last entry in sorted_pgs → end page falls back to 700,
                    # re-introducing cross-chapter leakage.  A production doc
                    # with such sparse numbering would need a smarter ceiling.
                    sec_buffer = max_unique + 3  # Match SEC_RE's extension range
                    # Pass 1: auto-keep known + within SEC_RE range, drop beyond
                    for k in list(chapter_first_pg):
                        if k in unique_nums:
                            continue
                        if k > sec_buffer:
                            del chapter_first_pg[k]
                    # Pass 2: drop SEC_RE-only chapters with first-word collisions
                    # (catches ch19 "VBoxManage" dup with ch15 while keeping ch17-18)
                    for k in list(chapter_first_pg):
                        if k in unique_nums or k <= max_unique:
                            continue
                        kt = next(
                            (
                                ct[2]
                                for ct in chapters_to_cover
                                if ct[0] == k and ct[1] == src
                            ),
                            "",
                        )
                        if kt:
                            kw = kt.lower().split()[0]
                            if len(kw) >= 6 and kw in seen_first:
                                del chapter_first_pg[k]
                # Pass 3: keep boundary chapters for page-range interpolation
                # even when they are not target chapters, then restrict the
                # output page ranges to only target chapters below.
                target_ch_nums = {ct[0] for ct in chapters_to_cover}

                # Build sorted page ranges from ALL boundary chapters
                sorted_pgs = sorted(chapter_first_pg.items(), key=lambda x: x[1])
                chapter_ranges_: dict[int, tuple[int, int]] = {}
                # Build boundary page mapping for end-page computation.
                # Keep ALL chapter boundaries so that end-page calculation for a
                # target chapter can see the next non-target chapter boundary.
                # We guard against sec_header_re false positives (which produce
                # start>end ranges) by skipping any next-chapter boundary whose
                # page number is <= the current chapter's start page.
                boundary_pgs = dict(chapter_first_pg)
                max_ch_ = max(boundary_pgs) if boundary_pgs else 0
                for ch_, start_pg_ in sorted_pgs:
                    # Only build ranges for target chapters
                    if ch_ not in target_ch_nums:
                        continue
                    # Find the next chapter IN SEQUENCE (ch+1, ch+2, ...) in the
                    # boundary map — NOT the next entry in page-sorted order.
                    # Otherwise interleaved page numbers produce wrong end pages
                    # (e.g. ch5 at p51 with ch1 at p56 in page order → end=55).
                    # Skip any boundary whose page is <= start_pg_ to avoid
                    # false positives producing start>end ranges.
                    # The sentinel must exceed any real book length: a fixed
                    # 700 inverted the last chapter's range for books with
                    # >700 pages (start>end → empty bucket → placeholder).
                    end_pg_ = 10**6
                    for nxt in range(ch_ + 1, max_ch_ + 2):
                        if nxt in boundary_pgs and boundary_pgs[nxt] > start_pg_:
                            end_pg_ = boundary_pgs[nxt] - 1
                            break
                    chapter_ranges_[ch_] = (start_pg_, end_pg_)

                chapter_keys = sorted(chapter_ranges_.keys())
                if not chapter_keys:
                    logger.warning(
                        "No chapter page ranges derived for %s; "
                        "falling back to generic search",
                        src,
                    )
                    logger.debug("chapter_first_pg was empty: %s", chapter_first_pg)
                    return self._generic_one_shot(
                        query, top_k, show_sources, source_filter=source_filter
                    )
                # Enumeration completeness: a target roster chapter no tier
                # pinned still belongs in the answer.  Give it an empty
                # sentinel range — its bucket stays empty and the existing
                # placeholder-note path speaks for it, instead of the chapter
                # silently vanishing from the enumeration.  Scoped to the
                # selected source: a foreign-source roster entry (another
                # book's chapter row surviving the phantom kill) must not
                # gain a placeholder from THIS book's summary.  Boundary
                # computation above already ran on chapter_first_pg, so
                # sentinel ranges cannot shift any real chapter's end page.
                tgt_src_nums_ = {ct[0] for ct in chapters_to_cover if ct[1] == src}
                for tgt_ch_ in sorted(tgt_src_nums_):
                    if tgt_ch_ not in chapter_ranges_:
                        chapter_ranges_[tgt_ch_] = (0, -1)
                logger.debug(
                    "Chapter page ranges for %s: %s",
                    src,
                    chapter_ranges_,
                )
                # Chapter-range agreement gate (add-anthology-aware-chapter-
                # summarization): the map above assumes one monotone chapter
                # sequence; on shapes it was never tuned for it can be
                # confidently wrong.  Cross-check each final range start
                # against the RAW provisional N.1 evidence pins (±2 pages —
                # the unfiltered map, see evidence_pins_all_ above: the
                # window-filtered evidence_pin_pg_ keeps too few pins on
                # anthology shapes to compare); below the calibrated
                # agreement threshold, refuse per-chapter enumeration and
                # degrade to a whole-document overview instead of emitting
                # wrong-page chapter summaries.  The gate never modifies pins
                # or ranges; passing documents proceed byte-identically.
                if not self._chapter_range_gate(
                    chapter_ranges_, evidence_pins_all_, src
                ):
                    return {
                        "answer": self._generate_whole_document_overview(body_all_),
                        "query": query,
                    }
                # Fetch mode counts real ranges only: sentinel ranges must
                # not flip a small book's single-section full fetch into
                # round-robin sampling.
                single_section_mode = len(chapter_keys) <= 2
                chapter_keys = sorted(chapter_ranges_.keys())
                # Per-chapter fetch budget for multi-chapter overviews.  Each
                # chapter is summarized independently via _summarize_bounded
                # (single-pass budget 320k chars), so 8 chunks stay within one
                # LLM call per chapter while tripling per-chapter coverage
                # versus the old 4-chunk cap, which summarized dense chapters
                # from one or two pages.
                per_chapter_limit = 8
                chapter_buckets: dict[int, list[dict[str, Any]]] = {
                    ch: [] for ch in chapter_keys
                }
                if single_section_mode:
                    # Deterministic full-chapter fetch: every body chunk inside
                    # the chapter's page range, in document order, with no
                    # per-chapter or per-page caps.  The previous capped
                    # sampling silently dropped dense pages from single-chapter
                    # overviews; the summarizer bounds its own context
                    # downstream, so fetching everything here is lossless.
                    for ch_num in chapter_keys:
                        start_pg_, end_pg_ = chapter_ranges_[ch_num]
                        in_range = [
                            c
                            for c in cast(
                                list[dict[str, Any]],
                                storage.get_body_chunks(src, page_gte=start_pg_),
                            )
                            if (c.get("page_number") or 0) <= end_pg_
                        ]
                        in_range.sort(
                            key=lambda c: (
                                c.get("page_number") or 0,
                                c.get("page_pos") or 0,
                            )
                        )
                        for c in in_range:
                            c["score"] = 0.5
                        chapter_buckets[ch_num] = in_range
                else:
                    # Multi-chapter round-robin: per-page caps keep sampling
                    # spread across the chapter's range instead of clustering
                    # on its first pages.
                    page_cap = 3
                    page_count_per_ch: dict[int, dict[int, int]] = {
                        ch: {} for ch in chapter_keys
                    }
                    for c in cast(
                        list[dict[str, Any]], storage.get_body_chunks(src, limit=6000)
                    ):
                        pg = c.get("page_number", 0)
                        for ch_num in chapter_keys:
                            rng = chapter_ranges_[ch_num]
                            if rng[0] <= pg <= rng[1]:
                                if len(chapter_buckets[ch_num]) < per_chapter_limit:
                                    per_page = page_count_per_ch[ch_num]
                                    if per_page.get(pg, 0) < page_cap:
                                        per_page[pg] = per_page.get(pg, 0) + 1
                                        c["score"] = 0.5
                                        chapter_buckets[ch_num].append(c)
                                    else:
                                        # Page at cap — promote header chunks over
                                        # footers/captions that were collected first.
                                        # Use a broader match: docling often embeds
                                        # section headers (e.g. "11.2 CPU Hot-Plugging")
                                        # in the middle of paragraph text rather than
                                        # at the start of a segment.
                                        txt = c.get("chunk_text", "")
                                        sec_pat = re.compile(
                                            rf"\b{ch_num}\.\d+(?:\.\d+)?\s"
                                        )
                                        if sec_pat.search(txt):
                                            replaced = False
                                            for i, existing in enumerate(
                                                chapter_buckets[ch_num]
                                            ):
                                                if existing.get(
                                                    "page_number"
                                                ) == pg and not sec_pat.search(
                                                    existing.get("chunk_text", "")
                                                ):
                                                    c["score"] = 0.5
                                                    chapter_buckets[ch_num][i] = c
                                                    replaced = True
                                                    break
                                            # All existing page entries are also section
                                            # headers — grant extra slots to avoid losing
                                            # genuine section content. Allow up to 4 per
                                            # page for pages with dense section headers
                                            # (e.g. VirtualBox ch11 p186 has 4: 11.6.3,
                                            # 11.6.4, 11.6.4.1, 11.6.5).
                                            if not replaced:
                                                if per_page.get(pg, 0) < page_cap + 2:
                                                    per_page[pg] = (
                                                        per_page.get(pg, 0) + 1
                                                    )
                                                    c["score"] = 0.5
                                                    chapter_buckets[ch_num].append(c)
                                                else:
                                                    logger.debug(
                                                        "Page %s at cap (%s slots), section header "
                                                        "'%s...' dropped (all %s existing entries "
                                                        "also have section numbers)",
                                                        pg,
                                                        per_page.get(pg, 0),
                                                        txt[:60],
                                                        len(chapter_buckets[ch_num]),
                                                    )
                                break

                # Post-processing: inject missing section headers.
                # Docling sometimes drops section numbers from body chunks
                # (e.g. "11.1 Automated Guest Logins" loses its "11.1 " prefix).
                # For each chapter, check if the expected first section (ch.1)
                # is missing from the bucket; if so, prepend it to the first
                # chunk that lacks a section header.
                # NOTE: Use \b{ch_num}\.1\b (not \b{ch_num}\.\d+) to avoid
                # matching e.g. 11.10 when 11.1 is actually missing.
                for ch_num in chapter_keys:
                    sec_pat_inject = re.compile(rf"\b{ch_num}\.1\b")
                    has_first = any(
                        sec_pat_inject.search(c.get("chunk_text", ""))
                        for c in chapter_buckets[ch_num]
                    )
                    if not has_first:
                        for c in chapter_buckets[ch_num]:
                            ct = c.get("chunk_text", "")
                            if not sec_pat_inject.search(ct) and ct.strip():
                                c["chunk_text"] = f"{ch_num}.1 " + ct
                                break

                # Merge buckets in round-robin order
                unique_by_hash: dict[int, dict[str, Any]] = {}
                hashes_seen: set[int] = set()
                max_bucket = max(len(b) for b in chapter_buckets.values())
                for slot in range(max_bucket):
                    for ch_num in chapter_keys:
                        bucket = chapter_buckets[ch_num]
                        if slot < len(bucket):
                            c = bucket[slot]
                            h = hash(c.get("chunk_text", "")[:512])
                            if h not in hashes_seen:
                                hashes_seen.add(h)
                                unique_by_hash[h] = c

                accumulated = list(unique_by_hash.values())
                accumulated.sort(key=lambda c: c.get("score", 0.0), reverse=True)
                if single_section_mode:
                    # The deterministic fetch returned the complete chapter;
                    # trimming here would drop real content.  The summarizer
                    # bounds its own context downstream.
                    final_chunks = accumulated
                else:
                    # Use the larger of top_k and per_chapter_limit for the
                    # final trim so the merged multi-chapter context stays
                    # bounded while single chapters keep their spread.
                    final_chunks = accumulated[: max(top_k, per_chapter_limit)]

                # Reorder chunks interleaving pages (round-robin by page) so the
                # LLM sees content from diverse pages early rather than sequential
                # page order. This prevents recency bias where the first few pages'
                # sections (e.g. ch5 section 5.1 across pages 51-59) dominate the
                # LLM's output.
                if len(chapter_keys) <= 2:
                    pg_groups: dict[int, list[dict[str, Any]]] = {}
                    for fc in final_chunks:
                        p = fc.get("page_number", fc.get("page", 0))
                        pg_groups.setdefault(p, []).append(fc)
                    interleaved: list[dict[str, Any]] = []
                    max_per_pg = max((len(g) for g in pg_groups.values()), default=0)
                    for slot in range(max_per_pg):
                        for pg in sorted(pg_groups):
                            if slot < len(pg_groups[pg]):
                                interleaved.append(pg_groups[pg][slot])
                    final_chunks = interleaved

                if appendix_entries and enum_target is None:
                    # Use only target chapters for the appendix start page.
                    # Non-target chapters from sec_header_re false positives
                    # (e.g. a phantom "22.3" at the very end of the document)
                    # would push the start page past all appendix content.
                    # The sweep is single-target-blind: in a "chapter N" query
                    # its start page (the target's opener) sweeps the +200
                    # following chunks — i.e. the NEXT chapters' bodies — into
                    # the answer (PVE: chapter 1's bucket came back with
                    # pages 23-54 instead of 23-31).  The book-wide appendix
                    # capture only makes sense for whole-book enumeration.
                    appendix_start_pg = max(
                        (
                            chapter_first_pg.get(k, 0)
                            for k in target_ch_nums
                            if k in chapter_first_pg
                        ),
                        default=0,
                    )
                    _max_appendix = 200
                    appendix_body_chunks = list(
                        storage.get_body_chunks(
                            src,
                            page_gte=appendix_start_pg,
                            limit=_max_appendix,
                        )
                    )
                    final_chunks.extend(
                        cast(list[dict[str, Any]], appendix_body_chunks)
                    )
                    # Re-deduplicate to remove any overlap between appendix
                    # chunks and already-selected body chunks.
                    _seen_ids: set[str] = set()
                    _deduped: list[dict[str, Any]] = []
                    for c in final_chunks:
                        cid = c.get("chunk_id")
                        if cid is None or cid not in _seen_ids:
                            if cid is not None:
                                _seen_ids.add(cid)
                            _deduped.append(c)
                    final_chunks = _deduped

                # Build chapter roster
                ch_titles: dict[int, str] = {}
                for ct in chapters_to_cover:
                    if ct[0] in good_title_nums and ct[0] not in ch_titles:
                        ch_titles[ct[0]] = ct[2]
                chapter_roster_lines = []
                for ch_num in sorted(chapter_ranges_.keys()):
                    pg_start, pg_end = chapter_ranges_[ch_num]
                    title = self._display_chapter_title(ch_titles.get(ch_num, ""))
                    # An unpinned chapter's sentinel range has no page to
                    # advertise; "(approx pages 0+)" would read as a bogus
                    # claim, so its roster line omits the page suffix.
                    pg_note = (
                        "" if pg_end < pg_start else f" (approx pages {pg_start}+)"
                    )
                    if title:
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} — {title}{pg_note}"
                        )
                    else:
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} — No official title{pg_note}"
                        )
                chapter_roster = "\n".join(chapter_roster_lines)

                if appendix_entries:
                    chapter_roster += "\n\n" + "\n".join(
                        f"Appendix {label} — {title}"
                        for label, _src, title in appendix_entries
                    )
                chapter_roster += "\n"

                # Single-chapter enumeration needs more context window to fit
                # sampled chunks from across the full page range.
                # Use *3 to balance coverage with LLM latency: *6 (96000 chars)
                # caused request timeouts (24000 input + 32768 output tokens
                # ≈ 56K total, exceeding the LLM provider's time budget).
                # *3 = 48000 chars ≈ 12000 input tokens; at 600 chars/page
                # covers ~80 pages — enough for most chapters.
                enum_max_chars = (
                    self._config.rag_max_context_chars * 3
                )  # ~48000 chars, balanced for 120s LLM timeout
                body_content = self._format_context(
                    final_chunks, max_chars=enum_max_chars
                )

                ql = query.lower()
                # "by section X.Y" means focus on that section, not enumerate all
                wants_sections = (
                    any(
                        p in ql
                        for p in (
                            "by sections",
                            "by section",
                            "list sections",
                            "list all sections",
                            "list section",
                            "sections of",
                            "show sections",
                            "enumerate sections",
                            "section listing",
                        )
                    )
                    and not bool(
                        re.search(r"by section \d+", ql)
                    )  # "by section 5.1" → focus
                )

                # Determine whether this is a multi-chapter query (e.g. "summarize by chapter"
                # with no specific chapter target) vs a single-chapter query.
                is_multi_chapter = not intent_decision.target and not has_section_target

                if has_section_target and raw_section_target:
                    # User asked about a specific section (e.g. "summarize section 11.16").
                    section_prompt = (
                        f"The user asked for a summary of section {raw_section_target}. "
                        f"Below is the content of chapter {enum_target}, which contains "
                        f"section {raw_section_target}. Provide a detailed, focused summary "
                        f"of section {raw_section_target} specifically. Include its key "
                        f"topics, instructions, and any important details.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif has_section_target:
                    # User asked about a specific chapter (e.g. "tell me about chapter 11").
                    # Provide a thorough section-level breakdown instead of a concise summary.
                    section_prompt = (
                        "__DETAILED_CHAPTER_SUMMARY_INSTRUCTIONS__\n"
                        + f"The user asked for details about chapter {enum_target}. "
                        + "Below is the content of that chapter. Provide a thorough, detailed "
                        + "summary of the chapter's content, organized by its numbered sections. "
                        + "For each section, include its number, title, and a description of its "
                        + "key topics and important details. Do NOT omit any section.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif wants_sections:
                    # Section enumeration — list every section concisely.
                    # Use adjective clauses (", which covers …") to keep each line
                    # short while still adding value, staying well within the token
                    # budget so the LLM doesn't truncate mid-way through the chapter.
                    section_prompt = (
                        "__ENUMERATION INSTRUCTIONS__\n"
                        + "The user asked for a section listing. "
                        + "List every numbered section below on its own line. "
                        + "For each section, include its number (e.g. 11.1) followed by "
                        + "a brief one-line description. Do NOT omit any section.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif is_multi_chapter:
                    # Multi-chapter ("summarize by chapter"): ask the LLM to give
                    # a concise overview of each chapter found in the body content.
                    section_prompt = (
                        "__CHAPTER_SUMMARY_INSTRUCTIONS__\n"
                        + "The user asked for a chapter-by-chapter overview. "
                        + "Below is the document's content organized by chapter. "
                        + "For each chapter listed in the roster above, provide "
                        + "a brief one-line summary of its key topics. "
                        + "Keep each chapter summary concise.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                else:
                    # Single-chapter summary (no section request).
                    section_prompt = (
                        "Keep your answer concise. Do NOT list numbered sections or provide "
                        "a section-by-section breakdown. Instead, give a brief paragraph "
                        "summarizing the overall content of the chapter.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                context_text = chapter_roster + section_prompt + body_content

                llm_fallback_roster = "\n".join(chapter_roster_lines)
                if appendix_entries:
                    llm_fallback_roster += "\n\n" + "\n".join(
                        f"Appendix {label} — {title}"
                        for label, _src, title in appendix_entries
                    )
                llm_fallback_roster += "\n"

                generation_start = time.perf_counter()
                answer = ""
                try:
                    if is_multi_chapter and chapter_buckets:
                        # Map-reduce the chapter-by-chapter overview: one bounded
                        # LLM call per chapter, then concatenate.  A single call
                        # covering every chapter overflows the output token budget
                        # and degenerates into token-soup after a few chapters.
                        with trace_operation("rag_generation_iterative") as span:
                            if span:
                                span.set_attribute("rag.iterative_mode", True)
                                span.set_attribute("rag.enumeration_mode", True)
                                span.set_attribute("rag.top_k", top_k)
                            answer = self._generate_multi_chapter_summary(
                                chapter_keys, chapter_buckets, ch_titles
                            )
                    elif has_section_target and not raw_section_target and final_chunks:
                        # Single-chapter detailed breakdown (e.g. "tell me about
                        # chapter 18").  Map-reduce by section: summarizing the
                        # whole chapter in one call overflows the output token
                        # budget and degenerates into token-soup part-way through.
                        with trace_operation("rag_generation_iterative") as span:
                            if span:
                                span.set_attribute("rag.iterative_mode", True)
                                span.set_attribute("rag.enumeration_mode", True)
                                span.set_attribute("rag.top_k", top_k)
                            chapter_title = next(
                                (
                                    t
                                    for ct, _s, t in chapters_to_cover
                                    if str(ct) == str(enum_target)
                                ),
                                "",
                            )
                            foreign_titles = [
                                t
                                for ct, _s, t in full_chapters
                                if str(ct) != str(enum_target) and t
                            ]
                            answer = self._generate_single_chapter_summary(
                                final_chunks,
                                str(enum_target),
                                chapter_title,
                                foreign_titles=foreign_titles,
                            )
                    else:
                        # Single-chapter overview (this query's path): generate
                        # non-streaming, vet (ground figures to the source and
                        # regenerate deterministically if the draft leaked reasoning,
                        # was empty, or burned the reasoning budget), then emit once
                        # -- so a spiral or "I got stuck" is never shown and figures
                        # are quoted from the source.
                        prompt = self._build_prompt(query, context_text)
                        prompt += (
                            "\n\nYou are summarizing source material. Quote figures "
                            "(percentages, counts, years, metrics, returns) EXACTLY as "
                            "stated in the retrieved context; never invent, estimate, "
                            "round, or 'correct' a value the source does not state. "
                            "This rule applies to prose statistics only -- do not "
                            "fixate on reproducing code details or function arguments "
                            "(e.g. list(range(...))) verbatim. State each figure once, "
                            "confidently, and move on."
                        )
                        with trace_operation("rag_generation_iterative") as span:
                            if span:
                                span.set_attribute("rag.iterative_mode", True)
                                span.set_attribute("rag.enumeration_mode", True)
                                span.set_attribute("rag.top_k", top_k)
                            answer = self._vet_answer(
                                self._generate(prompt), prompt, context_text
                            )
                            if self._on_chunk and answer:
                                self._on_chunk(answer, None)
                except Exception as e:
                    logger.error(
                        "Iterative query generation failed: %s: %s", type(e).__name__, e
                    )
                    answer = f"An error occurred during generation: {e}"
                finally:
                    metrics.record(
                        "generation_latency", time.perf_counter() - generation_start
                    )

                # If the LLM returned empty (transient failure, cold start, etc.),
                # fall back to the chapter roster so the user gets something useful.
                if not answer or not answer.strip():
                    answer = llm_fallback_roster

                result: dict[str, Any] = {"answer": answer, "query": query}
                if show_sources:
                    result["sources"] = final_chunks
                return result
            else:
                # No chapters were detected/covered. If the user explicitly
                # requested a specific chapter (e.g. "chapter 5") that does
                # not exist, report it. Otherwise (e.g. "summarize X" with no
                # chapter number), fall through to the generic top-k search
                # below instead of emitting a misleading "couldn't find
                # chapter" error.
                if intent_decision.target is not None:
                    target_label = f"chapter {intent_decision.target}"
                    return {
                        "answer": f"I couldn't find {target_label} in the document.",
                        "query": query,
                    }
                # else: fall through to generic search (Branch B) below

        # 2. Generic top-k search: one embedding call, no per-page
        # iteration (which would make 8000+ embedding requests).
        # Scoped retrieval embeds the name-stripped query: the raw string
        # carries path tokens that pollute the embedding and depress its
        # score against the document's own chunks. Prompts, the result dict,
        # and _handle_no_results keep the ORIGINAL query.
        search_query = self._scoped_search_query(query) if source_filter else query
        accumulated = self._searcher.search(
            search_query,
            top_k=top_k,
            source_filter=source_filter,
        )

        # 4. Sort by score descending and trim to top_k
        accumulated.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        final_chunks = self._dedupe_by_text_hash(accumulated)[:top_k]

        if not self._has_relevant_chunks(
            final_chunks, threshold=self._relevance_gate_threshold(source_filter)
        ):
            return {
                "answer": self._handle_no_results(query),
                "query": query,
            }

        chapter_roster = self._derive_chapter_roster(structure_chunks)
        context_text = chapter_roster + self._format_context(final_chunks)
        prompt = self._build_prompt(query, context_text)

        # 6. Generate answer. Every query that reaches _iterative_query is a
        #    chapter/section/coverage summary, so generate non-streaming and vet
        #    (ground figures to the source; a leak/empty/budget-fallback
        #    regenerated deterministically) then emit once -- a reasoning spiral or
        #    "I got stuck" can never surface in the terminal.
        generation_start = time.perf_counter()
        answer = ""
        try:
            with trace_operation("rag_generation_iterative") as span:
                if span:
                    span.set_attribute("rag.iterative_mode", True)
                    span.set_attribute("rag.top_k", top_k)

                prompt += (
                    "\n\nYou are summarizing source material. Quote figures "
                    "(percentages, counts, years, metrics, returns) EXACTLY as stated "
                    "in the retrieved context; never invent, estimate, round, or "
                    "'correct' a value the source does not state. This rule applies to "
                    "prose statistics only -- do not fixate on reproducing code "
                    "details or function arguments (e.g. list(range(...))) verbatim. "
                    "State each figure once, confidently, and move on."
                )
                answer = self._vet_answer(self._generate(prompt), prompt, context_text)
                if not answer or not answer.strip():
                    answer = (
                        "I couldn't produce a complete summary. Please try again or "
                        "narrow the scope of your request."
                    )
                if self._on_chunk and answer:
                    self._on_chunk(answer, None)
        except Exception as e:
            logger.error(
                "Iterative query generation failed: %s: %s", type(e).__name__, e
            )
            answer = f"An error occurred during generation: {e}"
        finally:
            metrics.record("generation_latency", time.perf_counter() - generation_start)

        # 7. Build result
        result = cast(dict[str, Any], {"answer": answer, "query": query})
        if show_sources:
            result["sources"] = final_chunks

        return result
