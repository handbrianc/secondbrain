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
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from secondbrain.utils.embedding_cache import EmbeddingCache

# Apply MPS patch before any docling import
from secondbrain.document.chunker import classify_chunk_role
from secondbrain.utils.mps_patch import patch_transformers_for_mps
from secondbrain.utils.tracing import trace_operation

patch_transformers_for_mps()

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
    converter = create_converter(file_path)
    result = converter.convert(file_path)
    content = result.document

    segments: list[_Segment] = []

    if hasattr(content, "texts") and content.texts:
        for text_item in content.texts:
            if not hasattr(text_item, "text") or not text_item.text:
                continue

            page_num = 1
            if hasattr(text_item, "prov") and text_item.prov:
                prov = text_item.prov[0]
                if hasattr(prov, "page_no"):
                    page_num = prov.page_no

            segments.append({"text": text_item.text, "page": page_num})

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
        converter = create_docling_converter(file_path)

        result = converter.convert(file_path)
        content = result.document

        segments: list[_Segment] = []

        if hasattr(content, "texts") and content.texts:
            for text_item in content.texts:
                if not hasattr(text_item, "text") or not text_item.text:
                    continue

                page_num = 1
                if hasattr(text_item, "prov") and text_item.prov:
                    prov = text_item.prov[0]
                    if hasattr(prov, "page_no"):
                        page_num = prov.page_no

                segments.append({"text": text_item.text, "page": page_num})

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


def _embed_unique_chunks(
    embedding_model: Any,
    unique_chunks: list[dict[str, Any]],
    embedding_cache: EmbeddingCache | None = None,
    batch_size: int | None = None,
) -> list[list[float]]:
    """Embed a list of unique chunk dicts in batches, optionally reusing a cache.

    Processes ``unique_chunks`` in slices of ``batch_size`` (defaulting to the
    configured ``embedding_batch_size``), calling ``embedding_model.generate_batch``
    once per slice. When ``embedding_cache`` is provided, per-text cache hits are
    reused so the embedder is only invoked for cache misses. The returned list is
    aligned 1:1 (same order, same length) with ``unique_chunks``.

    Args:
        embedding_model: Object exposing a ``generate_batch(texts)`` method that
            returns one embedding per input text, in the same order.
        unique_chunks: List of chunk dicts, each containing a ``"text"`` key.
        embedding_cache: Optional thread-safe embedding cache to reuse hits.
        batch_size: Size of each embedder batch. Defaults to the configured
            ``embedding_batch_size``.

    Returns
    -------
        List of embedding vectors, one per element of ``unique_chunks``.
    """
    if batch_size is None:
        from secondbrain.config import config

        batch_size = config().embedding_batch_size

    texts = [c["text"] for c in unique_chunks]
    embeddings: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        slice_texts = texts[start : start + batch_size]

        if embedding_cache is None:
            embeddings.extend(embedding_model.generate_batch(slice_texts))
            continue

        batch_results: list[list[float] | None] = [None] * len(slice_texts)
        missing_texts: list[str] = []
        missing_slots: list[int] = []

        for index, text in enumerate(slice_texts):
            cached = embedding_cache.get(text)
            if cached is not None:
                batch_results[index] = cached
            else:
                missing_slots.append(index)
                missing_texts.append(text)

        if missing_texts:
            missing_embeddings = embedding_model.generate_batch(missing_texts)
            for slot, text, emb in zip(
                missing_slots, missing_texts, missing_embeddings, strict=True
            ):
                batch_results[slot] = emb
                embedding_cache.set(text, emb)

        for result in batch_results:
            assert result is not None
            embeddings.append(result)

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
        from secondbrain.storage import VectorStorage

        storage = VectorStorage()
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
) -> dict[str, Any]:
    """Worker function that extracts, chunks, embeds, and reports progress.

    This function runs in a separate thread and returns documents with embeddings.
    All CPU/GPU intensive work (extraction, chunking, embedding) happens in thread.
    Main thread only handles storage.

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

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'documents' (list[dict]), 'error' (str | None).
    """
    import contextlib
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

        with trace_operation("ingest_worker_extract") as span:
            if span is not None:
                span.set_attribute("ingest.filesize_bytes", file_path.stat().st_size)
            converter = get_converter_for_path(file_path)

            result = converter.convert(file_path)
            content = result.document

            segments: list[_Segment] = []
            if hasattr(content, "texts") and content.texts:
                for text_item in content.texts:
                    if not hasattr(text_item, "text") or not text_item.text:
                        continue
                    page_num = 1
                    if hasattr(text_item, "prov") and text_item.prov:
                        prov = text_item.prov[0]
                        if hasattr(prov, "page_no"):
                            page_num = prov.page_no
                    segments.append({"text": text_item.text, "page": page_num})

            if not segments:
                with file_path.open(encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                segments = [{"text": text, "page": 1}]

        # NOTE: chunk_segments is imported here to avoid circular dep at module init
        # (chunker is in a sibling module)
        #
        # Inline the chunking logic rather than importing to keep workers self-contained.
        # When _chunk_segments moves to chunker.py, replace this inline with:
        #   from secondbrain.document.chunker import chunk_segments
        #   chunks = chunk_segments(segments, chunk_size, chunk_overlap)
        #
        # Inline minimal chunker for this worker only — not exported from this module.
        with trace_operation("ingest_worker_chunk") as span:
            if span is not None:
                span.set_attribute("ingest.segments_count", len(segments))
            min_segment_size = 200
            merged_segments: list[_Segment] = []
            current_text = ""
            current_page = 0

            for _i, segment in enumerate(segments):
                text = segment["text"]
                page = segment.get("page", 0)
                if not text.strip():
                    continue
                stripped = text.strip()
                is_likely_title = (
                    len(stripped) < 100
                    and not any(p in stripped for p in [".", ":", "-", "—"])
                    and not stripped.endswith(".")
                )
                if len(current_text) < min_segment_size or is_likely_title:
                    if current_text:
                        current_text += " " + stripped
                    else:
                        current_text = stripped
                    current_page = page
                else:
                    merged_segments.append({"text": current_text, "page": current_page})
                    current_text = stripped
                    current_page = page

            if current_text:
                merged_segments.append({"text": current_text, "page": current_page})

            chunks: list[dict[str, Any]] = []
            total_segs = len(merged_segments)
            seg_counter = 0
            for segment in merged_segments:
                text = segment["text"]
                page = segment.get("page", 0)
                if not text.strip():
                    continue
                is_likely_title_for_seg = (
                    len(text.strip()) < 100
                    and not any(p in text.strip() for p in [".", ":", "-", "—"])
                    and not text.strip().endswith(".")
                )
                start = 0
                while start < len(text):
                    if start + chunk_size >= len(text):
                        chunk_text = text[start:].rstrip()
                        if chunk_text:
                            chunks.append(
                                {
                                    "text": chunk_text,
                                    "page": page,
                                    "chunk_role": classify_chunk_role(
                                        chunk_text,
                                        seg_counter,
                                        total_segs,
                                        is_likely_title_for_seg,
                                    ),
                                }
                            )
                        seg_counter += 1
                        break
                    next_start = start + chunk_size
                    chunk_end = next_start
                    last_space = text.rfind(" ", start, chunk_end)
                    if last_space > start:
                        chunk_end = last_space
                    chunk_text = text[start:chunk_end]
                    if chunk_text.strip():
                        chunks.append(
                            {
                                "text": chunk_text,
                                "page": page,
                                "chunk_role": classify_chunk_role(
                                    chunk_text,
                                    seg_counter,
                                    total_segs,
                                    is_likely_title_for_seg,
                                ),
                            }
                        )
                        seg_counter += 1
                    new_start = chunk_end - chunk_overlap
                    start = chunk_end if new_start <= start else new_start

        cfg = config()
        embedding_model = EmbeddingProviderFactory.create_from_config(cfg)

        seen_hashes = set()
        unique_chunks = []
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
            return {
                "success": True,
                "file_path": file_path,
                "documents": [],
                "error": None,
                "skipped": True,
            }

        with trace_operation("ingest_worker_embed") as span:
            if span is not None:
                span.set_attribute("ingest.chunks_count", len(unique_chunks))
            embeddings = _embed_unique_chunks(
                embedding_model, unique_chunks, embedding_cache=embedding_cache
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
            ".vtt": "webvtt",
            ".xml": "xml",
            ".json": "docling-json",
        }
        file_type = _type_map.get(ext, "unknown")

        ingested_at = datetime.now(UTC).isoformat()

        for chunk_item, embedding in zip(unique_chunks, embeddings, strict=True):
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(file_path),
                "page_number": chunk_item["page"],
                "chunk_text": chunk_item["text"],
                "text_hash": chunk_item["text_hash"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
                "chunk_role": chunk_item.get("chunk_role", "body"),
            }
            documents.append(doc)

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
