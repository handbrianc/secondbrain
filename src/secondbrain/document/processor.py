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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import TypedDict

# Apply MPS patch before any docling import
from secondbrain.utils.mps_patch import patch_transformers_for_mps

patch_transformers_for_mps()


def create_docling_converter() -> "DocumentConverter":  # noqa: UP037
    """Create a configured DocumentConverter supporting all docling formats.

    Returns a converter pre-configured with:
    - PDF: OCR enabled, CPU-accelerated, table structure disabled
    - All other formats use docling defaults

    Factory exists to centralize format configuration and avoid bare
    DocumentConverter() instantiations that miss format options.
    """
    import logging as _logging

    _logging.getLogger("RapidOCR").setLevel(_logging.ERROR)
    _logging.getLogger("docling").setLevel(_logging.WARNING)

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfFormatOption(
        pipeline_options=PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=False,
            accelerator_options=AcceleratorOptions(
                device=AcceleratorDevice.CPU, num_threads=4
            ),
        )
    )
    return DocumentConverter(format_options={InputFormat.PDF: pdf_options})


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


def create_converter() -> DocumentConverter:
    """Create a configured DocumentConverter with CPU acceleration.

    Lazily imports docling internals. Calling this function incurs the
    docling cold-start cost once; subsequent calls reuse the same process.

    Returns
    -------
        Configured DocumentConverter instance.
    """
    import logging as _logging

    _logging.getLogger("RapidOCR").setLevel(_logging.ERROR)
    _logging.getLogger("docling").setLevel(_logging.WARNING)

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfFormatOption(
        pipeline_options=PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=False,
            accelerator_options=AcceleratorOptions(
                device=AcceleratorDevice.CPU, num_threads=4
            ),
        )
    )
    return DocumentConverter(format_options={InputFormat.PDF: pdf_options})


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
    converter = create_converter()
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
        converter = create_docling_converter()

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


def _extract_chunk_and_embed_file(
    file_path_str: str,
    chunk_size: int,
    chunk_overlap: int,
    progress_queue: Any,
    embedding_model_name: str,
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

        from docling.datamodel.accelerator_options import (
            AcceleratorDevice,
            AcceleratorOptions,
        )
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pdf_options = PdfFormatOption(
            pipeline_options=PdfPipelineOptions(
                do_ocr=True,
                do_table_structure=False,
                accelerator_options=AcceleratorOptions(
                    device=AcceleratorDevice.CPU, num_threads=4
                ),
            )
        )
        converter = DocumentConverter(format_options={InputFormat.PDF: pdf_options})

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
        MIN_SEGMENT_SIZE = 200
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
            if len(current_text) < MIN_SEGMENT_SIZE or is_likely_title:
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

        chunks: list[_Segment] = []
        for segment in merged_segments:
            text = segment["text"]
            page = segment.get("page", 0)
            if not text.strip():
                continue
            start = 0
            while start < len(text):
                if start + chunk_size >= len(text):
                    chunk_text = text[start:].rstrip()
                    if chunk_text:
                        chunks.append({"text": chunk_text, "page": page})
                    break
                next_start = start + chunk_size
                chunk_end = next_start
                last_space = text.rfind(" ", start, chunk_end)
                if last_space > start:
                    chunk_end = last_space
                chunk_text = text[start:chunk_end]
                if chunk_text.strip():
                    chunks.append({"text": chunk_text, "page": page})
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
                    }
                )

        if unique_chunks:
            texts = [c["text"] for c in unique_chunks]
            # Suppress mypy error: EmbeddingProviderFactory.create_from_config resolved dynamically
            embeddings = embedding_model.generate_batch(texts)
        else:
            embeddings = []

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
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
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
