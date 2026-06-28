"""Worker functions for threaded document extraction and embedding.

These functions are exported for use by the DocumentIngestor's parallel
processing methods. They must remain at module level to be picklable
for ThreadPoolExecutor.

Exports:
    _extract_and_chunk_file: Worker for threading - extract and chunk a single file.
    _extract_chunk_and_embed_file: Worker that extracts, chunks, embeds, and reports progress.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from secondbrain.document.protocols import Segment

# Configure logging suppressions for docling subprocesses
_log = logging.getLogger("RapidOCR")
_log.setLevel(logging.ERROR)
_log = logging.getLogger("docling")
_log.setLevel(logging.WARNING)


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
        'chunks' (list[Segment]), 'error' (str | None).
    """
    file_path = Path(file_path_str)
    try:
        import logging as _log

        _log.getLogger("RapidOCR").setLevel(_log.ERROR)
        _log.getLogger("docling").setLevel(_log.WARNING)

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

        # Extract segments from document (don't chunk yet - let main process handle streaming)
        segments: list[Segment] = []

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
            "segments": segments,  # Return segments, not chunks
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
    # Import chunker here to avoid circular imports at module load time
    from secondbrain.document.chunker import _chunk_segments

    file_path = Path(file_path_str)
    try:
        import logging

        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        logging.getLogger("docling").setLevel(logging.WARNING)

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

        segments: list[Segment] = []
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

        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        from secondbrain.config import config

        cfg = config()
        from secondbrain.embedding import EmbeddingProviderFactory

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
            embeddings = embedding_model.generate_batch(texts)
        else:
            embeddings = []

        from datetime import UTC, datetime
        from uuid import uuid4

        documents = []
        from secondbrain.document import get_file_type

        file_type = get_file_type(file_path)
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
            import contextlib

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
            import contextlib

            with contextlib.suppress(Exception):
                progress_queue.put_nowait((str(file_path), False))
        return {
            "success": False,
            "file_path": file_path,
            "documents": [],
            "error": f"{type(e).__name__}: {e}",
        }
