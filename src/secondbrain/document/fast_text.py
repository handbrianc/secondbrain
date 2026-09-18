"""Fast native-text PDF extraction that skips docling's layout/OCR models.

When a PDF carries an embedded (native) text layer, running docling's heavy
layout + OCR pipeline is pure overhead. This module offers a pure-pypdfium2
text extraction (no docling, no layout/OCR models) guarded behind the
``pdf_fast_text_enabled`` config flag.
:func:`try_fast_pdf_extraction` is the routing helper the extraction sites
(``processor.py`` and ``ingestor/_sync.py``) call before falling through to the
unchanged docling pipeline. It returns ``None`` whenever the fast path cannot or
should not run — non-PDF input, the feature disabled, OCR explicitly requested,
or a native text layer too sparse (scanned/empty) to be a faithful substitute —
so the caller always falls back to full docling extraction. ``pdf_fast_text_enabled``
defaults to True (fast path on); set it to False to force the full docling
pipeline everywhere, or to True only with ``pdf_ocr_enabled=False`` since OCR
users expect OCR output.

pypdfium2 is imported lazily inside :func:`extract_native_pdf_text` (it is a
docling dependency, already installed) to match the repo's lazy-import style and
avoid pulling anything heavy in at module import time.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

# Minimum total non-whitespace characters for the native text layer to be
# considered a faithful substitute for the full docling pipeline. Scanned or
# near-empty PDFs fall below this and still route through docling/OCR.
PDF_FAST_TEXT_MIN_CHARS = 200

# Fraction of non-whitespace characters in the fast-extracted native text that
# must be "corruption fingerprints" for the layer to be judged unusable. C1
# control characters (U+0080-U+009F), the Unicode replacement char (U+FFFD),
# private-use glyphs (U+E000-U+F8FF), and box-drawing glyphs (U+2500-U+257F)
# never legitimately appear in document prose. Their presence is the signature
# of a broken font/ToUnicode map or text mis-decoded by the extraction engine
# (which surfaces as wrong digits, e.g. "2012" rendered as "2132", and garbled
# glyphs). When the fast path's output trips this, the caller routes the whole
# file through the full docling pipeline (or OCR) instead of indexing garbage.
PDF_FAST_TEXT_CORRUPTION_RATIO = 0.02

# The structure probe only inspects the leading pages (front matter + early
# body, where a book's ToC and opening chapters live), so its cost stays
# negligible relative to extraction itself.
PDF_STRUCTURE_PROBE_MAX_PAGES = 40

# Line-start "Chapter N" openers and dotted ToC entries ("Title .... 42") are
# fingerprints of a structured book. The hit thresholds inside
# :func:`_looks_like_structured_book` keep a lone mention (a cross-reference,
# a single dotted line) from misrouting plain documents through the slow
# docling pipeline.
_CHAPTER_OPENER_RE = re.compile(r"^\s*chapter\s+\d+\b", re.IGNORECASE | re.MULTILINE)
_TOC_ENTRY_RE = re.compile(r"^\s*.+\.{3,}\s*\d+\s*$", re.MULTILINE)

# The book's printed page number appears as a "[ N ]" marker, typically at the
# top of each page.  The stored ``page_number`` is the PDF's *physical* page
# index, which differs from it (front matter / blank pages shift them), so the
# printed marker is the ground truth for "what is on page N" lookups.
_PRINTED_PAGE_RE = re.compile(r"\[\s*(\d{1,4})\s*\]")

# LaTeX/manual books stamp the printed page number in a page footer shaped
# "N / total" ("78 / 634").  Docling extracts such footers as stand-alone
# navigation chunks, so the printed index is carried in plain text rather
# than a bracket marker.  The full "N / total" shape is required (not a bare
# number) so ordinary body digits can never parse as a page stamp.
_FOOTER_PAGE_RE = re.compile(r"^\s*(\d{1,4})\s*/\s*\d{1,4}\s*$")

# Sanity bound for any parsed page stamp: values beyond this are in-text
# citations/IDs that regex-extraction mistook for page markers (observed:
# "[ 1647 ]" from a citation block in a 634-page book), which would seed a
# phantom printed-page index.
_PRINTED_PAGE_MAX = 9999


def extract_printed_page(text: str) -> int | None:
    """Return the printed-page marker in *text*, or None.

    Scans for a bracketed ``[ N ]`` marker (the book's printed page number) and
    returns ``N``. Returns ``None`` when no marker is present.
    """
    match = _PRINTED_PAGE_RE.search(text)
    if not match:
        return None
    try:
        return _checked_page(int(match.group(1)))
    except ValueError:
        return None


def _checked_page(value: int) -> int:
    """Reject page stamps beyond the sanity bound (in-text citation noise)."""
    if value < 1 or value > _PRINTED_PAGE_MAX:
        raise ValueError(value)
    return value


def footer_page_offset(nav_texts: dict[int, str]) -> int | None:
    """Return the print-to-physical offset from navigation footer texts.

    Keys are physical page numbers, values the footer text ("78 / 634").
    The offset is the majority physical-minus-printed difference, trusted
    only when it holds for at least 80 % of at least three distinct footer
    pages (the same gates :func:`resolve_printed_pages` applies).
    """
    sampled: dict[int, int] = {}
    for physical, text in nav_texts.items():
        m = _FOOTER_PAGE_RE.match(text.strip())
        if not m:
            continue
        try:
            printed = _checked_page(int(m.group(1)))
        except ValueError:
            continue
        if 0 < printed < physical:
            sampled[physical] = printed
    if len(sampled) < 3:
        return None
    offset_counts: Counter[int] = Counter(
        physical - printed for physical, printed in sampled.items()
    )
    offset, agree = max(offset_counts.items(), key=lambda pair: (pair[1], -pair[0]))
    if agree < 3 or agree / len(sampled) < 0.8:
        return None
    return offset


def resolve_printed_pages(
    docs: list[dict[str, Any]],
) -> int:
    """Fill ``printed_page`` per physical page from "N / total" footer chunks.

    Bracket-marker extraction (``extract_printed_page``) covers books that
    stamp ``[ N ]`` markers; footer-stamped books (Proxmox VE admin guide,
    most LaTeX manuals) instead carry "N / 634" navigation chunks that docling
    never scans for page stamps.  After a document's chunk list is assembled,
    this pass parses those footers, derives each footer's physical
    ``page_number``, checks the extraction for consistency and plausibility,
    then stamps ``printed_page`` on every chunk of each matched physical page.

    Confidence gates (conservative by design — a wrong stamp corrupts page
    lookups forever):
    - every footer's printed value must be below its own physical page number
      (printed indexes trail the physical index for books with front matter);
    - the physical-minus-printed offset must agree across at least 80 % of
      footer pages and at least three distinct physical pages.

    When the gates pass, the agreed footer mapping is authoritative: it
    overwrites any pre-existing ``printed_page`` on the covered pages.
    Chunk-level bracket-marker extraction cannot see the book context
    (in-text citations like "[ 1647 ] IEEE Std ..." parse as a marker), so
    footer evidence is the stronger signal on every page it covers; pages
    outside the footer-covered set keep whatever bracket stamps they carry.

    Mutates *docs* in place and returns the number of physical pages stamped.

    Parameters
    ----------
    docs:
        Chunk dicts as built by the ingest assembly sites; each carries
        ``page_number``, ``printed_page`` (from bracket-marker extraction),
        ``chunk_text`` and ``element_type``/``chunk_role``.
    """
    footer_pages: dict[int, int] = {}
    nav_texts: dict[int, str] = {}
    for c in docs:
        if (c.get("element_type") or c.get("chunk_role") or "body") != "navigation":
            continue
        m = _FOOTER_PAGE_RE.match(c.get("chunk_text") or "")
        if m:
            try:
                printed = _checked_page(int(m.group(1)))
            except ValueError:
                continue
            physical = int(c.get("page_number") or 0)
            # Printed indexes never lead the physical index by design (front
            # matter shifts them the other way); a stamp at/above its page
            # cannot belong to this book's pagination.
            if printed < physical:
                footer_pages[physical] = printed
                nav_texts[physical] = c.get("chunk_text") or ""
    if len(footer_pages) < 3:
        return 0
    offset = footer_page_offset(nav_texts)
    if offset is None:
        return 0
    valid = set(footer_pages)
    page_maps: dict[int, int] = {}
    for physical in valid:
        page_maps[physical] = physical - offset
    for c in docs:
        physical = int(c.get("page_number") or 0)
        stamped_page = page_maps.get(physical)
        if stamped_page is None:
            continue
        if c.get("printed_page") != stamped_page:
            c["printed_page"] = stamped_page
    return len(page_maps)


def _looks_corrupted(text: str) -> bool:
    """Return True if *text* carries a broken-glyph / mis-decoding fingerprint.

    Detects characters that have no legitimate use in extracted document prose:
    C1 control chars (U+0080-U+009F), the Unicode replacement char (U+FFFD),
    private-use glyphs (U+E000-U+F8FF), and box-drawing glyphs (U+2500-U+257F).
    These arise when a PDF's font/ToUnicode map is broken (the usual cause of the
    garbled numeric/glyph output described in the module docstring) or when bytes
    were decoded with the wrong codec.

    Parameters
    ----------
    text:
        The extracted text to inspect (a page segment).

    Returns
    -------
    bool
        True when the ratio of suspicious characters to non-whitespace
        characters exceeds ``PDF_FAST_TEXT_CORRUPTION_RATIO``.
    """
    if not text:
        return False

    total = 0
    corrupt = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        o = ord(ch)
        if (
            0x80 <= o <= 0x9F
            or o == 0xFFFD
            or 0xE000 <= o <= 0xF8FF
            or 0x2500 <= o <= 0x257F
        ):
            corrupt += 1
    if total == 0:
        return False
    return corrupt / total > PDF_FAST_TEXT_CORRUPTION_RATIO


def _looks_like_structured_book(segments: list[dict[str, Any]]) -> bool:
    """Return True when the leading pages carry book-structure fingerprints.

    Scans only the first ``PDF_STRUCTURE_PROBE_MAX_PAGES`` extracted pages
    (front matter + early body, where a book's ToC and opening chapters live)
    for line-start "Chapter N" openers and dotted ToC entries, and requires
    several hits so a lone cross-reference cannot misroute a plain document
    through the slow docling pipeline.
    """
    head = "\n".join(
        str(seg.get("text", "")) for seg in segments[:PDF_STRUCTURE_PROBE_MAX_PAGES]
    )
    chapter_hits = len(_CHAPTER_OPENER_RE.findall(head))
    toc_hits = len(_TOC_ENTRY_RE.findall(head))
    return chapter_hits >= 2 or toc_hits >= 3


def extract_native_pdf_text(path: Path) -> list[dict[str, Any]]:
    """Extract a PDF's native text layer with pure pypdfium2 (no docling).

    Opens the PDF, iterates its pages (1-indexed), and collects the non-empty
    text of each page via ``get_textpage`` / ``get_text_range``. Pages that
    yield no text are skipped. This does NOT run docling's layout or OCR models
    and loads no models of any kind.

    On any failure (corrupt/unreadable PDF, pypdfium2 unavailable) an empty list
    is returned instead of raising, so the caller can fall back to docling.

    Parameters
    ----------
    path:
        Path to the PDF file.

    Returns
    -------
    list[dict[str, Any]]
        List of ``{"text": <non-empty stripped text>, "page": <1-indexed page>}``
        dicts, one per page that yielded text. Empty list on failure.
    """
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []

    try:
        pdf = pdfium.PdfDocument(str(path))
        try:
            segments: list[dict[str, Any]] = []
            for page_index in range(len(pdf)):
                page = pdf[page_index]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                finally:
                    textpage.close()
                stripped = text.strip()
                if stripped:
                    segments.append({"text": stripped, "page": page_index + 1})
            return segments
        finally:
            pdf.close()
    except Exception:
        return []


def try_fast_pdf_extraction(file_path: Path) -> list[dict[str, Any]] | None:
    """Return native-text PDF segments via the fast path, or ``None`` to fall back.

    Returns ``None`` (the caller should fall through to the full docling
    pipeline) when ANY of the following holds:

    - the file is not a PDF;
    - ``pdf_fast_text_enabled`` is False (feature off — set explicitly to force
      the full docling pipeline);
    - ``pdf_ocr_enabled`` is True (user explicitly wants OCR — do not bypass);
    - the total non-whitespace native text is below ``PDF_FAST_TEXT_MIN_CHARS``
      (scanned/empty PDFs cannot be faithfully represented by the text layer);
    - any page's native text trips :func:`_looks_corrupted` (a broken
      font/ToUnicode decode would feed garbage downstream, so the file is routed
      to the full docling pipeline instead);
    - the structure probe finds book-structure markers (line-start "Chapter N"
      openers or dotted ToC entries) in the leading pages while
      ``pdf_structure_probe_enabled`` is True — such documents are better
      served by docling's per-item structural labels than by page-blob text.

    Otherwise returns the extracted, non-empty segments.

    Parameters
    ----------
    file_path:
        Path to the candidate file.

    Returns
    -------
    list[dict[str, Any]] | None
        The fast-extracted segments, or ``None`` when the fast path must not run.
    """
    if file_path.suffix.lower() != ".pdf":
        return None

    from secondbrain.config import config

    cfg = config()
    if not cfg.pdf_fast_text_enabled:
        return None
    if cfg.pdf_ocr_enabled:
        return None

    segments = extract_native_pdf_text(file_path)
    if not segments:
        return None

    if any(_looks_corrupted(seg["text"]) for seg in segments):
        # The native text layer carries a broken font/ToUnicode decode (garbled
        # digits/glyphs). Treat it as unusable and route through docling/OCR.
        return None

    total_non_whitespace = sum(
        1 for seg in segments for ch in seg["text"] if not ch.isspace()
    )
    if total_non_whitespace < PDF_FAST_TEXT_MIN_CHARS:
        return None

    if cfg.pdf_structure_probe_enabled and _looks_like_structured_book(segments):
        # A text-layer book gains docling's per-item structural labels
        # (headings/toc entries) for structure-aware retrieval, so defer to
        # the full pipeline despite the usable native text layer.
        return None

    return segments
