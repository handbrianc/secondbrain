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

from pathlib import Path
from typing import Any

# Minimum total non-whitespace characters for the native text layer to be
# considered a faithful substitute for the full docling pipeline. Scanned or
# near-empty PDFs fall below this and still route through docling/OCR.
PDF_FAST_TEXT_MIN_CHARS = 200


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
      (scanned/empty PDFs cannot be faithfully represented by the text layer).

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

    total_non_whitespace = sum(
        1 for seg in segments for ch in seg["text"] if not ch.isspace()
    )
    if total_non_whitespace < PDF_FAST_TEXT_MIN_CHARS:
        return None

    return segments
