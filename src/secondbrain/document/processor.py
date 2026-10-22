"""Document processing — docling lifecycle and segment extraction.

This module is responsible for the heavy-weight docling operations:
- Creating/configuring DocumentConverter instances
- Extracting text Segments from various file formats
- Running in-thread for use with ThreadPoolExecutor

Docling is lazily imported inside functions to avoid 2+ second import
overhead at module load time.

Exports:
    convert_file_to_segments: Convert a file path to list[Segment].
    create_converter: Factory for DocumentConverter with CPU accelerator.
    _extract_and_chunk_file: ThreadPoolExecutor worker (picklable at module level).
    _extract_chunk_and_embed_file: ThreadPoolExecutor worker with embedding.
"""

from __future__ import annotations

import hashlib
import logging
import os
import warnings
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired

import numpy as np
from typing_extensions import TypedDict

from secondbrain.exceptions import DocumentExtractionError

if TYPE_CHECKING:
    from secondbrain.utils.embedding_cache import EmbeddingCache

# Apply MPS patch before any docling import
from secondbrain.document.chunker import chunk_segments, docling_item_label
from secondbrain.document.docling_progress import scraped_page_progress
from secondbrain.document.fast_text import (
    extract_printed_page,
    pdf_page_count,
    resolve_printed_pages,
)
from secondbrain.utils.tracing import trace_operation

# Suppress HF-hub progress bars before any docling/transformers import.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

# Suppress PyTorch user warnings about padding+dilation on MPS - harmless
warnings.filterwarnings(
    "ignore",
    r"Using padding='same' with even kernel lengths and odd dilation",
    module="torch",
)


def create_docling_converter(file_path: Path) -> "DocumentConverter":  # noqa: UP037
    """Create a configured DocumentConverter supporting all docling formats.

    Routes through the shared per-document resolver (:func:`get_converter_for_path`)
    so this path honors the same on-demand OCR decision as every other path.

    Returns a converter pre-configured with:
    - PDF: OCR on demand (digital PDFs skip OCR via embedded text layer)
    - All other formats use docling defaults

    Factory exists to centralize format configuration and avoid bare
    DocumentConverter() instantiations that miss format options.
    """
    from secondbrain.document.docling_factory import get_converter_for_path

    return get_converter_for_path(file_path)


def _segment_as_text(item: Any) -> str:
    if hasattr(item, "export_to_data_frame"):
        try:
            return str(item.export_to_data_frame().to_csv(index=False))
        except Exception:
            return str(item)
    if hasattr(item, "text") and item.text:
        return str(item.text)
    return ""


if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)


# Re-export Segment for use in this module
class _Segment(TypedDict):
    """Local alias so worker functions have the correct type annotation."""

    text: str
    page: int
    label: NotRequired[str]


# Suffixes whose raw bytes are faithfully readable as UTF-8 text when docling
# yields nothing. Anything else without extracted text is either audio (empty
# ASR transcript) or binary/image-only content, which must fail loudly instead
# of embedding the file's raw bytes as mojibake chunks.
_TEXT_LIKE_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".log",
        ".html",
        ".htm",
        ".xml",
        ".asciidoc",
        ".adoc",
        ".tex",
        ".vtt",
        ".srt",
    }
)


def _segments_have_text(segments: Iterable[Mapping[str, Any]]) -> bool:
    """Return True when any segment carries non-whitespace text.

    Args:
        segments: Extracted segments, each carrying a ``"text"`` entry.

    Returns
    -------
        False when the list is empty or every text is whitespace-only.
    """
    return any(str(seg.get("text") or "").strip() for seg in segments)


def _fallback_text_or_raise(file_path: Path) -> str:
    """Resolve a docling extraction that produced no text, by suffix.

    Classification (checked in order, raising before any file read):

    - audio (``docling_factory._AUDIO_SUFFIXES``): the ASR pipeline returned
      an empty transcript (docling logs "ASR conversion resulted in an empty
      document" and reports PARTIAL_SUCCESS, which callers do not check).
      Reading the raw bytes would embed audio mojibake, so raise instead.
    - text-like (``_TEXT_LIKE_SUFFIXES``): keep the historical raw UTF-8 read,
      which is faithful for these formats.
    - anything else (PDF, DOCX, images, unknown binaries): no text was
      extracted and the bytes are not text, so raise.

    Args:
        file_path: Path whose extraction produced no text.

    Returns
    -------
        Raw file text (text-like suffixes only).

    Raises
    ------
        DocumentExtractionError: For audio files with an empty transcript and
            for binary/image-only files with no extracted text.
    """
    from secondbrain.document.docling_factory import _AUDIO_SUFFIXES

    suffix = file_path.suffix.lower()
    if suffix in _AUDIO_SUFFIXES:
        raise DocumentExtractionError(
            f"Audio transcription produced no text for {file_path} — the ASR "
            "model returned an empty transcript. Check ASR model availability "
            "and ingest logs."
        )
    if suffix in _TEXT_LIKE_SUFFIXES:
        with file_path.open(encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise DocumentExtractionError(
        f"No text could be extracted from {file_path} — file may be binary, "
        "image-only, or extraction/transcription failed."
    )


def _extend_segments_from_document(content: Any, segments: list[_Segment]) -> None:
    """Extend *segments* with the text items of a docling document.

    Appends one window's (or the whole document's) text items in document
    order, skipping empty items — the exact loop the historical
    single-conversion path inlined, so windowed and whole-document
    conversions produce identical segment streams.

    Args:
        content: A docling ``DoclingDocument`` (``result.document``).
        segments: Segment list to extend; each entry carries ``"text"``,
            ``"page"``, and optionally ``"label"``.
    """
    if not (hasattr(content, "texts") and content.texts):
        return
    for text_item in content.texts:
        if not hasattr(text_item, "text") or not text_item.text:
            continue
        page_num = 1
        if hasattr(text_item, "prov") and text_item.prov:
            prov = text_item.prov[0]
            if hasattr(prov, "page_no"):
                page_num = prov.page_no
        # prov.page_no is the ABSOLUTE 1-based PDF page index, also under
        # page_range windowing — verified against docling 2.138.0:
        # get_expected_page_nos enumerates
        # range(max(1, start), min(page_count, end) + 1)
        # (docling/pipeline/base_pipeline.py:45-53); iter_pdf_page_backends
        # yields page backends "identified by absolute one-based page number"
        # via load_page(page_no - 1) (docling/backend/pdf_backend.py:166-176);
        # PyPdfiumPageBackend.page_no returns its 0-based absolute index + 1
        # (docling/backend/pypdfium2_backend.py:294-295); the pipeline keys
        # its Page objects by those absolute numbers
        # (docling/pipeline/standard_pdf_pipeline.py:829-834). No
        # window-relative remap is needed.
        segment: _Segment = {"text": text_item.text, "page": page_num}
        label = docling_item_label(text_item)
        if label is not None:
            segment["label"] = label
        segments.append(segment)


# ---------------------------------------------------------------------------
# Converter factory
# ---------------------------------------------------------------------------


def create_converter(file_path: Path) -> DocumentConverter:
    """Create a configured DocumentConverter with automatic device detection.

    Routes through the shared per-document resolver (:func:`get_converter_for_path`)
    so this path honors the same on-demand OCR decision as every other path.

    Lazily imports docling internals. Calling this function incurs the
    docling cold-start cost once; subsequent calls reuse the same process.

    Returns
    -------
        Configured DocumentConverter instance.
    """
    from secondbrain.document.docling_factory import get_converter_for_path

    return get_converter_for_path(file_path)


# ---------------------------------------------------------------------------
# Segment extraction
# ---------------------------------------------------------------------------


def convert_file_to_segments(file_path: Path) -> list[_Segment]:
    """Convert a file to a list of text segments using docling.

    Falls back to plain-text read if docling returns no text items.

    Args:
        file_path: Path to the file to process.

    Returns
    -------
        List of dicts with 'text' and 'page' keys.
    """
    from secondbrain.document.fast_text import try_fast_pdf_extraction

    segments: list[_Segment]
    fast_segments = try_fast_pdf_extraction(file_path)
    if fast_segments is not None:
        return [{"text": s["text"], "page": s["page"]} for s in fast_segments]

    converter = create_converter(file_path)
    result = converter.convert(file_path)
    content = result.document

    segments = []

    if hasattr(content, "texts") and content.texts:
        for text_item in content.texts:
            if not hasattr(text_item, "text") or not text_item.text:
                continue

            page_num = 1
            if hasattr(text_item, "prov") and text_item.prov:
                prov = text_item.prov[0]
                if hasattr(prov, "page_no"):
                    page_num = prov.page_no

            segment: _Segment = {"text": text_item.text, "page": page_num}
            label = docling_item_label(text_item)
            if label is not None:
                segment["label"] = label
            segments.append(segment)

    # Fallback: plain text read
    if not segments:
        with file_path.open(encoding="utf-8", errors="ignore") as f:
            text = f.read()
        segments = [{"text": text, "page": 1}]

    return segments


# ---------------------------------------------------------------------------
# Picklable worker functions for ThreadPoolExecutor
# ---------------------------------------------------------------------------


def _extract_and_chunk_file(
    file_path_str: str, chunk_size: int, chunk_overlap: int
) -> dict[str, Any]:
    """Worker function for threading: extract and chunk a single file.

    This function runs in a separate thread and returns extracted chunks.
    Must be at module level to be picklable for ThreadPoolExecutor.
    Creates its own DocumentConverter instance.

    Args:
        file_path_str: String path to the file to process.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'segments' (list[_Segment]), 'error' (str | None).
    """
    file_path = Path(file_path_str)
    try:
        from secondbrain.document.fast_text import try_fast_pdf_extraction

        segments: list[_Segment]
        fast_segments = try_fast_pdf_extraction(file_path)
        if fast_segments is not None:
            segments = [{"text": s["text"], "page": s["page"]} for s in fast_segments]
        else:
            converter = create_docling_converter(file_path)

            result = converter.convert(file_path)
            content = result.document

            segments = []

            if hasattr(content, "texts") and content.texts:
                for text_item in content.texts:
                    if not hasattr(text_item, "text") or not text_item.text:
                        continue

                    page_num = 1
                    if hasattr(text_item, "prov") and text_item.prov:
                        prov = text_item.prov[0]
                        if hasattr(prov, "page_no"):
                            page_num = prov.page_no

                    segment: _Segment = {"text": text_item.text, "page": page_num}
                    label = docling_item_label(text_item)
                    if label is not None:
                        segment["label"] = label
                    segments.append(segment)

        # Fallback: read file directly for plain text formats
        if not segments:
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                text = f.read()
            segments = [{"text": text, "page": 1}]

        return {
            "success": True,
            "file_path": file_path,
            "segments": segments,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": file_path,
            "segments": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _as_embedding_row(values: Any, dtype: np.dtype[Any]) -> np.ndarray:
    """Coerce one embedding vector into a fixed-width numpy row.

    Embeddings accumulate and travel as fixed-width arrays (per
    ``cfg.embedding_dtype``) instead of Python-float-object lists, bounding
    the worker's accumulation, the worker→parent pickle, and the parent's
    live copy to ~6 KB per 1536-dim chunk instead of ~49 KB. Stored vector
    values are the provider's floats at *dtype* precision.

    Args:
        values: One embedding vector — a sequence of floats (provider batch
            item or embedding-cache hit) or an ndarray.
        dtype: Target numpy dtype derived from ``cfg.embedding_dtype``.

    Returns
    -------
        1-D ndarray of *dtype*; an already-compatible array is returned
        as-is without a copy.
    """
    return np.asarray(values, dtype=dtype)


def _embed_unique_chunks(
    embedding_model: Any,
    unique_chunks: list[dict[str, Any]],
    embedding_cache: EmbeddingCache | None = None,
    batch_size: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[np.ndarray]:
    """Embed a list of unique chunk dicts in batches, optionally reusing a cache.

    Processes ``unique_chunks`` in slices of ``batch_size`` (defaulting to the
    configured ``embedding_batch_size``), calling ``embedding_model.generate_batch``
    once per slice. When ``embedding_cache`` is provided, per-text cache hits are
    reused so the embedder is only invoked for cache misses. The returned list is
    aligned 1:1 (same order, same length) with ``unique_chunks``.

    Every vector is converted to a fixed-width array (``cfg.embedding_dtype``,
    float32) as its batch returns, so the worker's accumulation and the
    worker→parent transport stay compact. The embedding cache keeps storing the
    provider's raw batch items, so cache keys and stored values are unchanged.

    Args:
        embedding_model: Object exposing a ``generate_batch(texts)`` method that
            returns one embedding per input text, in the same order.
        unique_chunks: List of chunk dicts, each containing a ``"text"`` key.
        embedding_cache: Optional thread-safe embedding cache to reuse hits.
        batch_size: Size of each embedder batch. Defaults to the configured
            ``embedding_batch_size``.
        progress_callback: Optional callback ``(done, total)`` invoked after each
            batch completes so callers can report within-file ingestion progress.
            ``total`` is always ``len(unique_chunks)``.

    Returns
    -------
        List of fixed-width numpy arrays of ``cfg.embedding_dtype``, one per
        element of ``unique_chunks``.
    """
    from secondbrain.config import config

    cfg = config()
    if batch_size is None:
        batch_size = cfg.embedding_batch_size
    # Fixed-width transport dtype: cfg.embedding_dtype ("float32") maps to the
    # numpy dtype used for accumulation, transport, and storage. A missing or
    # unrecognized value falls back to float32 — config validation is the gate
    # for accepted values.
    dtype = {"float32": np.dtype("float32")}.get(
        str(getattr(cfg, "embedding_dtype", "float32")), np.dtype("float32")
    )

    texts = [c["text"] for c in unique_chunks]
    embeddings: list[np.ndarray] = []
    processed = 0
    total = len(texts)

    for start in range(0, len(texts), batch_size):
        slice_texts = texts[start : start + batch_size]

        if embedding_cache is None:
            embeddings.extend(
                _as_embedding_row(vec, dtype)
                for vec in embedding_model.generate_batch(slice_texts)
            )
        else:
            batch_results: list[np.ndarray | None] = [None] * len(slice_texts)
            missing_texts: list[str] = []
            missing_slots: list[int] = []

            for index, text in enumerate(slice_texts):
                cached = embedding_cache.get(text)
                if cached is not None:
                    batch_results[index] = _as_embedding_row(cached, dtype)
                else:
                    missing_slots.append(index)
                    missing_texts.append(text)

            if missing_texts:
                missing_embeddings = embedding_model.generate_batch(missing_texts)
                for slot, text, emb in zip(
                    missing_slots, missing_texts, missing_embeddings, strict=True
                ):
                    batch_results[slot] = _as_embedding_row(emb, dtype)
                    # Cache the provider's raw item: keys and stored values
                    # stay unchanged; only the worker's accumulation and
                    # transport switch to the compact array form.
                    embedding_cache.set(text, emb)

            for result in batch_results:
                assert result is not None  # nosec B101
                embeddings.append(result)

        processed += len(slice_texts)
        if progress_callback is not None:
            progress_callback(processed, total)

    return embeddings


def _filter_existing_chunks(
    unique_chunks: list[dict[str, Any]],
    existing_hashes: set[str],
) -> list[dict[str, Any]]:
    """Return chunks whose text_hash is not in existing_hashes, preserving order."""
    if not existing_hashes:
        return unique_chunks
    return [c for c in unique_chunks if c.get("text_hash") not in existing_hashes]


def _existing_text_hashes(hashes: list[str]) -> set[str]:
    """Query storage for which of the given text hashes already exist.

    Degrades gracefully: on any storage/connection error, returns an empty set so
    the caller embeds everything rather than aborting the ingest.
    """
    if not hashes:
        return set()
    try:
        from secondbrain.storage import StorageFactory

        storage = StorageFactory.create_from_config()
        return set(storage.has_existing_hashes(hashes))
    except Exception as e:
        logger.warning(
            "Could not query existing text hashes for re-ingest skip (%s: %s); "
            "proceeding to embed all chunks.",
            type(e).__name__,
            e,
        )
        return set()


def _extract_chunk_and_embed_file(
    file_path_str: str,
    chunk_size: int,
    chunk_overlap: int,
    progress_queue: Any,
    embedding_model_name: str,
    embedding_cache: EmbeddingCache | None = None,
    skip_existing: bool | None = None,
    scrape_docling_pages: bool = False,
) -> dict[str, Any]:
    """Worker function that extracts, chunks, embeds, and reports progress.

    This function runs in a separate thread and returns documents with embeddings.
    All CPU/GPU intensive work (extraction, chunking, embedding) happens in thread.
    Main thread only handles storage.

    In addition to the legacy ("started", "progress", final) queue events, this
    worker emits per-phase ("phase", file_path, phase, done, total) tuples so
    callers can render a phase-aware progress bar:

    - ``"extract"``: ``(0, 0)`` at worker start (indeterminate), then page
      ticks with a known total for PDFs (fast native extraction and, when
      ``scrape_docling_pages`` is set, scraped docling page batches; under
      page-window conversion the scraped ticks are rebased per window so
      they advance continuously across window boundaries).
    - ``"chunk"``: ``(0, 1)`` just before, ``(1, 1)`` right after chunking.
    - ``"embed"``: per embedding batch with ``total = len(unique_chunks)``.

    Args:
        file_path_str: String path to the file to process.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        progress_queue: Thread-safe Queue for progress updates.
        embedding_model_name: Name of embedding model to use.
        embedding_cache: Optional shared thread-safe embedding cache to reuse
            embeddings across files (deduplicates redundant API calls).
        skip_existing: If True, drop chunks whose text_hash already exists in
            storage before embedding, so unchanged content is neither re-embedded
            nor re-stored. If None, falls back to config().skip_existing_on_reingest.
        scrape_docling_pages: If True and *progress_queue* is set, scrape
            docling's per-page-batch DEBUG log for "extract" phase ticks
            during ``converter.convert()``. Only enable for single-thread
            executors or process pools (one conversion per process): the
            scraper mutates a shared process-wide logger's level, so a
            multi-worker thread pool would cross-contaminate concurrent
            conversions.

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'documents' (list[dict]), 'error' (str | None). When nothing is
        stored, 'skipped' distinguishes a legitimate re-ingest skip (True,
        with 'extracted_chunks' counting the chunks that were extracted) from
        a failed extraction with no text at all (reported as success=False).
    """
    import contextlib
    import gc
    from datetime import UTC, datetime
    from uuid import uuid4

    from secondbrain.config import config
    from secondbrain.embedding import EmbeddingProviderFactory

    file_path = Path(file_path_str)
    try:
        import logging as _logging

        _logging.getLogger("RapidOCR").setLevel(_logging.ERROR)
        _logging.getLogger("docling").setLevel(_logging.WARNING)

        from secondbrain.document.docling_factory import get_converter_for_path
        from secondbrain.document.fast_text import try_fast_pdf_extraction

        def _emit_phase(phase: str, done: int, total: int) -> None:
            """Queue one ("phase", ...) tuple; never raises.

            Failures (hostile/full/closed queues) are suppressed exactly like
            the legacy progress events so a progress hiccup cannot kill the
            worker.
            """
            if progress_queue is None:
                return
            with contextlib.suppress(Exception):
                progress_queue.put_nowait(("phase", str(file_path), phase, done, total))

        def _emit_extract(done: int, total: int) -> None:
            """Forward fast/docling page progress into the extract phase."""
            _emit_phase("extract", done, total)

        # Signal extraction has begun; total=0 marks the indeterminate state
        # until a page count (PDF) or a first batch tick provides one.
        _emit_phase("extract", 0, 0)

        segments: list[_Segment]
        fast_segments = try_fast_pdf_extraction(file_path, page_progress=_emit_extract)
        if fast_segments is not None:
            with trace_operation("extract_fast_text"):
                segments = [
                    {"text": s["text"], "page": s["page"]} for s in fast_segments
                ]
        else:
            # Native extraction may have reported completion before deciding
            # this PDF needs the slower Docling fallback.
            _emit_phase("extract", 0, 0)
            with trace_operation("ingest_worker_extract") as span:
                if span is not None:
                    span.set_attribute(
                        "ingest.filesize_bytes", file_path.stat().st_size
                    )
                converter = get_converter_for_path(file_path)

                # One page count, shared by windowing and — when enabled —
                # the docling DEBUG page-batch scraper. 0 means unknown
                # (non-PDF or unreadable), which keeps the whole-document
                # conversion.
                is_pdf = file_path.suffix.lower() == ".pdf"
                total_pages = pdf_page_count(file_path) if is_pdf else 0
                # Window setting from config (0 disables windowing); the
                # getattr default mirrors the config default (200) so stub
                # configs without the field keep working.
                max_convert_pages = int(
                    getattr(config(), "pdf_max_pages_per_convert", 200)
                )
                use_windows = 0 < max_convert_pages < total_pages

                # Sequential, non-overlapping 1-based inclusive page ranges
                # covering every page exactly once (window count =
                # ceil(pages / window)); a whole-document conversion is the
                # single-element case, exactly the historical path.
                windows: list[tuple[int, int] | None] = [None]
                if use_windows:
                    windows = [
                        (start, min(start + max_convert_pages - 1, total_pages))
                        for start in range(1, total_pages + 1, max_convert_pages)
                    ]

                segments = []

                def _convert_one(window: tuple[int, int] | None) -> None:
                    """Convert one page window (or the whole file) and release it.

                    Extends *segments* from the conversion result, then
                    releases all conversion artifacts. Mirrors docling's own
                    release pattern (``DocumentConverter._unload_input_document``,
                    docling #2209): the backend page state is unloaded and the
                    ``ConversionResult``/``DoclingDocument`` references are
                    dropped before the next window, so peak memory no longer
                    grows with page count. Release failures never fail the
                    extraction.
                    """
                    result = (
                        converter.convert(file_path, page_range=window)
                        if window is not None
                        else converter.convert(file_path)
                    )
                    _extend_segments_from_document(result.document, segments)
                    backend = getattr(getattr(result, "input", None), "_backend", None)
                    if backend is not None and hasattr(backend, "unload"):
                        with contextlib.suppress(Exception):
                            backend.unload()
                    del result
                    gc.collect()

                if scrape_docling_pages and progress_queue is not None:
                    # Docling has no progress callback API; the per-page-batch
                    # DEBUG log on base_pipeline is the only in-band signal.
                    # see secondbrain.document.docling_progress for the why.
                    if total_pages:
                        _emit_extract(0, total_pages)
                    window_offset = [0]

                    def _scraped_page_tick(done: int, total: int) -> None:
                        # The scraper's counters are per convert() call: done
                        # counts pages inside the current conversion and
                        # total is that conversion's page count only. Rebase
                        # done against the pages already converted in earlier
                        # windows and report against the real page count so
                        # the CLI progress bar advances continuously across
                        # window boundaries.
                        _emit_extract(done + window_offset[0], total_pages)

                    on_page_batch: Callable[[int, int], None] = (
                        _scraped_page_tick if use_windows else _emit_extract
                    )
                    with scraped_page_progress(on_page_batch):
                        for window in windows:
                            if window is not None:
                                window_offset[0] = window[0] - 1
                            _convert_one(window)
                else:
                    for window in windows:
                        _convert_one(window)

                if not _segments_have_text(segments):
                    segments = [{"text": _fallback_text_or_raise(file_path), "page": 1}]

        from secondbrain.document.ingestor._sync import _warn_if_glued_text

        segments = _warn_if_glued_text(file_path, segments)
        _emit_phase("chunk", 0, 1)
        with trace_operation("ingest_worker_chunk") as span:
            if span is not None:
                span.set_attribute("ingest.segments_count", len(segments))
            chunks = chunk_segments(segments, chunk_size, chunk_overlap)
        _emit_phase("chunk", 1, 1)
        extracted_chunk_count = len(chunks)

        cfg = config()
        embedding_model = EmbeddingProviderFactory.create_from_config(cfg)

        seen_hashes = set()
        unique_chunks: list[dict[str, Any]] = []
        for chunk in chunks:
            cleaned = chunk["text"].strip()
            if not cleaned:
                continue
            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                unique_chunks.append(
                    {
                        "text": cleaned,
                        "page": chunk["page"],
                        "text_hash": text_hash,
                        "chunk_role": chunk.get("chunk_role", "body"),
                        "element_type": chunk.get("element_type", "body"),
                    }
                )

        if skip_existing is None:
            skip_existing = cfg.skip_existing_on_reingest
        if skip_existing:
            try:
                existing_hashes = _existing_text_hashes(
                    [c["text_hash"] for c in unique_chunks]
                )
                unique_chunks = _filter_existing_chunks(unique_chunks, existing_hashes)
            except Exception:
                logger.warning(
                    "Re-ingest skip lookup failed for %s; embedding all chunks.",
                    file_path,
                )

        if not unique_chunks:
            if extracted_chunk_count == 0:
                # Nothing was ever extracted: a silent success here would
                # report the file as ingested while it contributed no text.
                return {
                    "success": False,
                    "file_path": file_path,
                    "documents": [],
                    "error": (
                        f"No text extracted from {file_path} "
                        "(empty file or failed extraction/transcription)"
                    ),
                    "skipped": False,
                }
            # Chunks were extracted but all deduplicated away (whitespace-only
            # chunks, duplicates, or all already stored) — a legitimate skip.
            return {
                "success": True,
                "file_path": file_path,
                "documents": [],
                "error": None,
                "skipped": True,
                "extracted_chunks": extracted_chunk_count,
            }

        # Signal ingestion of this file has begun (with its total chunk count) so
        # the CLI can render a determinate per-file progress bar.
        if progress_queue is not None:
            with contextlib.suppress(Exception):
                progress_queue.put_nowait(
                    ("started", str(file_path), len(unique_chunks))
                )

        def _report_chunk_progress(done: int, total: int) -> None:
            if progress_queue is None:
                return
            # Legacy within-file embed progress (kept for backward compat)…
            with contextlib.suppress(Exception):
                progress_queue.put_nowait(("progress", str(file_path), done, total))
            # …plus the new per-phase embed tick with the same numbers.
            with contextlib.suppress(Exception):
                progress_queue.put_nowait(
                    ("phase", str(file_path), "embed", done, total)
                )

        _emit_phase("embed", 0, len(unique_chunks))
        with trace_operation("ingest_worker_embed") as span:
            if span is not None:
                span.set_attribute("ingest.chunks_count", len(unique_chunks))
            embeddings = _embed_unique_chunks(
                embedding_model,
                unique_chunks,
                embedding_cache=embedding_cache,
                progress_callback=_report_chunk_progress,
            )

        documents = []

        # Determine file_type from extension (mirrors document/__init__.py:get_file_type)
        ext = file_path.suffix.lower()
        _type_map: dict[str, str] = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".pptx": "pptx",
            ".xlsx": "xlsx",
            ".html": "html",
            ".htm": "html",
            ".md": "markdown",
            ".txt": "text",
            ".asciidoc": "asciidoc",
            ".adoc": "asciidoc",
            ".tex": "latex",
            ".csv": "csv",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".tiff": "image",
            ".tif": "image",
            ".bmp": "image",
            ".webp": "image",
            ".wav": "audio",
            ".mp3": "audio",
            ".m4a": "audio",
            ".aac": "audio",
            ".ogg": "audio",
            ".flac": "audio",
            ".vtt": "webvtt",
            ".xml": "xml",
            ".json": "docling-json",
        }
        file_type = _type_map.get(ext, "unknown")

        ingested_at = datetime.now(UTC).isoformat()

        page_pos = 0
        last_page: int | None = None
        for chunk_item, embedding in zip(unique_chunks, embeddings, strict=True):
            page = chunk_item["page"]
            if page != last_page:
                page_pos = 0
                last_page = page
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(file_path),
                "page_number": page,
                "printed_page": extract_printed_page(chunk_item["text"]),
                "page_pos": page_pos,
                "chunk_text": chunk_item["text"],
                "text_hash": chunk_item["text_hash"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
                "chunk_role": chunk_item.get("chunk_role", "body"),
                "element_type": chunk_item.get("element_type", "body"),
            }
            documents.append(doc)
            page_pos += 1

        setup_pages = resolve_printed_pages(documents)
        if setup_pages:
            logger.debug(
                "Footer page stamps: %d physical pages stamped for %s",
                setup_pages,
                file_path,
            )

        if progress_queue is not None:
            with contextlib.suppress(Exception):
                progress_queue.put_nowait((str(file_path), len(documents) > 0))

        return {
            "success": True,
            "file_path": file_path,
            "documents": documents,
            "error": None,
            "skipped": False,
        }
    except Exception as e:
        if progress_queue is not None:
            with contextlib.suppress(Exception):
                progress_queue.put_nowait((str(file_path), False))
        return {
            "success": False,
            "file_path": file_path,
            "documents": [],
            "error": f"{type(e).__name__}: {e}",
        }
