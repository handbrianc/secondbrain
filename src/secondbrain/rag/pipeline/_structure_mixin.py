"""Chapter/section detection and structural helpers for the RAG pipeline."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, ClassVar, cast

from secondbrain.rag.intent_parser import QueryIntent
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.rag.pipeline._constants import (
    BROAD_COVERAGE_TRIGGERS,
    CHAPTER_ENUMERATION_PATTERNS,
    ENUMERATE_CHAPTER_SIGNALS,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _REASONING_BUDGET_FALLBACK_PREFIX,
    _contains_reasoning_leak,
)
from secondbrain.rag.pipeline._text_quality import (
    _ground_figures,
    _prune_implausible_metric_figures,
)
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)

logger = logging.getLogger(__name__)

# Front-matter "about this book" pages describe every chapter in prose:
# "Chapter 9 , AI Cloud Platforms for IoT , introduces major cloud platforms ...".
# These body-role sentences are the only "Chapter N" matches in books extracted
# without real heading/toc_entry chunks, and pinning a chapter's start page to
# the page its description sits on collapses the chapter's page range to that
# front-matter page and starves its content bucket.  The pattern requires the
# comma form ("Chapter N , Title") plus a description verb shortly after, so
# genuine headings ("Chapter 9: AI Cloud Platforms", "9 AI Cloud Platforms") and
# cross-references ("see Chapter 9 on page 144") never match.
_CHAPTER_DESC_RE = re.compile(
    r"Chapter\s+(\d+)\s*,\s+[A-Z].{0,240}?\b(?:introduces|explores|focuses|"
    r"dives|delves|provides|covers|describes|examines|presents|outlines|"
    r"walks|discusses|explains|emphasizes|helps|contains|shows|builds|"
    r"teaches|prepares|starts|takes|brings|opens|closes|gives|guides|"
    r"includes|is\b)",
    re.DOTALL,
)


# Tail of a front-matter chapter-description sentence inside a captured title:
# "... , introduces the core concepts of IoT and edge computing ...".  Trimming
# at the description verb leaves the bare chapter title.  The leading comma is
# required so ordinary titles ("How Regularization Introduces Robustness") are
# never cut.
_CHAPTER_DESC_TAIL_RE = re.compile(
    r",\s+(?:introduces|explores|focuses|dives|delves|provides|covers|describes|"
    r"examines|presents|outlines|walks|discusses|explains|emphasizes|helps|"
    r"contains|shows|builds|teaches|prepares|starts|takes|brings|opens|closes|"
    r"gives|guides|includes|is\b).*$",
)


# Front-matter ToC listing lines, parsed for the chapter pin/phantom-kill
# reconciliation tier.  Docling flattens the printed ToC into two row shapes:
# bare listing lines ("12 Bayesian Deep Learning 310") and Chapter-prefixed
# rows ("Chapter 4: Unsupervised Graph Learning 107") that run-on into the
# next entry on the same flattened line.  The per-line anchor plus the lazy
# 2-90 char letter-started title keeps a run-on section row ("584 Using
# Spearman's rank correlation ...") from satisfying the trailing page capture;
# roman-numeral rows ("IX Old Chapters 55") and multi-line fragments (page
# number orphaned on the next line) match neither shape and parse to nothing.
_TOC_LISTING_LINE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z].{2,90}?)\s+(\d{1,3})\s*$")


_TOC_CHAPTER_ENTRY_RE = re.compile(
    r"Chapter\s+(\d{1,2})\s*[:.\-]\s*([A-Za-z].{2,90}?)\s+(\d{1,3})\b"
)


# Same Chapter-prefixed row WITHOUT a trailing page number (a wrapped entry,
# or one whose page number was lost in extraction).  A roster chapter with
# such a row in the ToC region is ambiguous, so the tier keeps (never kills)
# it and logs instead.
_TOC_CHAPTER_MENTION_RE = re.compile(r"Chapter\s+(\d{1,2})\s*[:.\-]")


# Coverage floor for the reconciliation tier: the parsed ToC must list at
# least this fraction of the roster chapters before a pin or a phantom kill
# may act; below it the tier is fully disabled.
_TOC_MIN_COVERAGE = 0.6


# Section-heading evidence pins: a chapter's own first numbered section
# ("7.1 Introductory Topics", or a deeper "7.1.2 ...") is the strongest
# structural chapter-start signal in heading-role output — docling keeps the
# ``N.1`` heading on (or next to) the chapter's opening page even when the
# banner/title heading itself is dropped.  Anchored at the first line so
# mid-prose section references never match; the captured group names the
# chapter and is capped at 30 by the caller (same bound as the section scan).
_SECTION_PIN_RE = re.compile(r"^(\d{1,2})\.1(?:\.\d+)?\s+")


# ToC-like page classification (see :meth:`_dot_leader_page`): a flattened
# printed ToC is dominated by lines ending in a page serial ("12 Bayesian
# Deep Learning 310") or carrying dot leaders ("Chapter 8 ....... 223").
_DOT_LEADER_TAIL_RE = re.compile(r"\d{1,4}$")
_DOT_LEADER_RUN_RE = re.compile(r"\.{2,}")
# Share of a page's non-empty lines that must look like ToC rows before the
# page is classified ToC-like; 60% keeps prose pages that merely end a few
# lines with a year or figure from being misclassified.
_DOT_LEADER_MIN_SHARE = 0.6


# Version-number tokens for heading-anchor token matching ("7" vs "7.2"):
# digits and dots only, so word tokens can never prefix-match each other.
_VERSION_TOKEN_RE = re.compile(r"\d+(?:\.\d+)*")


# Boilerplate caption detection: end-of-book license/colophon headings
# ("GNU Free Documentation License", GFDL numbered sections such as
# "6. COLLECTIONS OF DOCUMENTS") are tagged `heading` by docling, and their
# numbered-caps shape mimics bare-number chapter openers.  On the Proxmox VE
# 9.1 admin guide they seeded the chapter roster with a license-section
# title for a chapter whose real opener was never extracted, and anchored
# that chapter on the license page near the END of the book — which then
# cascade-killed every legitimate chapter pin in the monotonic validator.
# The gate requires the all-caps shape (real chapter titles are Title Case)
# AND a license-section token, so ordinary all-caps headings pass.
_BOILERPLATE_CAPTION_RE = re.compile(
    r"\b(?:(?:FREE\s+DOCUMENTATION|GENERAL\s+PUBLIC)\s+LICENSE|"
    r"PREAMBLE|APPLICABILITY\s+AND\s+DEFINITIONS|VERBATIM\s+COPYING|"
    r"COPY\s+IN\s+QUANTITY|MODIFICATIONS|COMBINING\s+DOCUMENTS|"
    r"COLLECTIONS\s+OF\s+DOCUMENTS|AGGREGATION\s+WITH\s+INDEPENDENT\s+"
    r"WORKS|TRANSLATION|TERMINATION|FUTURE\s+REVISIONS|"
    r"PERMISSION\s+NOTICE)\b"
)


# Standalone headings that start a license/colophon region regardless of
# letter case (unnumbered license openers between real appendices).
_BOILERPLATE_TITLE_RE = re.compile(
    r"^(?:the\s+)?GNU\s+(?:Free\s+Documentation|General\s+Public|Lesser\s+"
    r"General\s+Public)\s+License\b|^(?:MIT|Apache|BSD|ISC)\s+License\b",
    re.IGNORECASE,
)


# --- Anthology-aware chapter summarization ----------------------------------
# (add-anthology-aware-chapter-summarization.)  Compilations that concatenate
# several sub-reports — each restarting its own section numbering at 1 — break
# every assumption of the single monotone chapter sequence the legacy
# machinery below models, so such documents are detected up front and
# enumerated per part (routing in ``_pipeline.py``), with an agreement gate
# behind the legacy path so unknown shapes degrade to a whole-document
# overview instead of confident wrong-page summaries.

# Part-opener heading shapes, matched at the START of a heading chunk's text:
# a dotted roman-numeral part label followed by a separator — the corpus
# compilation's openers read "I.1 · From Vague Requirements to Well-Defined
# Epics" and "II.12 · Volume 11 — Frontend & Web UI Engineering" — or an
# explicit "Part N" word label ("Part I", "Part 2", "Part A").
_ANTHOLOGY_PART_OPENER_RE = re.compile(
    r"^(?P<label>[IVXLCDM]+\.\d+)\s*[\u00b7\u2013\u2014-]\s*(?P<title>\S.*)$"
)
_ANTHOLOGY_PART_WORD_RE = re.compile(
    r"^(?P<label>Part\s+(?:[IVX]+|\d+|[A-Z]))\b[.:\u00b7\u2013\u2014-]?\s*"
    r"(?P<title>\S.*)$"
)


# Numbered section heading inside a part — "1 Why Requirements Start Vague —
# and Why That Is Normal", "1.1 The nature of the problem", "2.2.1 ..." — the
# same start-of-heading digit-label shape the legacy section scans rely on
# (_SECTION_PIN_RE, section_re), generalized to any leading N(.M)* label.
# The detector's restart signal reads the part number (num.split(".")[0]);
# the per-part roster keeps the full dotted label with the heading's own page.
_ANTHOLOGY_SECTION_RE = re.compile(
    r"^(?P<num>\d{1,2}(?:\.\d{1,2})*)[.:]?\s+(?P<title>\S.*)$"
)


# Detector signal thresholds (design.md §1): a document is an anthology only
# with ≥3 part-opener headings AND ≥2 parts whose first numbered section
# restarts at 1.  Single-book shapes (chapter banners, straight 1..N
# numbering) carry no part-labeled headings and cannot satisfy the opener
# signal at all.
_ANTHOLOGY_MIN_OPENERS = 3
_ANTHOLOGY_MIN_RESTARTS = 2


# Per-part body-bucket sampling: exactly the legacy multi-chapter round-robin
# constants (_pipeline.py — per_chapter_limit = 8, page_cap = 3) so anthology
# part buckets sample like legacy chapter buckets, including the
# section-header promotion of capped pages.
_ANTHOLOGY_PART_CHUNK_LIMIT = 8
_ANTHOLOGY_PART_PAGE_CAP = 3
# Dotted "N.M" section-header shape used to promote a capped page's header
# chunk over footers/captions collected first.  The legacy rule keys on the
# bucket chapter's own number ("\b{ch_num}\.\d+(?:\.\d+)?\s"); per part the
# major is the part's own numbering namespace, so the shape stays dotted but
# number-agnostic.
_ANTHOLOGY_BUCKET_SECTION_RE = re.compile(r"\b\d{1,2}\.\d+(?:\.\d+)?\s")


# Scale gate (design.md §1 signal 3): a part spanning fewer than this many
# body-bearing pages is not a real sub-report — the enrichment then declines
# and the caller takes the legacy path.
_ANTHOLOGY_MIN_PART_BODY_PAGES = 2


# Chapter-range agreement gate calibration (design.md §3; recorded in
# tests/fixtures/chapter_map/baselines.json "gate_divergence"): the final
# range starts of the known-good corpus books agree with their provisional
# N.1 evidence pins for every chapter (user-manual 1.00 = 18/18 within ±2
# pages, pve-admin-guide 1.00 = 19/19), while the compilation's wrong global
# map agrees on only 2 of 8 comparable chapters (0.25).  A map is vetoed
# below 0.7 agreement, and the gate is skipped entirely when fewer than 4
# chapters are comparable — absence of evidence is not disagreement (the HCD
# report carries 0 evidence pins and keeps the legacy path).
_CHAPTER_GATE_MAX_PIN_DRIFT = 2
_CHAPTER_GATE_MIN_COMPARED = 4
_CHAPTER_GATE_MIN_SCORE = 0.7


def _anthology_is_heading_chunk(chunk: dict[str, Any]) -> bool:
    """Return True when a chunk is heading-role (role or element_type).

    The anthology scans receive the heading-chunk stream, but defensively
    accept either role marker so a caller passing role-or-element-matched
    chunks (find_structural_chunks ORs them) cannot slip a body chunk in.
    """
    role = chunk.get("chunk_role")
    if role is None or role == "heading":
        return True
    return chunk.get("element_type") == "heading"


def _anthology_heading_sort_key(chunk: dict[str, Any]) -> tuple[int, int]:
    """Document-order sort key for chunk streams: (page, position on page)."""
    return (
        int(chunk.get("page_number") or 0),
        int(chunk.get("page_pos") or 0),
    )


class _StructureMixin(_RAGPipelineState):
    """Chapter/section detection and structural helpers."""

    # Structure-tree query path (add-structure-aware-ingestion, tasks 12-14).
    # Both are assigned in ``RAGPipeline.__init__``; the store object is
    # created lazily on the first tree lookup so pipeline construction never
    # touches SQLite (or the shared conversation database).
    _structure_store: StructureStore | None
    _structure_store_ready: bool

    def _derive_chapter_roster(self, structure_chunks: list[dict[str, Any]]) -> str:
        import re

        if self._chunks_are_code_like(structure_chunks):
            # No prose structure to enumerate (see _chunks_are_code_like) — emit
            # an empty header so the LLM never sees a fabricated chapter index.
            return ""

        ch_entries, ch_good, appendix_entries = self._derive_chapter_numbers(
            structure_chunks
        )
        ch_titles: dict[int, str] = {}
        for ch_num, _src, title in ch_entries:
            if ch_num in ch_good and ch_num not in ch_titles:
                ch_titles[ch_num] = title if title else "Unknown"

        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        sec_entries: list[tuple[int, str, str]] = []
        seen_sec: set[str] = set()
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if major < 1 or major > 30:
                    continue
                full_match = m.group(0)
                sec_num = full_match.split()[0] if full_match else ""
                raw_title = (m.group(3) or "").strip().rstrip(".")
                if len(raw_title) < 2:
                    continue
                sec_key = f"{major}.{sec_num.split('.')[1] if '.' in sec_num else '0'}"
                if sec_key not in seen_sec:
                    seen_sec.add(sec_key)
                    sec_entries.append((major, sec_num, raw_title))

        sec_entries.sort(key=lambda x: (x[0], *[int(p) for p in x[1].split(".") if p]))

        # When authoritative "Chapter N" headings were detected, section numbers
        # from any other major are body-text noise (dataframe dumps, page stubs),
        # not real chapters — they must not spawn fabricated `[Chapter N]` lines.
        if ch_good:
            sec_entries = [s for s in sec_entries if s[0] in ch_good]

        # Group detected subsections by their parent chapter.
        sec_by_major: dict[int, list[tuple[str, str]]] = {}
        for major, sn, title in sec_entries:
            sec_by_major.setdefault(major, []).append((sn, title))

        # Build the index from the UNION of reliably-detected chapter headings
        # (ch_good) and chapters that have recognised subsections, so a chapter
        # whose heading was detected but whose section headers were not seen in
        # the probe chunks still appears instead of silently vanishing.
        chapter_nums = sorted(set(ch_good) | set(sec_by_major))

        lines: list[str] = []
        # Cap subsection detail per chapter so one long chapter cannot starve
        # the rest of the index, but never drop a chapter heading itself.
        max_subsections_per_chapter = 30
        for major in chapter_nums:
            sections = sec_by_major.get(major, [])
            ch_title = ch_titles.get(major)
            if ch_title and sections:
                first, _t = sections[0]
                lines.append(f"[Chapter {major}] {first} — {ch_title}")
            elif ch_title:
                lines.append(f"[Chapter {major}] — {ch_title}")
            elif sections:
                sn, title = sections[0]
                lines.append(f"[Chapter {major}] {sn} — {title}")
            else:
                continue
            for sn, title in sections[1:max_subsections_per_chapter]:
                lines.append(f"  {sn} — {title}")

        if appendix_entries:
            lines.append("")
            for label, _src, title in appendix_entries:
                lines.append(f"[Appendix {label}] — {title}")

        header = (
            "DOCUMENT STRUCTURE INDEX (enumerate ALL of the following in your answer):\n"
            + "\n".join(lines)
            + "\n\n"
        )
        return header

    _SECTION_LABEL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Chapter|Section|Appendix|Part)\s+\S+",
        re.IGNORECASE,
    )

    @staticmethod
    def _infer_section_label(chunk_text: str, chunk_role: str | None) -> str | None:
        if chunk_role not in ("heading", "toc_entry"):
            return None
        m = _StructureMixin._SECTION_LABEL_RE.search(chunk_text[:200])
        if m:
            label = m.group(0)
            after = chunk_text[m.end() :].split("\n")[0].strip().rstrip(".:-—")
            if after:
                return f"{label}: {after}"
            return label
        return None

    def _is_enumerate_chapters_query(self, query: str) -> bool:
        """Detect queries explicitly requesting chapter-by-chapter enumeration.

        Matches phrases like "summarize all 21 chapters", "chapter 1", "give me an overview of each chapter".
        Returns True when query mentions chapter numbers AND implies enumeration (not just a single chapter lookup).

        Args:
            query: User query string.

        Returns:
            True if query explicitly enumerates chapters.
        """
        q = query.lower()
        has_chapter_ref = any(p.search(q) for p in CHAPTER_ENUMERATION_PATTERNS)
        has_enum_signal = any(t in q for t in ENUMERATE_CHAPTER_SIGNALS)
        return has_chapter_ref and has_enum_signal

    _APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s+(.{2,60})",
    )
    _BARE_APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:^|\n)\s*(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s*[.:-]?\s*(.{2,80})",
        re.MULTILINE,
    )

    @staticmethod
    def _chunks_are_code_like(structure_chunks: list[dict[str, Any]]) -> bool:
        """Return True when structure-probe chunks look like source code, not prose.

        Structural chapter extraction is only meaningful for prose manuals.
        Source code — especially bundled/minified output — sets off the
        chapter/section regexes on version numbers, identifiers and SVG/data
        path fragments (e.g. ``8.5``, ``7.0.0``, ``25.8``), producing
        hallucinated chapters for documents that have none.  This gate is
        intentionally conservative: it only fires on unambiguous code signals
        (near-zero whitespace density, or pervasive code punctuation), so
        genuine prose documents are never suppressed.

        Parameters
        ----------
        structure_chunks :
            List of probe chunk dicts (each with a ``chunk_text`` key).

        Returns
        -------
        bool
            True when the sampled content is clearly code, False otherwise.
        """
        if not structure_chunks:
            return False
        text = "".join(
            (c.get("chunk_text") or "")[:4000] for c in structure_chunks[:24]
        )
        n = len(text)
        if n < 200:
            # Too little signal to classify — never suppress a prose document.
            return False

        # Signal 1: bundled / minified output has almost no whitespace at all
        # (prose has a blank between essentially every word, ~15%+ whitespace).
        whitespace = sum(1 for ch in text if ch.isspace())
        if whitespace / n < 0.05:
            return True

        # Signal 2: code punctuation density.  Braces, semicolons, and
        # operators appear constantly in source code (formatted or not) but are
        # essentially absent from prose.  Parens and quotes are excluded as
        # they occur in ordinary writing.
        code_punct = "{};=<>&|#`"
        density = sum(1 for ch in text if ch in code_punct) / n
        return density > 0.02

    @staticmethod
    def _clean_chapter_title(title: str) -> str:
        """Return a TOC chapter title with page numbers and run-on entries removed.

        Dotted ToC heads look like ``Chapter 8 The ML4T Workflow ....... 223``.
        Docling-flattened ToCs drop the dots and run consecutive entries together,
        separating them with bare page numbers only ("Title 147 Next section 148
        More"). The capture regexes therefore grab the following entries too, so
        the text is cut at the first standalone page number that precedes a
        capitalized continuation (the start of the next entry); trailing page
        numbers and run-on description sentences are then stripped, leaving the
        real chapter heading.
        """
        # NFKD + combining-mark stripping canonicalizes the docling spellings
        # of accented titles (precomposed U+00EF vs decomposed i + U+0308) so
        # both clean to the same complete string instead of being split or
        # mangled at the non-ASCII mark.
        title = "".join(
            ch
            for ch in unicodedata.normalize("NFKD", title)
            if not unicodedata.combining(ch)
        )
        title = re.sub(r"\s*\.{2,}[.\-\u2013\u2014]*", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        title = re.split(r"\s+\d{1,4}\s+(?=[A-Z(])", title)[0]
        # Flattened-ToC run-ons continue with a DOTTED SECTION number instead
        # of a capital ("... VE 10 2.1 System Requirements"): a standalone
        # printed page serial (<= 3 digits) followed by an "N.N" section
        # number is a row boundary — cut there.  Ordinary titles carrying a
        # dotted number with no preceding serial are unaffected.  The
        # docling-parse space regression can also GLUE the section number to
        # its title ("10 2.1Emulated...") so the lookahead must not demand a
        # trailing space after "N.N" — only that no further digit/dot
        # continues the number.
        title = re.split(r"\s+\d{1,3}\s+(?=\d+(?:\.\d+)+(?![\d.]))", title)[0]
        title = re.sub(r"[\s.\u2026:\-\u2013\u2014]+\d+\s*$", "", title)
        # Front-matter description sentences run the captured title on into the
        # sentence body ("Chapter 3 , Machine Learning for IoT , explores
        # supervised and unsupervised ..."); cut at the description verb so the
        # heading carries the chapter title only.
        title = _CHAPTER_DESC_TAIL_RE.sub("", title)
        return title.strip(" \t\r\n.,:;-\u2013\u2014")

    @staticmethod
    def _recovered_runon_toc_rows(
        structure_chunks: list[dict[str, Any]],
        src: str,
    ) -> dict[int, tuple[str, int]]:
        """Recover chapter (title, printed page) from run-on flattened ToC rows.

        Flattened ToCs merge consecutive rows into one body chunk ("5.14.2
        Migration Network . 134 Proxmox Cluster File System (pmxcfs) 136 6.1
        POSIX" -- chapter 6's row is stranded mid-run-on after section 5.14.2
        and BEFORE its own 6.1 subsection row).  Split each early-page chunk
        at "serial-followed-by-dotted-section" boundaries, then parse the
        boundary-tail shape: the split's LEFT segment ends with the recovered
        row's "<printed> <title>", and the RIGHT segment's leading "N.N"
        prefix names the recovered chapter (6.1 -> chapter 6).  The left
        seg's own number-prefixed run-on (5.14.2) must not be confused with
        the row: only its TAIL after the last printed serial is the row.
        """
        row_title_re = re.compile(r"^(?:Chapter\s+)?(\d{1,2})\.?\s+")
        dotted_prefix_re = re.compile(r"^(\d{1,2})\.\d+\s")
        recovered: dict[int, tuple[str, int]] = {}
        split_re = re.compile(r"\s+(\d{1,3})\s+(?=\d{1,2}\.\d+\s)")
        serial_re = re.compile(r"(?<![\d.])\d{1,3}(?![\d.])\s+")
        dot_run_re = re.compile(r"(?:\s*\.\s*){2,}")
        # Glued row shape: the docling space regression deletes the space
        # AFTER a dotted section number too ("5.14.2MigrationNetwork"), so
        # pass 1's split lookahead ("serial + SPACE + next dotted section")
        # finds no boundary and the stranded chapter row inside the run-on
        # ("... 134 6 ProxmoxClusterFileSystem(pmxcfs) 136") is lost with it.
        # Match the chapter number (not preceded by digit/dot: rejects the
        # 5 of "5.14.1..." and the 6 of "B.6 ..."), then glued title tokens
        # (capital/paren led, no digits, no whitespace inside), then a
        # trailing standalone serial (the printed page).  Section rows like
        # "5.14.1MigrationType 133" fail the shape (5 is dot-followed;
        # title would need to start right after "5.14.1" glue-free).
        glued_row_re = re.compile(
            r"(?<![\d.])(\d{1,2})\s+"
            r"([A-Z(][^\s]*(?:\s+[A-Z(][^\s]*)*)"
            r"\s+(\d{1,3})(?![\d.])"
        )
        for c in structure_chunks:
            page = int(c.get("page_number") or 0)
            if page > 30 or (c.get("source_file") or "") != src:
                continue
            text = c.get("chunk_text") or ""
            flat = re.sub(r"\s+", " ", dot_run_re.sub(" ", text)).strip()
            if not flat:
                continue
            matches = list(split_re.finditer(flat))
            if not matches:
                continue
            spans: list[tuple[str, str]] = []
            cut = 0
            for m in matches:
                spans.append((flat[cut : m.start()], m.group(1)))
                cut = m.end()
            if cut < len(flat):
                spans.append((flat[cut:], ""))
            for idx, (left, serial) in enumerate(spans):
                left = left.strip()
                right = spans[idx + 1][0] if idx + 1 < len(spans) else ""
                rm = row_title_re.match(left)
                split_valid = False
                if rm is not None:
                    ch = int(rm.group(1))
                    title_head = re.sub(r"^(?:Chapter\s+)?\d{1,2}\.?\s+", "", left)
                    # A real chapter row's title never starts with its own
                    # dotted section number ("6 5.7.3 Separate ...": the 6 is
                    # a wrapped page-column artifact of the ToC layout, and
                    # 5.7.3 is a section of chapter 5, not chapter 6's name).
                    if not re.match(r"^\d+(?:\.\d+)+\s", title_head):
                        title = _StructureMixin._clean_chapter_title(
                            re.sub(r"\s+\d{1,3}\s*$", "", title_head)
                        )
                        if (
                            len(title) >= 4
                            and 1 <= ch <= 30
                            and serial.isdigit()
                            and int(serial) > 0
                        ):
                            recovered.setdefault(ch, (title, int(serial)))
                            split_valid = True
                if split_valid:
                    continue
                # Tail shape: the chapter row is stranded mid-run-on
                # ("... 134 <Chapter-6 title>" inside a 5.14.x section run-on).
                # The title runs from after the LAST standalone serial in the
                # span to its end; the earlier serials belong to section rows.
                serials_in_left = list(serial_re.finditer(left))
                if not serials_in_left:
                    continue
                last = serials_in_left[-1]
                if last.start() == 0:
                    # A span leading with its serial ("136 6.2 File ...") is a
                    # continuation chunk boundary — no chapter row text sits
                    # in front of it; the title after it is a section name,
                    # not a chapter title.
                    continue
                title = _StructureMixin._clean_chapter_title(left[last.end() :])
                next_dotted = dotted_prefix_re.match(right.strip())
                if next_dotted is None or len(title) < 4:
                    continue
                ch = int(next_dotted.group(1))
                # The chapter's printed page is the boundary serial the
                # splitter consumed; the serial inside the tail (134 above)
                # belongs to the previous section's row.
                printed = int(serial) if serial.isdigit() else 0
                if not (1 <= ch <= 30) or printed <= 0:
                    continue
                recovered.setdefault(ch, (title, printed))
        # Pass 2: glued-shape scan over the SAME early-page chunks, in a
        # separate loop so it runs even where pass 1's splitter found no
        # boundary (the gate above `continue`s those chunks): the docling
        # space regression deleted the space AFTER the dotted section
        # number ("5.14.2MigrationNetwork"), so pass 1's split lookahead
        # never fires on this book and only this pass can rescue the
        # stranded row.  Merging still uses setdefault, and this loop runs
        # after pass 1 has walked every chunk, so spaced pass-1 rows win
        # over glued duplicates regardless of chunk order.
        for c in structure_chunks:
            page = int(c.get("page_number") or 0)
            if page > 30 or (c.get("source_file") or "") != src:
                continue
            flat = re.sub(
                r"\s+", " ", dot_run_re.sub(" ", c.get("chunk_text") or "")
            ).strip()
            if not flat:
                continue
            for gm in glued_row_re.finditer(flat):
                ch = int(gm.group(1))
                raw_title = re.sub(r"\s+", " ", gm.group(2)).strip()
                printed = int(gm.group(3))
                # Glue evidence: a real glued title shows either several
                # tokens or an intra-word case/paren boundary.  A single
                # unbroken capitalized word ("6 Other 8", "6 Covers 12") is
                # prose noise, not a space-regression casualty — gluing can
                # only delete spaces, so one-word titles are never victims.
                tokens_ = raw_title.split(" ")
                boundary_ = re.search(r"(?<=[a-z])[A-Z(]", raw_title)
                if not (len(tokens_) > 1 or boundary_):
                    continue
                title = _StructureMixin._clean_chapter_title(raw_title)
                if len(title) >= 4 and 1 <= ch <= 30 and printed > 0 and printed <= 999:
                    recovered.setdefault(ch, (title, printed))
        return recovered

    @staticmethod
    def _pretty_glued_title(title: str) -> str:
        """Re-space a fully-glued chapter title for display only.

        The docling-parse space regression deletes intra-title spaces in the
        stored ToC/roster rows ("ProxmoxClusterFileSystem(pmxcfs)").  When no
        spaced spelling of the title survives anywhere in the document
        (backfill and run-on recovery both need one), this is the last resort
        so the roster shows "Proxmox Cluster File System (pmxcfs)" instead of
        the glued wall.  Conservative by construction: it fires ONLY when the
        title contains no whitespace at all AND is at least 10 chars — short
        mixed-case words ("macOS", "pmxcfs") and every normally-spaced title
        pass through untouched — and it only splits at lower→upper CamelCase
        boundaries plus before "(" after a lowercase letter, so all-caps runs
        and lowercase words are never broken.  Display only: matching and
        comparison paths keep the raw stored form.  The true fix is re-ingest
        with a docling build that does not glue; this only repairs what is
        shown.
        """
        t = title.strip()
        if len(t) < 10 or re.search(r"\s", t):
            return t
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
        spaced = re.sub(r"(?<=[a-z])\(", " (", spaced)
        return spaced

    @staticmethod
    def _display_chapter_title(title: str) -> str:
        """Return the trimmed single-line title for display in rosters/headers.

        The last consumer-side cleanup against polluted roster captures: cuts
        run-on ToC artifacts (embedded printed-page serials, next-row text)
        after every capture-side filter has been applied.  Kept on the mixin
        so the roster builder and the answer header builder share one
        implementation.  A fully-glued title with no spaced form anywhere in
        the document gets a display-only re-spacing here (see
        :meth:`_pretty_glued_title`).
        """
        title = title.strip()
        if not title:
            return ""
        title = _StructureMixin._pretty_glued_title(title)
        dot = title.find(". ")
        if 10 < dot < 150:
            title = title[:dot]
        dup = re.search(r"\s+\d{1,2}\s+", title[5:])
        if dup:
            title = title[: 5 + dup.start()].strip()
        if len(title) > 100:
            title = title[:100].rsplit(" ", 1)[0]
        return title.strip()

    @staticmethod
    def _is_boilerplate_caption(title: str) -> bool:
        """Return True for license captions shaped like chapter titles.

        Numbered all-caps GFDL sections ("6. COLLECTIONS OF DOCUMENTS") match
        the bare-number roster patterns yet name legal boilerplate, not a
        chapter.  The gate needs BOTH an all-caps body (real chapter titles
        are Title Case) and a known license-section token, so ordinary
        all-caps headings ("WHAT IS NEW") are unaffected.
        """
        if not re.search(r"\d{1,2}[.)]?\s+\S", title[:6]):
            return False
        if not re.search(r"[A-Z]{4,}", title):
            return False
        return bool(_BOILERPLATE_CAPTION_RE.search(title))

    @staticmethod
    def _boilerplate_pages(structure_chunks: list[Any]) -> set[int]:
        """Pages inside license/colophon regions, from license opener headings.

        Scans structural chunks for GNU/MIT/Apache-style license headings and
        collects every numbered all-caps section heading at or below the
        earliest opener page.  Two passes keep the result independent of the
        (unordered) storage iteration order: openers are found first, then
        candidate captions are intersected with the license span.
        """
        openers: list[int] = []
        caps_pages: set[int] = set()
        for c in structure_chunks:
            page = int(c.get("page_number") or 0)
            text = c.get("chunk_text") or ""
            first_line = text.split("\n")[0].strip()
            role = c.get("chunk_role") or c.get("element_type") or ""
            if _BOILERPLATE_TITLE_RE.match(first_line):
                openers.append(page)
                continue
            if "heading" in str(role) and re.match(
                r"^\d{1,2}[.)]\s+[A-Z][A-Z\s,'()-]+$", first_line
            ):
                caps_pages.add(page)
        if not openers:
            return set()
        floor = min(openers)
        return {p for p in caps_pages if p >= floor} | set(openers)

    @staticmethod
    def _front_matter_desc_pages(structure_chunks: list[Any]) -> dict[int, int]:
        """Map chapter number -> page of its front-matter description sentence.

        Books extracted without heading/toc_entry roles still carry per-chapter
        prose descriptions in the front matter ("Chapter 9 , AI Cloud Platforms
        for IoT , introduces ...").  Those sentences used to serve as page
        anchors for the very chapters they describe, pinning them to the
        front-matter page instead of their real start.  Callers use the result
        to refuse anchoring a chapter on its description page.
        """
        desc_pages: dict[int, int] = {}
        for c in structure_chunks:
            page = int(c.get("page_number") or 0)
            text = c.get("chunk_text") or ""
            for m in _CHAPTER_DESC_RE.finditer(text):
                desc_pages.setdefault(int(m.group(1)), page)
        return desc_pages

    @staticmethod
    def _toc_chapter_listings(
        structure_chunks: list[Any],
    ) -> tuple[dict[int, tuple[str, int]], set[int]]:
        """Parse front-matter ToC listing rows into chapter -> (title, page).

        Returns (listings, mentions).  Chapter rows arrive in the two shapes
        the module ToC regexes describe; a "Chapter N :.-" row whose trailing
        page number was lost in extraction is collected separately as an
        ambiguous mention so the reconciliation tier can keep (never kill)
        its chapter.
        """
        listings: dict[int, tuple[str, int]] = {}
        mentions: set[int] = set()
        for c in structure_chunks:
            text = c.get("chunk_text") or ""
            for line in text.split("\n"):
                m = _TOC_LISTING_LINE_RE.match(line)
                if m:
                    listings.setdefault(
                        int(m.group(1)), (m.group(2).strip(), int(m.group(3)))
                    )
                    continue
                entry = _TOC_CHAPTER_ENTRY_RE.search(line)
                if entry:
                    listings.setdefault(
                        int(entry.group(1)),
                        (entry.group(2).strip(), int(entry.group(3))),
                    )
                mention = _TOC_CHAPTER_MENTION_RE.search(line)
                if mention:
                    mentions.add(int(mention.group(1)))
        return listings, mentions

    @staticmethod
    def _toc_listing_pages(
        structure_chunks: list[Any],
        desc_pages: dict[int, int],
        roster: set[int],
    ) -> tuple[dict[int, tuple[str, int]], set[int]]:
        """Gate the ToC parse to the region and coverage the tier trusts.

        Only chunks strictly below the earliest chapter-description page are
        parsed: that front-matter span is where the printed ToC lives, and
        the description pages mark where the book's prose begins.  With no
        description evidence, or when the parse lists fewer than
        ``_TOC_MIN_COVERAGE`` of the roster chapters, the tier is disabled
        and both results come back empty so neither a pin nor a phantom kill
        can act.
        """
        if not desc_pages or not roster:
            return {}, set()
        cap = min(desc_pages.values())
        region = [c for c in structure_chunks if int(c.get("page_number") or 0) < cap]
        if not region:
            return {}, set()
        listings, mentions = _StructureMixin._toc_chapter_listings(region)
        matched = sum(1 for ch in roster if ch in listings)
        if matched / len(roster) < _TOC_MIN_COVERAGE:
            return {}, set()
        return listings, mentions

    @staticmethod
    def _detect_chapter_openings(body_chunks: list[Any]) -> dict[int, int]:
        """Map chapter numbers to their start page from body-opening headers.

        Some books (e.g. ML4T) tag chapter openings as *body* chunks in a
        magazine style -- a ``[ 591 ]`` printed-page marker, then a bare chapter
        number line, then a capitalized title -- so they are invisible to the
        heading/TOC structure probe.  This scans body chunks for those openings
        to fill in every real chapter boundary, so each chapter's page range is
        bounded by the next chapter's start and the next chapter's content
        cannot leak into the previous chapter's bucket.
        """
        marker = re.compile(r"^\[\s*\d{1,4}\s*\]\s*\r?\n?")
        dot_leader = re.compile(r"\.{2,}")
        page_suffix = re.compile(r"\d+\s*$")
        starts: dict[int, int] = {}
        for c in body_chunks:
            page = int(c.get("page_number", 0) or 0)
            if page < 20:  # front matter / TOC
                continue
            text = (c.get("chunk_text") or "").lstrip()
            m = marker.match(text)
            if m:
                text = text[m.end() :].lstrip()
            head = text.split("\n")[0].strip()
            if not (head.isdigit() and 1 <= int(head) <= 30):
                continue
            for ln in text.split("\n")[1:3]:
                t = ln.strip()
                if len(t) < 4 or not re.match(r"^[A-Z]", t):
                    continue
                if dot_leader.search(t) or page_suffix.search(t.rstrip()):
                    break
                starts.setdefault(int(head), page)
                break
        return starts

    def _derive_chapter_numbers(
        self, structure_chunks: list[dict[str, Any]]
    ) -> tuple[list[tuple[int, str, str]], set[int], list[tuple[str, str, str]]]:
        """Return reliable chapter and appendix entries from structure chunks.

        Returns (entries, chapter_level_nums, appendix_entries) where
        chapter_level_nums are chapter numbers from CHAPTER_N_RE/BARE_CHAPTER_RE
        (reliable titles) and appendix_entries are (appendix_label, source, title).
        """
        import re

        if self._chunks_are_code_like(structure_chunks):
            # Code files (bundled JS, source, etc.) have no prose chapter
            # structure — the regexes below would just hallucinate chapters
            # from version numbers and identifiers.  Suppress entirely so the
            # pipeline falls through to generic search.
            return [], set(), []

        entries: list[tuple[int, str, str]] = []
        appendix_entries: list[tuple[str, str, str]] = []
        seen: set[tuple[int, str]] = set()
        seen_appendix: set[tuple[str, str]] = set()
        gated_nums: set[tuple[int, str]] = set()
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        chapter_n_re = re.compile(
            r"(?:Chapter\s+(\d+)\s*[:\-]?\s*|(?:Module|Lesson)\s+(\d+)\s*[:\-]\s*)"
            r"((?:(?!\.{2,})(?!\s+\d{1,4}\s*[\r\n])(?!\n\s*(?:\n|(?:Chapter|Module|Lesson|Appendix)\s+\d+))"
            r"[A-Za-z0-9 ,'\-():/+\s.\u2013\u2014]){2,120})",
            re.IGNORECASE,
        )
        # The title class includes straight and typographic double quotes so
        # quoted phrases inside a heading survive capture whole ("2 First
        # Principles: What "Well-Defined" Actually Means" used to truncate at
        # the quote, rosters reading "First Principles: What").  Display-only:
        # no pin logic reads quotes (add-anthology-aware-chapter-
        # summarization rider).
        bare_chapter_re = re.compile(
            r"(?:^|\n)\s*(\d{1,2})\.?\s+([A-Za-z0-9]"
            r"[A-Za-z0-9\s\-\(\),'/:.\u2013\u2014\"\u201c\u201d]{4,80})",
            re.MULTILINE,
        )
        # Patterns for appendix detection
        appendix_n_re = self._APPENDIX_RE
        bare_appendix_re = self._BARE_APPENDIX_RE
        seen_sec: set[int] = set()
        sec_limit = 0

        # Pass 1: CHAPTER_N_RE + APPENDIX_N_RE (most reliable patterns)
        desc_titles: dict[tuple[int, str], str] = {}
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            for dm in _CHAPTER_DESC_RE.finditer(raw):
                dch = int(dm.group(1))
                dtitle = self._clean_chapter_title(
                    re.sub(r"^Chapter\s+\d+\s*,\s*", "", dm.group(0))
                )
                if len(dtitle) >= 4 and (dch, source) not in desc_titles:
                    desc_titles[(dch, source)] = dtitle
            for nm in chapter_n_re.finditer(raw):
                major = int(nm.group(1) or nm.group(2))
                if major < 1 or major > 30 or (major, source) in seen:
                    continue
                title = self._clean_chapter_title(nm.group(3))
                if len(title) < 2:
                    continue
                # Mid-sentence cross-references ("discussed in Chapter 12 of
                # Doing Bayesian Data Analysis by Kruschke") capture a
                # lowercase run-on as the title; real headings never start
                # lowercase.
                if title[0].islower():
                    continue
                fw = title.lower().split()[0] if title.split() else ""
                if fw in (
                    "contents",
                    "copyright",
                    "licensed",
                    "license",
                    "trolltech",
                    "red",
                    "bootstrap",
                    "of",
                    "and",
                    "in",
                    "by",
                    "from",
                    "with",
                    "for",
                    "to",
                ):
                    continue
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    continue
                seen.add((major, source))
                entries.append((major, source, title))
            for am in appendix_n_re.finditer(raw):
                label = am.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = self._clean_chapter_title(am.group(2))
                if len(title) < 2:
                    continue
                # Skip false positives: mid-sentence references like
                # "Appendix A of the Specification" (title starts with
                # a preposition/article/conjunction, not a heading).
                _fpa = title.lower().split()[0] if title.split() else ""
                if _fpa in (
                    "of",
                    "to",
                    "in",
                    "for",
                    "the",
                    "and",
                    "or",
                    "by",
                    "with",
                    "from",
                    "at",
                    "on",
                    "is",
                    "are",
                    "its",
                    "this",
                    "that",
                    "was",
                    "were",
                    "been",
                ):
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

        # Rescue roster titles captured from preface cross-references:
        # "(covered in Chapter 10). My goal is …" captures "). My goal is …"
        # as the title — garbage that can never match a heading.  The
        # verb-gated description sentence carries the real title, so swap
        # it in when the roster title starts with punctuation.
        for i, (major, source, title) in enumerate(entries):
            rescued = desc_titles.get((major, source))
            if rescued and title and not title[0].isalnum():
                entries[i] = (major, source, rescued)

        # Authoritative "Chapter N" headings (from chapter_n_re in pass 1) define
        # the true chapter span.  When present, bare-number and section matches
        # may corroborate within that span but must not invent chapters beyond
        # it — otherwise noisy body text (e.g. "12 Selection and Assignment" or
        # dataframe dumps) fabricates chapters for books whose chapters are all
        # explicitly labeled "Chapter N".
        auth_max = max((e[0] for e in entries), default=0)

        # Pass 2: bare_chapter_re + bare_appendix_re
        ft_catch = re.compile(
            r"\d+\s+(\d{1,2})\s+([A-Za-z][A-Za-z0-9\s\-\(\),'/:.\u2013\u2014]{4,80})"
        )
        legal_starts = {
            "contents",
            "copyright",
            "licensed",
            "license",
            "trolltech",
            "red",
            "bootstrap",
            "a",
            "an",
            "the",
            "you",
            "your",
            "this",
            "each",
            "by",
            "if",
            "as",
            "subject",
            "whereas",
            "notwithstanding",
            "accepting",
            "submission",
            "disclaimer",
            "disclaimers",
            "limitation",
            "at",  # "15 At least moderately important"
            # Report / white-paper false-positive starters — these
            # first words appear in non-chapter section headings
            # (e.g. "8 Key findings", "22 Question:") and would
            # otherwise be hallucinated as chapter numbers.
            "key",
            "question",
            "questions",
            "figure",
            "table",
        }
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()

            for bm in bare_chapter_re.finditer(raw):
                major = int(bm.group(1))
                if (
                    major < 1
                    or major > 30
                    or (auth_max > 0 and major > auth_max)
                    or (major, source) in seen
                ):
                    continue
                title = self._clean_chapter_title(bm.group(2))
                if len(title) < 4:
                    continue
                fw = (title.lower().split()[0] if title.split() else "").rstrip(":;,.")
                if fw in legal_starts:
                    continue
                if title[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title, re.IGNORECASE):
                    continue
                if self._is_boilerplate_caption(f"{major}. {title}"):
                    gated_nums.add((major, source))
                    continue
                seen.add((major, source))
                entries.append((major, source, title))

            for bam in bare_appendix_re.finditer(raw):
                label = bam.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = self._clean_chapter_title(bam.group(2))
                if len(title) < 4:
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

            for fm in ft_catch.finditer(raw):
                major_ft = int(fm.group(1))
                if (
                    major_ft < 1
                    or major_ft > 30
                    or (auth_max > 0 and major_ft > auth_max)
                    or (major_ft, source) in seen
                ):
                    continue
                title_ft = self._clean_chapter_title(fm.group(2))
                if len(title_ft) < 6:
                    continue
                fw_ft = (
                    title_ft.lower().split()[0] if title_ft.split() else ""
                ).rstrip(":;,.")
                if fw_ft in legal_starts:
                    continue
                if title_ft[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title_ft, re.IGNORECASE):
                    continue
                if self._is_boilerplate_caption(f"{major_ft}. {title_ft}"):
                    gated_nums.add((major_ft, source))
                    continue
                seen.add((major_ft, source))
                entries.append((major_ft, source, title_ft))

            seen_max = max([s[0] for s in seen], default=0)
            sec_limit = seen_max + 3 if seen_max > 0 else 999
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if (
                    major < 1
                    or major > 30
                    or major in seen_sec
                    or (major, source) in seen
                    or (seen_max > 0 and major > sec_limit)
                ):
                    continue
                raw_title = (m.group(3) or "").strip()
                clean_title = raw_title.rstrip(".")
                if len(clean_title) < 2:
                    continue
                fw = clean_title.lower().split()[0] if clean_title.split() else ""
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    clean_title = ""
                seen_sec.add(major)

        # Phase 3: chunk-boundary recovery for chapters
        if entries:
            found_nums = {e[0] for e in entries}
            all_seen = {s[0] for s in seen}
            lo = min(found_nums)
            hi = max(found_nums)
            for gap_n in range(lo + 1, hi):
                if gap_n in all_seen:
                    continue
                for i in range(len(structure_chunks) - 1):
                    cur = structure_chunks[i]
                    nxt = structure_chunks[i + 1]
                    cur_text = cur.get("chunk_text", "")
                    src_cur = cur.get("source_file", "")
                    if (
                        f"Chapter {gap_n}" not in cur_text
                        and f"chapter {gap_n}" not in cur_text
                    ):
                        continue
                    idx = cur_text.lower().find(f"chapter {gap_n}")
                    remaining = len(cur_text) - idx
                    if remaining > 80 or (gap_n, src_cur) in seen:
                        continue
                    nxt_text = nxt.get("chunk_text", "").strip()
                    first_line = nxt_text.split("\n")[0].strip()
                    if (
                        len(first_line) >= 4
                        and first_line[0].isupper()
                        and not first_line[0].islower()
                        and not re.search(r"^\d+\.\d+", first_line)
                    ):
                        title = re.sub(r"\s*\d+\s*$", "", first_line).rstrip(".")
                        seen.add((gap_n, src_cur))
                        entries.append((gap_n, src_cur, title))

        entries.sort(key=lambda x: x[0])
        appendix_entries.sort(key=lambda x: x[0])

        # Gated license captions yield no roster entry; if one sits INSIDE the
        # detected chapter span it leaves a numbering hole that the
        # consecutive-run trim below would resolve by dropping the SHORTER
        # side (PVE: a gated ch6 would discard chapters 1-5).  Re-add those
        # interior numbers as title-less placeholders — they keep the span
        # gapless and give Phase-3 interpolation a slot — while captions
        # numbered beyond the real span (GFDL "10. FUTURE REVISIONS" in a
        # 9-chapter book) produce no phantom chapter.
        if gated_nums and entries:
            real_nums = {e[0] for e in entries if e[2]}
            if real_nums:
                span_lo, span_hi = min(real_nums), max(real_nums)
                for g_num, g_src in sorted(gated_nums):
                    if span_lo < g_num < span_hi and not any(
                        e[0] == g_num and e[1] == g_src for e in entries
                    ):
                        seen.add((g_num, g_src))
                        entries.append((g_num, g_src, ""))

        # Post-validation: drop outlier chapters that are likely false
        # positives from over-eager pass-2 regex patterns (bare_chapter_re,
        # ft_catch).  Find the longest consecutive run of chapter numbers;
        # if it accounts for >= 60 % of detected chapters AND there are
        # at least 5 total entries (too few data points makes the ratio
        # unreliable), exclude chapters outside that run.
        if len(entries) >= 5:
            all_nums = sorted({e[0] for e in entries})
            runs: list[list[int]] = [[all_nums[0]]]
            for n in all_nums[1:]:
                if n == runs[-1][-1] + 1:
                    runs[-1].append(n)
                else:
                    runs.append([n])
            main_run = max(runs, key=len)
            if len(main_run) / len(all_nums) >= 0.60:
                main_set = set(main_run)
                entries = [e for e in entries if e[0] in main_set]
                seen = {(n, s) for (n, s) in seen if n in main_set}

        # LLM fallback: classify unmatched appendix candidates
        if not appendix_entries and self._llm_provider is not None:
            llm_candidates: list[str] = []
            llm_sources: list[str] = []
            seen_keywords: set[str] = {str(e[0]) for e in entries}
            seen_keywords.update(al[0] for al in appendix_entries)
            for chunk in structure_chunks:
                raw = chunk.get("chunk_text", "").strip()
                src = chunk.get("source_file", "")
                first_line = raw.split("\n")[0].strip()
                if not first_line or len(first_line) > 120:
                    continue
                first_word = first_line.split()[0].lower() if first_line.split() else ""
                if first_word in seen_keywords:
                    continue
                if not any(
                    k in first_line.lower()
                    for k in ("appendix", "annex", "supplement", "supplementary")
                ):
                    continue
                candidate = first_line[:120]
                llm_candidates.append(candidate)
                llm_sources.append(src)

            if llm_candidates:
                candidates_prompt = (
                    "Classify each of the following document headings. "
                    "If it is an appendix, respond with APPENDIX:<label> on its own line, "
                    "where label is a single letter like A, B, C. "
                    "If it is a chapter heading, respond with CHAPTER. "
                    "If neither, respond with NONE. "
                    "One response per line, in order.\n\n"
                    + "\n".join(
                        f"{i + 1}. {c}" for i, c in enumerate(llm_candidates[:5])
                    )
                )
                try:
                    llm_reply = self._llm_provider.generate(
                        prompt=candidates_prompt,
                        temperature=0.1,
                        max_tokens=200,
                    )
                    for i, line in enumerate(llm_reply.strip().split("\n")):
                        line = line.strip()
                        if i >= len(llm_candidates):
                            break
                        if line.startswith("APPENDIX:"):
                            label = line.split(":", 1)[1].strip().upper()
                            if label and len(label) == 1 and label.isalpha():
                                candidate_text = llm_candidates[i]
                                parts = candidate_text.split(None, 2)
                                title = parts[-1] if len(parts) > 1 else candidate_text
                                title = title.rstrip(".:-")
                                key = (label, llm_sources[i])
                                if key not in seen_appendix:
                                    seen_appendix.add(key)
                                    appendix_entries.append(
                                        (label, llm_sources[i], title)
                                    )
                except Exception:
                    logger.debug("LLM appendix fallback failed", exc_info=True)

        return entries, {s[0] for s in seen}, appendix_entries

    def _is_broad_coverage_query(self, query: str) -> bool:
        q = query.lower().strip()
        return any(t in q for t in BROAD_COVERAGE_TRIGGERS)

    def _probe_document_structure(
        self,
        top_k: int = 10000,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Probe for document structural elements (TOC/section headers) via chunk_role.

        Attempts targeted structural-role filters first; falls back to raw
        top-K retrieval when few candidates are found (handles documents whose
        chunks lack explicit element_type/chunk_role markers).

        Args:
            top_k: How many structural candidates to retrieve (default 10000).
            source_filter: Optional source_file filter to scope to one document.

        Returns:
            List of chunk dicts with 'chunk_text', 'page_number',
            'source_file', 'chunk_id'.
        """
        # Structural roles that signal TOC/section/heading content.  The Qdrant
        # OR-filter matches a chunk when its element_type OR chunk_role is one of
        # these — identical to the former legacy "$or" filter query.
        element_types = [
            "heading",
            "toc_entry",
            "body",
            "paragraph",
            "title",
            "section",
            "header",
        ]
        chunk_roles = [
            "body",
            "caption",
            "navigation",
            "heading",
            "toc_entry",
            "title",
            "section",
            "header",
        ]
        storage = self._searcher.storage
        try:
            result = list(
                storage.find_structural_chunks(
                    element_types=element_types,
                    chunk_roles=chunk_roles,
                    source_prefix=source_filter,
                    limit=10000,
                )
            )
            if len(result) < 5:
                # Fall back to ALL chunks for the source (or all chunks when no
                # source_filter given), ordered by page and limited to top_k —
                # preserves the former legacy fallback query.
                result = list(
                    storage.find_structural_chunks(
                        source_prefix=source_filter,
                        limit=top_k,
                    )
                )
        except Exception:  # storage unavailable → no structure to probe
            logger.debug("Structure probing failed", exc_info=True)
            return []
        return [dict(c) for c in result]

    def _generic_one_shot(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        """Fallback one-shot retrieval when document structure probing fails."""
        # Scoped retrieval embeds the name-stripped query (path tokens pollute
        # the embedding); prompts/results/fallbacks keep the original query.
        search_query = self._scoped_search_query(query) if source_filter else query
        chunks = self._searcher.search(
            search_query,
            top_k=top_k,
            source_filter=source_filter,
        )
        if not self._has_relevant_chunks(
            chunks, threshold=self._relevance_gate_threshold(source_filter)
        ):
            return {"answer": self._handle_no_results(query), "query": query}
        chunks = self._union_opener_chunks(query, chunks, source_filter, top_k=top_k)
        chunks = self._apply_heading_diversity(chunks)
        context = self._format_context(chunks)
        prompt = self._build_prompt(query, context)

        # Summary overviews reproduce figures exactly: reinforce it calmly (one
        # figure, then move on -- the anti-spiral phrasing), then vet below.
        intent = self._intent_parser.parse(query).intent
        is_summary = intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
        )
        if is_summary:
            prompt += (
                "\n\nYou are summarizing source material. Quote figures (percentages, "
                "counts, years, metrics, returns) EXACTLY as stated in the retrieved "
                "context; never invent, estimate, round, or 'correct' a value the "
                "source does not state. This rule applies to prose statistics only -- "
                "do not fixate on reproducing code details or function arguments "
                "(e.g. list(range(...))) verbatim. State each figure once, "
                "confidently, and move on."
            )

        # Summary queries generate non-streaming, are vetted (grounded, and a
        # spiral/fallback/leak regenerated deterministically), then emitted once --
        # so raw drafting is never shown and a reasoning spiral can never surface
        # in the terminal. Other queries keep live streaming.
        if is_summary:
            answer = self._vet_answer(self._generate(prompt), prompt, context)
            if self._on_chunk and answer:
                self._on_chunk(answer, None)
        else:
            answer, streamed = self._stream_generate(prompt)
            if not streamed and self._on_chunk and answer:
                self._on_chunk(answer, None)
            answer = self._vet_answer(answer, prompt, context)

        result: dict[str, Any] = {"answer": answer, "query": query}
        if show_sources:
            result["sources"] = chunks
        return result

    def _vet_answer(self, text: str, prompt: str, context: str) -> str:
        """Ground figures to the source and regenerate deterministically if broken.

        Drops figures the source never stated, and when the text is empty, is the
        reasoning-budget fallback (the model spiraled before writing content), or
        leaks chain-of-thought self-talk, re-generates at low temperature for a
        clean, deterministic result instead of shipping a dead end.
        """
        answer = _prune_implausible_metric_figures(text)
        answer = _ground_figures(answer, context)
        if (
            not answer.strip()
            or answer.strip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX)
            or _contains_reasoning_leak(answer.lower())
        ):
            clean = self._generate_guarded(prompt, temperature=0.1)
            if clean:
                answer = _ground_figures(
                    _prune_implausible_metric_figures(clean), context
                )
        # A spiral that even the low-temperature retry could not recover is a dead
        # end -- return empty so callers fall back to a useful default (e.g. the
        # chapter roster) instead of surfacing the "I got stuck" fallback.
        if answer.strip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX):
            return ""
        return answer

    @staticmethod
    def _heading_title_anchors(
        chapters: list[tuple[int, str, str]],
        src: str,
        heading_chunks: list[dict[str, Any]],
        blocked_pages: dict[int, int] | None = None,
        boiler_pages: set[int] | None = None,
        titles_out: dict[int, str] | None = None,
    ) -> dict[int, int]:
        """Map chapter numbers to opener pages via heading-role title matches.

        Labeled docling output drops the "Chapter N" banner text and strips
        section numbers from headings, but keeps each chapter's title as a
        heading chunk on its real opening page — while ToC/covers pages stay
        body-role. Matching each detected chapter title (cut at embedded ToC
        page numbers, e.g. "Title 147 How ma") against heading chunks
        therefore anchors chapters on their true openers even when every
        "Chapter N"/section-number scan fails. Comparison normalizes the
        subtitle separators docling is inconsistent about (" - " vs " ") and
        allows a leading chapter-number prefix on the heading ("5 Title").
        It is also whitespace-insensitive: the needle and the heading line
        are each squashed (all whitespace removed) before comparing, because
        the docling-parse space regression glues ToC words together
        ("InstallingProxmoxVE" in the roster) while the same title sits
        correctly spaced on the real opener page ("Installing Proxmox VE") —
        exact spacing would never match the two forms. Glued ToC-row text
        compared against a glued needle still matches, and a spaced needle
        against glued heading text matches in the reverse direction, so both
        corrupted spellings anchor. Heading chunks arrive page-ordered, so
        the first match per chapter is the earliest page; pages < 10 (front
        matter) never anchor. Two listing-artifact refusals keep the
        earliest match honest: headings ending in a standalone page reference
        ("Title 295") are ToC entries, not openers, and `blocked_pages`
        (chapter -> front-matter description page) skips "What this book
        covers" prose pages. When the blocked pages sit in the front matter
        (min <= 30), everything before them is ToC/part-divider region —
        part dividers repeat chapter titles as headings on ToC pages — so
        anchoring also refuses those pages. ``boiler_pages`` refuses
        license/colophon regions: their numbered all-caps section headings
        can match a roster title that was itself seeded by the same license
        text. When a heading matches, the spaced opener-page spelling of the
        title is recorded into ``titles_out[ch_num]`` (raw first line,
        whitespace-normalized, before casefold/prefix stripping) so the
        caller can repair glued roster titles for display.

        A squashed-PREFIX match (heading extends the title) is additionally
        token-checked (:meth:`_heading_tokens_admit_suffix`): every title
        token must appear as a whole token in the heading with at most a
        two-token slack, so "REFERENCES" cannot anchor "Reference" and
        "Change logs are also available at:" cannot anchor "Change Log",
        while genuine extensions ("...Release 7.2" for "…Release 7") and
        subtitle continuations still anchor. Exact squashed matches (the
        glued/spaced corruption paths) are exempt by construction. When the
        title's trailing token is page-serial-shaped, the walk runs against
        the un-truncated spelling whenever the heading extends past it, so a
        version title ("Release 7") keeps its own token for the dot-segment
        rule instead of being truncated to "Release".
        """
        anchors: dict[int, int] = {}
        blocked_map = blocked_pages or {}
        boiler_map = boiler_pages or set()
        floor = min(blocked_map.values()) if blocked_map else None
        if floor is not None and floor > 30:
            floor = None
        for ch_num, ch_src, title in chapters:
            if ch_src != src:
                continue
            # The listing-cleanup strips are ordered so the full (un-truncated)
            # spelling survives: ``full_tt`` only cuts embedded "Title 147 How
            # ma" artifacts, while ``tt`` additionally drops a trailing page
            # serial.  A trailing token can also be a version number
            # ("Networking Release 7"), so the token walk below runs against
            # ``full_tt`` whenever the heading extends past it — admitting the
            # dot-segment extension ("…Release 7.2") while refusing longer
            # continuations ("…Release 7.2 subnets") that the truncated
            # needle would wrongly admit with two-token slack.
            full_tt = re.split(r"\s+\d{1,4}\s+", title)[0]
            tt = re.sub(r"\s+\d{1,4}\s*$", "", full_tt)
            needle = (
                re.sub(r"\s+", " ", re.sub(r"[-\u2013\u2014:]", " ", tt))
                .strip()
                .casefold()
            )
            if len(needle) < 4:
                continue
            needle_sq = re.sub(r"\s+", "", needle)
            full_needle = (
                re.sub(r"\s+", " ", re.sub(r"[-\u2013\u2014:]", " ", full_tt))
                .strip()
                .casefold()
            )
            full_needle_sq = re.sub(r"\s+", "", full_needle)
            blocked = blocked_map.get(ch_num)
            for hc in heading_chunks:
                page = int(hc.get("page_number") or 0)
                if (
                    page < 10
                    or page == blocked
                    or (floor and page < floor)
                    or page in boiler_map
                ):
                    continue
                head_line = re.sub(
                    r"[-\u2013\u2014:]",
                    " ",
                    (hc.get("chunk_text") or "").split("\n")[0],
                )
                if _BOILERPLATE_CAPTION_RE.search(head_line):
                    continue
                head_line = re.sub(r"\s+", " ", head_line).strip().casefold()
                if re.search(r"\s+\d{1,4}$", head_line):
                    continue
                # The docling-parse space regression also glues the
                # "Chapter N" banner and section-number prefixes to the
                # title ("Chapter4 Installing..."), so the space before the
                # number is optional in the strip patterns.
                head_line = re.sub(
                    r"^(?:chapter\s*\d+[\s:.\-]*)?(?:\d+[\s.:\-]+)?", "", head_line
                )
                head_sq = re.sub(r"\s+", "", head_line)
                if full_needle_sq != needle_sq and head_sq.startswith(full_needle_sq):
                    # Heading carries the title's own trailing token: walk the
                    # un-truncated title (version semantics, see above).
                    walk_needle = full_needle
                elif head_sq.startswith(needle_sq):
                    walk_needle = needle
                else:
                    walk_needle = None
                if head_sq in (needle_sq, full_needle_sq) or (
                    walk_needle is not None
                    and _StructureMixin._heading_tokens_admit_suffix(
                        head_line, walk_needle
                    )
                ):
                    anchors[ch_num] = page
                    if titles_out is not None:
                        # Record the opener page's own spelling (spaced when
                        # the page is intact) for roster-title backfill: raw
                        # first line, before casefold/prefix strip, with
                        # line breaks and padding collapsed to single spaces.
                        titles_out[ch_num] = re.sub(
                            r"\s+", " ", (hc.get("chunk_text") or "").split("\n")[0]
                        ).strip()
                    break
        return anchors

    @staticmethod
    def _heading_tokens_admit_suffix(
        head_line: str, needle: str, max_extra: int = 2
    ) -> bool:
        """Token-level admission for a squashed-prefix heading match.

        The squashed comparison (``head_sq.startswith(needle_sq)``) cannot
        tell a genuine extension ("…Release 7.2" for roster "…Release 7")
        from a sub-word accident ("REFERENCES" for "Reference").  Both
        sides walk their whitespace tokens as one squashed character
        stream — so the docling space regression's glued spellings match
        their spaced forms in either direction — and the walk must END on
        a token boundary of the heading: after the last needle character,
        the heading may keep at most ``max_extra`` whole tokens (bounded
        slack for version suffixes and short subtitle continuations).
        Ending mid-heading-token is admitted only at a dot-segment
        boundary of a version-shaped token pair ("7" ≈ "7.2"), so
        "reference" never matches "references".

        Parameters
        ----------
        head_line:
            Case-folded heading text (whitespace already normalized).
        needle:
            Case-folded roster title to admit.
        max_extra:
            Maximum number of heading tokens beyond the match.

        Returns
        -------
        bool
            True when the heading's token sequence admits the title.
        """
        head_tokens = head_line.split()
        needle_tokens = needle.split()
        if not needle_tokens or not head_tokens:
            return False
        if len(head_tokens) - len(needle_tokens) > max_extra:
            return False
        hi = 0
        ho = 0
        for tok in needle_tokens:
            for ch in tok:
                if hi >= len(head_tokens):
                    # Needle text outruns the heading: the squash-prefix
                    # pre-check above should have refused this already.
                    return False
                head_tok = head_tokens[hi]
                if ho >= len(head_tok):
                    hi += 1
                    ho = 0
                    if hi >= len(head_tokens):
                        return False
                    head_tok = head_tokens[hi]
                if head_tok[ho] != ch:
                    return False
                ho += 1
                if ho == len(head_tok):
                    hi += 1
                    ho = 0
        if hi < len(head_tokens) and ho > 0:
            # Ended mid-token: only a version-token dot-segment boundary
            # may split a head token mid-word ("Release 7" roster vs
            # "Release 7.2 …" heading); anything else is a sub-word
            # accident ("Reference" inside "References").
            head_tok = head_tokens[hi]
            if head_tok[ho] != ".":
                return False
            if (
                _VERSION_TOKEN_RE.fullmatch(head_tok) is None
                or _VERSION_TOKEN_RE.fullmatch(needle_tokens[-1]) is None
            ):
                return False
            while ho < len(head_tok) and head_tok[ho] == ".":
                ho += 1
        leftover = len(head_tokens) - hi + (1 if ho > 0 else 0)
        return leftover <= max_extra

    @staticmethod
    def _dot_leader_page(chunks_on_page: list[dict[str, Any]]) -> bool:
        """Return True when a page's chunk lines look like a printed ToC.

        A flattened ToC page is dominated by lines ending in a page serial
        ("12 Bayesian Deep Learning 310") or carrying dot leaders ("Chapter
        8 ....... 223"); real body pages are prose.  A page classifies as
        ToC-like when at least ``_DOT_LEADER_MIN_SHARE`` (60%) of its
        non-empty chunk lines end in 1-4 digits or contain a ``..``+ leader
        run — the guard the section-heading evidence tier and the
        section-number / loose-digit scans apply so ToC rows (whatever role
        docling stamped them with) never anchor a chapter.

        Parameters
        ----------
        chunks_on_page:
            The chunk dicts stored on the page (any roles the caller
            scanned; callers pass exactly the stream they are about to pin
            from).

        Returns
        -------
        bool
            True when the page is dot-leader/serial dense (ToC-like).
        """
        lines = [
            stripped
            for chunk in chunks_on_page
            for line in (chunk.get("chunk_text") or "").split("\n")
            if (stripped := line.strip())
        ]
        if not lines:
            return False
        toc_like = sum(
            1
            for line in lines
            if _DOT_LEADER_TAIL_RE.search(line) or _DOT_LEADER_RUN_RE.search(line)
        )
        return toc_like / len(lines) >= _DOT_LEADER_MIN_SHARE

    @staticmethod
    def _section_heading_pins(
        chapters: list[tuple[int, str, str]],
        src: str,
        heading_chunks: list[dict[str, Any]],
        boiler_pages: set[int] | None = None,
        body_chunks_by_page: dict[int, list[dict[str, Any]]] | None = None,
    ) -> dict[int, int]:
        """Pin roster chapters provisionally at their first ``N.1`` heading page.

        Every chapter's first numbered section heading (``N.1``, heading
        role) sits on or beside the chapter's true opening page even when
        the banner/title heading itself is dropped, so it is the strongest
        chapter-start evidence available to the enumeration pipeline.  For
        each roster chapter the FIRST heading chunk shaped ``N.1`` /
        ``N.1.m`` (pages walked in order) on a page at or above the
        front-matter floor (10), outside license/colophon boilerplate, and
        on a page that does not classify as ToC-like
        (:meth:`_dot_leader_page` — a dot-leader-dense page is a printed
        ToC whose rows can carry ``N.1`` shapes, and must never pin) wins
        the pin.

        The pin is provisional at ±1-page precision: when the heading's
        page also carries body chunks the section heading sits below the
        page top (opener intro above it), so the chapter is pinned one page
        earlier; a page carrying only the heading chunk is a bare opener
        page and pins at the heading's own page.  Exact ToC evidence
        (listing rows / recovered run-on rows resolved through a validated
        printed→stored offset) may REPLACE these pins; fuzzy anchors and
        digit scans may not.

        Parameters
        ----------
        chapters:
            Roster entries as ``(chapter_number, source, title)``.
        src:
            Source document the pins must belong to.
        heading_chunks:
            Heading-role chunks for the source (any order).
        boiler_pages:
            License/colophon pages excluded from pinning.
        body_chunks_by_page:
            Body chunks grouped by page number for ``src``; drives both the
            ±1 adjustment and the ToC-like page classification.  When
            omitted, no page is considered to carry body chunks.

        Returns
        -------
        dict[int, int]
            Chapter number -> provisionally pinned page (within one page of
            the chapter's true opener).
        """
        pins: dict[int, int] = {}
        boiler = boiler_pages or set()
        body_by_page = body_chunks_by_page or {}
        wanted = {
            ch_num
            for ch_num, ch_src, _title in chapters
            if ch_src == src and 1 <= ch_num <= 30
        }
        if not wanted:
            return pins
        headings_by_page: dict[int, list[dict[str, Any]]] = {}
        for heading in heading_chunks:
            headings_by_page.setdefault(
                int(heading.get("page_number") or 0), []
            ).append(heading)
        for page in sorted(headings_by_page):
            if page < 10 or page in boiler:
                continue
            page_chunks = body_by_page.get(page, []) + headings_by_page[page]
            if _StructureMixin._dot_leader_page(page_chunks):
                continue
            # ±1 contract: body chunks on the heading's page mean the
            # heading sits below the page top (opener intro above it) —
            # pin one page earlier; a heading-only page is the opener
            # itself and pins exactly.
            pin = page - 1 if body_by_page.get(page) else page
            for heading in headings_by_page[page]:
                match = _SECTION_PIN_RE.match(
                    (heading.get("chunk_text") or "").split("\n")[0].strip()
                )
                if match is None:
                    continue
                ch_num = int(match.group(1))
                if ch_num in wanted and ch_num not in pins:
                    pins[ch_num] = pin
            if len(pins) == len(wanted):
                break
        return pins

    @staticmethod
    def _select_monotone_pins(pins: dict[int, int]) -> dict[int, int]:
        """Keep the largest strictly-increasing subset of chapter-number pins.

        Chapter openings must increase with chapter number (same open-interval
        contract as :meth:`_pin_fits_window`).  Conflicting pins are resolved
        by maximum-cardinality selection over (chapter, page) pairs; equal-
        cardinality ties prefer the subset with the larger total pin page
        (front-matter mis-anchors pin to near-page-0 listings, real openers
        sit in the document body) with a lexicographic chapter-set final
        tiebreak, so the outcome stays deterministic.  This replaces the
        previous fixed-point loop that popped the highest-numbered violator
        each scan — a pin landing on end-of-book license text outlived there
        every real pin it corrupted.  Dropped pins are logged with the
        historical "Rejected chapter" message shape which tests assert on.
        """
        items = sorted(pins.items())
        n = len(items)
        if n < 2:
            return dict(pins)
        best_len = [1] * n
        best_sum = [0] * n
        best_chain: list[tuple[int, ...]] = [(ch,) for ch, _ in items]
        parent = [-1] * n
        for i in range(n):
            ch_i, pg_i = items[i]
            best_sum[i] = pg_i
            for j in range(i):
                ch_j, pg_j = items[j]
                if ch_j >= ch_i or pg_j >= pg_i:
                    continue
                cand_len = best_len[j] + 1
                cand_sum = best_sum[j] + pg_i
                cand_chain = best_chain[j] + (ch_i,)
                if (cand_len, cand_sum) < (best_len[i], best_sum[i]):
                    continue
                if (cand_len, cand_sum) > (best_len[i], best_sum[i]) or (
                    cand_chain < best_chain[i]
                ):
                    best_len[i] = cand_len
                    best_sum[i] = cand_sum
                    best_chain[i] = cand_chain
                    parent[i] = j
        max_key = max((best_len[i], best_sum[i]) for i in range(n))
        end = min(
            (i for i in range(n) if (best_len[i], best_sum[i]) == max_key),
            key=lambda i: best_chain[i],
        )
        keep: set[int] = set()
        node = end
        while node != -1:
            keep.add(items[node][0])
            node = parent[node]
        if len(keep) == n:
            return dict(pins)
        for ch, pg in items:
            if ch not in keep:
                logger.debug(
                    "Rejected chapter %d pin @%d violating monotonic window; "
                    "larger consistent pin subset kept",
                    ch,
                    pg,
                )
        return {ch: pg for ch, pg in pins.items() if ch in keep}

    @staticmethod
    def _pin_fits_window(first_pg: dict[int, int], ch: int, pg: int) -> bool:
        """Open-interval monotonic-window check for a candidate chapter pin.

        Mirrors the monotone selection applied to the heading/body-title
        pins: the pin must sit strictly above the nearest lower-numbered
        pinned chapter's page and strictly below the nearest higher-numbered
        pinned chapter's page, so chapter-number order keeps matching page
        order and the derived page ranges stay disjoint (an out-of-window
        pin collides with a neighbor's range and the ascending-key bucket
        assignment starves the numbered-later chapter of every body chunk).
        Later scan tiers pin after that selection has run and nothing
        re-checks their pins, so they apply this check at insertion time.
        """
        lo_pg = max((p for n, p in first_pg.items() if n < ch), default=None)
        hi_pg = min((p for n, p in first_pg.items() if n > ch), default=None)
        return (lo_pg is None or pg > lo_pg) and (hi_pg is None or pg < hi_pg)

    # -- Anthology-aware chapter summarization --------------------------------
    # (add-anthology-aware-chapter-summarization.  Contracts declared in
    # _attributes.py; routing in _pipeline.py._iterative_query; the per-part
    # and whole-document summaries live on _FallbackMixin — this mixin only
    # detects the shape, builds per-part maps, and vets legacy maps.)

    @staticmethod
    def _detect_anthology_parts(
        heading_chunks: list[dict[str, Any]],
        source: str,
    ) -> list[dict[str, Any]] | None:
        """Detect an anthology document and return its part openers.

        An anthology concatenates several sub-reports that each restart their
        own section numbering, so the single monotone chapter sequence the
        legacy machinery models does not exist.  The document is claimed only
        on multiple independent signals (design.md §1):

        1. part openers — ≥3 heading-role chunks starting with a
           part-opener shape (_ANTHOLOGY_PART_OPENER_RE / _WORD_RE);
        2. numbering restarts — ≥2 parts whose first numbered section
           heading inside the part is numbered 1 (_ANTHOLOGY_SECTION_RE);
        3. scale — ≥3 parts; the ≥2-body-bearing-pages check lives in
           :meth:`_enrich_anthology_parts` (it needs the body stream).

        Single-book documents (chapter banners, straight 1..N numbering)
        carry no part-labeled headings, so signal 1 fails and the legacy
        path runs unchanged.

        Returns ``[{"label": ..., "title": ..., "start_page": ...}, ...]`` in
        document order, or ``None`` when the document is not an anthology.
        """
        # One opener occurrence per label, LAST in document order: a
        # front-matter master index that lists the openers as heading-role
        # rows repeats every label on its 1-3 front-matter pages, while the
        # real opener heading sits later in the document — the last
        # occurrence is the real one.  (Verified on the corpus compilation:
        # its pp. 1-2 master topic index is body-role, so the heading stream
        # holds exactly one occurrence per label; this dedupe is defense for
        # documents that do emit heading-role index rows.  Index-row
        # occurrences cluster on the front-matter pages and can therefore
        # never displace a later real opener.)
        openers_by_label: dict[str, tuple[int, int, str]] = {}
        ordered = sorted(heading_chunks, key=_anthology_heading_sort_key)
        for chunk in ordered:
            if not _anthology_is_heading_chunk(chunk):
                continue
            chunk_source = chunk.get("source_file")
            if source and chunk_source and not str(chunk_source).startswith(source):
                continue
            text = (chunk.get("chunk_text") or "").lstrip()
            opener = _ANTHOLOGY_PART_OPENER_RE.match(text)
            word = None if opener is not None else _ANTHOLOGY_PART_WORD_RE.match(text)
            if opener is not None:
                label = opener.group("label")
                title = opener.group("title").strip()
            elif word is not None:
                label = word.group("label")
                title = (word.group("title") or "").strip()
            else:
                continue
            openers_by_label[label] = (
                int(chunk.get("page_number") or 0),
                int(chunk.get("page_pos") or 0),
                title,
            )
        parts = sorted(
            (page, pos, label, title)
            for label, (page, pos, title) in openers_by_label.items()
        )
        if len(parts) < _ANTHOLOGY_MIN_OPENERS:
            return None
        # Signal 2 — numbering restarts: the first numbered section heading
        # inside each part's page range must be numbered 1 in ≥2 parts.
        restarts = 0
        for i, (page, pos, _label, _title) in enumerate(parts):
            end_page = parts[i + 1][0] - 1 if i + 1 < len(parts) else None
            for chunk in ordered:
                chunk_page, chunk_pos = _anthology_heading_sort_key(chunk)
                if chunk_page < page or (
                    end_page is not None and chunk_page > end_page
                ):
                    continue
                if chunk_page == page and chunk_pos < pos:
                    # The previous part's trailing section headings can share
                    # the opener's page (document tail layout); only headings
                    # at/after the opener belong to this part.
                    continue
                if not _anthology_is_heading_chunk(chunk):
                    continue
                section = _ANTHOLOGY_SECTION_RE.match(
                    (chunk.get("chunk_text") or "").lstrip()
                )
                if section is None:
                    continue
                if int(section.group("num").split(".")[0]) == 1:
                    restarts += 1
                break
        if restarts < _ANTHOLOGY_MIN_RESTARTS:
            return None
        logger.debug(
            "Anthology shape detected for %s: %d parts, %d restart at 1",
            source,
            len(parts),
            restarts,
        )
        return [
            {"label": label, "title": title, "start_page": page}
            for page, _pos, label, title in parts
        ]

    def _anthology_opener_pos(
        self,
        headings: list[dict[str, Any]],
        page: int,
        label: str,
    ) -> int:
        """Position on ``page`` of the opener heading carrying ``label``.

        The detector's part dicts carry label/title/start_page only, so the
        enrichment re-locates the opener among the heading chunks to know
        where on the opener page the part actually starts — the previous
        part's trailing section headings can share that page and must not
        enter this part's roster.  Returns 0 (no position filter) when the
        opener is not found.
        """
        opener_pos = 0
        for chunk in sorted(headings, key=_anthology_heading_sort_key):
            if int(chunk.get("page_number") or 0) != page:
                continue
            if not _anthology_is_heading_chunk(chunk):
                continue
            text = (chunk.get("chunk_text") or "").lstrip()
            opener = _ANTHOLOGY_PART_OPENER_RE.match(text)
            word = None if opener is not None else _ANTHOLOGY_PART_WORD_RE.match(text)
            matched = opener if opener is not None else word
            if matched is not None and matched.group("label") == label:
                # Keep the LAST match so the dedupe rule in
                # _detect_anthology_parts (last occurrence wins) stays
                # consistent when a label repeats on the same page.
                opener_pos = int(chunk.get("page_pos") or 0)
        return opener_pos

    def _anthology_part_sections(
        self,
        headings: list[dict[str, Any]],
        start: int,
        end: int,
        opener_pos: int,
    ) -> list[dict[str, Any]]:
        """Roster the numbered sections of one part from its heading chunks.

        A section pins at its own heading page (heading chunks are the
        reliable anchor in this shape); dotted ``N.M`` headings keep their
        full label so they group under their parent ``N`` lexically.  Kept
        small on purpose: label, page, title.
        """
        sections: list[dict[str, Any]] = []
        for chunk in sorted(headings, key=_anthology_heading_sort_key):
            page, pos = _anthology_heading_sort_key(chunk)
            if page < start or page > end:
                continue
            if page == start and pos < opener_pos:
                continue
            if not _anthology_is_heading_chunk(chunk):
                continue
            section = _ANTHOLOGY_SECTION_RE.match(
                (chunk.get("chunk_text") or "").lstrip()
            )
            if section is None:
                continue
            sections.append(
                {
                    "label": section.group("num"),
                    "page": page,
                    "title": re.sub(r"\s+", " ", section.group("title")).strip(),
                }
            )
        return sections

    def _anthology_part_bucket(
        self,
        body_chunks_by_page: dict[int, list[dict[str, Any]]],
        start: int,
        end: int,
        opener_pos: int,
    ) -> list[dict[str, Any]]:
        """Sample one part's body chunks exactly like a legacy chapter bucket.

        Same constants and rules as the legacy multi-chapter round-robin in
        ``_pipeline.py`` (_ANTHOLOGY_PART_CHUNK_LIMIT per part,
        _ANTHOLOGY_PART_PAGE_CAP per page, header-over-footer promotion on
        capped pages with extra slots for section-header-dense pages).  An
        empty part keeps an empty bucket — its summary carries the existing
        placeholder note.
        """
        candidates: list[dict[str, Any]] = []
        for page in range(start, end + 1):
            page_chunks = body_chunks_by_page.get(page, ())
            if page == start and opener_pos:
                page_chunks = [
                    chunk
                    for chunk in page_chunks
                    if int(chunk.get("page_pos") or 0) >= opener_pos
                ]
            candidates.extend(page_chunks)
        candidates.sort(key=_anthology_heading_sort_key)
        bucket: list[dict[str, Any]] = []
        per_page: dict[int, int] = {}
        for chunk in candidates:
            if len(bucket) >= _ANTHOLOGY_PART_CHUNK_LIMIT:
                break
            page = int(chunk.get("page_number") or 0)
            if per_page.get(page, 0) < _ANTHOLOGY_PART_PAGE_CAP:
                per_page[page] = per_page.get(page, 0) + 1
                chunk["score"] = 0.5
                bucket.append(chunk)
                continue
            # Page at cap — promote header chunks over footers/captions that
            # were collected first (legacy promotion rule).
            if not _ANTHOLOGY_BUCKET_SECTION_RE.search(chunk.get("chunk_text", "")):
                continue
            replaced = False
            for i, existing in enumerate(bucket):
                if existing.get("page_number") == page and not (
                    _ANTHOLOGY_BUCKET_SECTION_RE.search(existing.get("chunk_text", ""))
                ):
                    chunk["score"] = 0.5
                    bucket[i] = chunk
                    replaced = True
                    break
            if not replaced and per_page.get(page, 0) < (_ANTHOLOGY_PART_PAGE_CAP + 2):
                per_page[page] = per_page.get(page, 0) + 1
                chunk["score"] = 0.5
                bucket.append(chunk)
        return bucket

    def _enrich_anthology_parts(
        self,
        parts: list[dict[str, Any]],
        body_chunks_by_page: dict[int, list[dict[str, Any]]],
        headings: list[dict[str, Any]],
        total_pages: int,
    ) -> list[dict[str, Any]] | None:
        """Extend detected anthology parts with ranges, sections, buckets.

        Adds per part: "end_page" (the next opener's page minus 1; the last
        part runs to ``total_pages``), "sections" (the part's own numbered
        section roster, each pinned at its heading's page) and "chunks" (the
        part's sampled body bucket, filled exactly like the legacy
        multi-chapter buckets).  Returns None when the scale check fails —
        any part spanning fewer than _ANTHOLOGY_MIN_PART_BODY_PAGES
        body-bearing pages is not a real sub-report — and the caller then
        takes the legacy path.  The check runs before any enrichment so a
        declined document leaves no partial work behind.
        """
        ordered = sorted(parts, key=lambda p: int(p.get("start_page") or 0))
        bounds = [
            (
                int(part.get("start_page") or 0),
                (
                    int(ordered[i + 1].get("start_page") or 0) - 1
                    if i + 1 < len(ordered)
                    else total_pages
                ),
            )
            for i, part in enumerate(ordered)
        ]
        for (start, end), part in zip(bounds, ordered, strict=True):
            body_pages = sum(1 for page in body_chunks_by_page if start <= page <= end)
            if body_pages < _ANTHOLOGY_MIN_PART_BODY_PAGES:
                logger.debug(
                    "Anthology enrichment declined for %s: part %s spans %d "
                    "body-bearing pages (< %d)",
                    part.get("label"),
                    start,
                    body_pages,
                    _ANTHOLOGY_MIN_PART_BODY_PAGES,
                )
                return None
        enriched: list[dict[str, Any]] = []
        for (start, end), part in zip(bounds, ordered, strict=True):
            label = str(part.get("label") or "")
            opener_pos = self._anthology_opener_pos(headings, start, label)
            enriched.append(
                {
                    **part,
                    "end_page": end,
                    "sections": self._anthology_part_sections(
                        headings, start, end, opener_pos
                    ),
                    "chunks": self._anthology_part_bucket(
                        body_chunks_by_page, start, end, opener_pos
                    ),
                }
            )
        return enriched

    def _chapter_range_gate(
        self,
        chapter_ranges_: dict[int, tuple[int, int]],
        evidence_pin_pg_: dict[int, int],
        src: str,
    ) -> bool:
        """Veto a legacy chapter map that disagrees with its own evidence.

        The legacy machinery assumes one monotone chapter sequence; on shapes
        it was never tuned for (anthologies, flattened front matter) it can
        derive a confidently wrong map.  Every chapter with a real range
        (start > 0; sentinel ``(0, -1)`` ranges have no derived start to
        compare) whose provisional ``N.1`` evidence pin exists is compared:
        it agrees when the final range start stays within
        _CHAPTER_GATE_MAX_PIN_DRIFT pages of the pin.  The gate skips when
        fewer than _CHAPTER_GATE_MIN_COMPARED chapters are comparable —
        absence of evidence is not disagreement (the HCD report carries 0
        evidence pins and keeps the legacy path) — and vetoes below
        _CHAPTER_GATE_MIN_SCORE agreement (calibration in the constants'
        comment; baseline scores recorded in
        tests/fixtures/chapter_map/baselines.json).  The gate never modifies
        pins or ranges; a passing map proceeds byte-identically.
        """
        agreements: list[bool] = []
        for ch_num, page_range in chapter_ranges_.items():
            if page_range[0] <= 0:
                continue
            pin_page = evidence_pin_pg_.get(ch_num)
            if pin_page is None:
                continue
            agreements.append(
                abs(page_range[0] - pin_page) <= _CHAPTER_GATE_MAX_PIN_DRIFT
            )
        if len(agreements) < _CHAPTER_GATE_MIN_COMPARED:
            return True
        score = sum(agreements) / len(agreements)
        if score < _CHAPTER_GATE_MIN_SCORE:
            logger.warning(
                "chapter range agreement gate vetoed the derived map for %s "
                "(score %.2f)",
                src,
                score,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Structure-tree query path (add-structure-aware-ingestion, tasks 12-14)
    # ------------------------------------------------------------------
    #
    # A stored capture tree (``StructureStore.load_tree``) replaces the
    # regex-derived chapter map outright whenever it carries at least one
    # chapter/section node: node page ranges become the chapter ranges and
    # node numbers/titles become the roster.  Everything here is additive —
    # every failure mode (store unavailable, load error, treeless document,
    # zero structural nodes, storage without the page-list ``find_chunks``
    # API) returns ``None`` so the legacy scan continues unchanged, and the
    # anthology detector plus the chapter-range agreement gate keep
    # governing the legacy path only.

    def _get_structure_store(self) -> StructureStore | None:
        """Return the lazily-created, cached structure store, or ``None``.

        The store opens the shared SQLite database (``cfg.sqlite_path``) on
        first use, so it is created lazily here instead of in the pipeline
        constructor and cached for the pipeline's lifetime.  Construction
        failures (unreadable path, broken SQLite) are downgraded to
        ``None`` — every caller then takes the legacy chapter path.

        Returns
        -------
            The cached :class:`StructureStore`, or ``None`` when the store
            cannot be created.
        """
        if self._structure_store_ready:
            return self._structure_store
        self._structure_store_ready = True
        try:
            self._structure_store = StructureStore()
        except Exception:
            logger.warning(
                "Structure store unavailable; tree-governed chapter "
                "enumeration disabled",
                exc_info=True,
            )
            self._structure_store = None
        return self._structure_store

    def _load_document_tree(self, source_file: str) -> DocumentStructure | None:
        """Load the stored capture tree for *source_file*.

        Args:
            source_file: The document key, exactly the string stored in the
                qdrant payload ``source_file`` (design §9 trap 6).

        Returns
        -------
            The stored :class:`DocumentStructure`, or ``None`` when the
            document is treeless or the lookup failed (both send the caller
            to the legacy chapter path; load errors are logged once here).
        """
        store = self._get_structure_store()
        if store is None:
            return None
        try:
            return store.load_tree(source_file)
        except Exception:
            logger.warning(
                "Structure tree lookup failed for %s; using the legacy chapter scan",
                source_file,
                exc_info=True,
            )
            return None

    @staticmethod
    def _tree_chapter_map(
        nodes: list[StructureNode],
    ) -> tuple[dict[int, tuple[int, int]], dict[int, str]]:
        """Build the legacy-shaped chapter map from tree nodes.

        Chapter-shaped nodes are ``kind`` ``"chapter"`` or top-level
        ``"section"`` nodes whose ``number`` is a plain integer (nested
        sections carry dotted numbers and belong to their chapter's range).
        Ranges are the node's inclusive ``page_start``/``page_end``; a node
        without a usable page range gets the legacy ``(0, -1)`` sentinel so
        the existing empty-bucket placeholder note speaks for it.  The first
        (page-ordered) node wins when numbers repeat.

        Args:
            nodes: The tree's nodes, in stored (page-ordered) sequence.

        Returns
        -------
            ``(ranges, titles)`` — chapter number to inclusive page range
            (sentinel ``(0, -1)`` when the node carries none), and chapter
            number to raw node title (``""`` when untitled).  Empty
            ``ranges`` means the tree has no structural chapter nodes and
            the caller must fall back to the legacy scan.
        """
        ranges: dict[int, tuple[int, int]] = {}
        titles: dict[int, str] = {}
        for node in nodes:
            if node.kind not in ("chapter", "section"):
                continue
            number = (node.number or "").strip()
            if not re.fullmatch(r"\d+", number):
                continue
            ch_num = int(number)
            if ch_num in ranges:
                continue
            start, end = node.page_start, node.page_end
            if start is not None and end is not None and end >= start:
                ranges[ch_num] = (start, end)
            else:
                ranges[ch_num] = (0, -1)
            titles[ch_num] = node.title or ""
        return ranges, titles

    @staticmethod
    def _tree_chapter_buckets(
        storage: Any,
        source_file: str,
        chapter_ranges: dict[int, tuple[int, int]],
    ) -> dict[int, list[dict[str, Any]]] | None:
        """Collect per-chapter body chunks via the existing qdrant API.

        One ``find_chunks`` call per chapter with the node range expanded to
        an exact ``page_number`` list (MatchAny — design §8); no new storage
        API is used.  The client-side ``chunk_role == "body"`` filter mirrors
        ``get_body_chunks`` semantics, which ``find_chunks`` does not apply
        itself, so summarizer input matches the legacy shape.  Sentinel
        ranges skip the storage call and leave an empty bucket (the existing
        placeholder-note path speaks for the chapter).  Chunks are ordered
        ``(page_number, page_pos)`` because the live ``find_chunks`` scroll
        order is unspecified within a page.

        Args:
            storage: The searcher's vector storage.
            source_file: Exact document key for the equality filter.
            chapter_ranges: Chapter number to inclusive page range.

        Returns
        -------
            Chapter number to bucket (possibly empty), or ``None`` when the
            storage has no ``find_chunks`` API (legacy doubles and older
            stores) — the caller then falls back to the legacy path.
        """
        finder = getattr(storage, "find_chunks", None)
        if not callable(finder):
            return None
        buckets: dict[int, list[dict[str, Any]]] = {}
        for ch_num, (start_pg, end_pg) in chapter_ranges.items():
            bucket: list[dict[str, Any]] = []
            if end_pg >= start_pg:
                found = finder(
                    source_file=source_file,
                    page_number=list(range(start_pg, end_pg + 1)),
                )
                for chunk in cast(list[dict[str, Any]], list(found)):
                    if chunk.get("chunk_role") != "body":
                        continue
                    chunk["score"] = 0.5
                    bucket.append(chunk)
                bucket.sort(
                    key=lambda c: (
                        c.get("page_number") or 0,
                        c.get("page_pos") or 0,
                    )
                )
            buckets[ch_num] = bucket
        return buckets
