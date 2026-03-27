"""Worker process functions for multiprocessing document processing."""

from __future__ import annotations

import contextlib
import hashlib
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from secondbrain.document.segment import chunk_segments
from secondbrain.document.utils import get_file_type

warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)

_worker_converter: Any = None
_worker_progress_queue: Any = None
_worker_embedding_model: Any = None


def init_worker() -> None:
    """Initialize worker process with DocumentConverter."""
    global _worker_converter
    from docling.document_converter import DocumentConverter

    _worker_converter = DocumentConverter()


def init_worker_with_queue(
    queue: Any, embedding_model_name: str, num_workers: int
) -> None:
    """Initialize worker process with DocumentConverter, progress queue, and embedding model."""
    global _worker_converter, _worker_progress_queue, _worker_embedding_model

    total_cores = os.cpu_count() or 4
    threads_per_worker = max(1, total_cores // num_workers)

    try:
        import torch

        torch.set_num_threads(threads_per_worker)
    except ImportError:
        pass

    os.environ["OMP_NUM_THREADS"] = str(threads_per_worker)
    os.environ["MKL_NUM_THREADS"] = str(threads_per_worker)

    from docling.document_converter import DocumentConverter

    from secondbrain.embedding.local import LocalEmbeddingGenerator

    _worker_converter = DocumentConverter()
    _worker_progress_queue = queue
    _worker_embedding_model = LocalEmbeddingGenerator(model_name=embedding_model_name)


def get_worker_converter() -> Any:
    """Get the worker's DocumentConverter instance."""
    return _worker_converter


def get_worker_progress_queue() -> Any:
    """Get the worker's progress queue."""
    return _worker_progress_queue


def get_worker_embedding_model() -> Any:
    """Get the worker's embedding model."""
    return _worker_embedding_model


def send_progress_update(file_path: str, success: bool) -> None:
    """Send progress update to the main process via queue."""
    if _worker_progress_queue is not None:
        with contextlib.suppress(Exception):
            _worker_progress_queue.put_nowait((file_path, success))


__all__ = ["extract_and_chunk_file", "extract_and_chunk_file_with_progress", "extract_chunk_and_embed_file", "get_worker_converter", "get_worker_embedding_model", "get_worker_progress_queue", "init_worker", "init_worker_with_queue", "send_progress_update"]

def extract_and_chunk_file(
    file_path_str: str, chunk_size: int, chunk_overlap: int
) -> dict[str, Any]:
    """Worker function for multiprocessing: extract and chunk a single file."""
    from secondbrain.document.segment import Segment

    file_path = Path(file_path_str)
    try:
        converter = get_worker_converter()
        if converter is None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()

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

        if chunk_size > 0:
            chunks = chunk_segments(segments, chunk_size, chunk_overlap)
        else:
            chunks = segments

        return {
            "success": True,
            "file_path": file_path,
            "segments": chunks,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": file_path,
            "segments": [],
            "error": f"{type(e).__name__}: {e}",
        }


def extract_chunk_and_embed_file(
    file_path_str: str,
    chunk_size: int,
    chunk_overlap: int,
    progress_queue: Any,
    embedding_model_name: str,
) -> dict[str, Any]:
    """Worker function that extracts, chunks, embeds, and reports progress."""
    file_path = Path(file_path_str)
    try:
        converter = get_worker_converter()
        if converter is None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()

        result = converter.convert(file_path)
        content = result.document

        segments: list[dict[str, Any]] = []
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

        chunks = chunk_segments(
            [{"text": s["text"], "page": s["page"]} for s in segments],
            chunk_size,
            chunk_overlap,
        )

        embedding_model = get_worker_embedding_model()
        if embedding_model is None:
            from secondbrain.embedding.local import LocalEmbeddingGenerator

            embedding_model = LocalEmbeddingGenerator(model_name=embedding_model_name)

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
                    {"text": cleaned, "page": chunk["page"], "text_hash": text_hash}
                )

        if unique_chunks:
            texts = [c["text"] for c in unique_chunks]
            embeddings = embedding_model.generate_batch(texts)
        else:
            embeddings = []

        documents = []
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

        send_progress_update(str(file_path), len(documents) > 0)

        return {
            "success": True,
            "file_path": file_path,
            "documents": documents,
            "error": None,
        }
    except Exception as e:
        send_progress_update(str(file_path), False)
        return {
            "success": False,
            "file_path": file_path,
            "documents": [],
            "error": f"{type(e).__name__}: {e}",
        }


__all__ = ["extract_and_chunk_file", "extract_and_chunk_file_with_progress", "extract_chunk_and_embed_file", "get_worker_converter", "get_worker_embedding_model", "get_worker_progress_queue", "init_worker", "init_worker_with_queue", "send_progress_update"]

def extract_and_chunk_file_with_progress(
    file_path_str: str, chunk_size: int, chunk_overlap: int, progress_queue: Any
) -> dict[str, Any]:
    """Worker function that extracts and chunks with progress reporting.

    This is similar to extract_and_chunk_file but sends progress updates
    to the main process via the queue.
    """
    result = extract_and_chunk_file(file_path_str, chunk_size, chunk_overlap)

    # Send progress update
    if progress_queue is not None and result.get("success"):
        with contextlib.suppress(Exception):
            progress_queue.put_nowait((file_path_str, True))

    return result
