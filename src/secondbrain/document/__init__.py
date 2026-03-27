"""Document ingestion and processing for secondbrain.

This module provides:
- DocumentIngestor: Main class for ingesting documents
- AsyncDocumentIngestor: Async version for non-blocking ingestion
- Segment: TypedDict for text segments with page info
- is_supported: Check if file type is supported
- get_file_type: Get file type category string
"""

from __future__ import annotations

from typing import Any

from secondbrain.config import get_config
from secondbrain.document.async_ingestor import AsyncDocumentIngestor
from secondbrain.document.ingestor import MAX_MEMORY_BATCH_SIZE, DocumentIngestor
from secondbrain.document.segment import Segment, chunk_segments
from secondbrain.document.utils import SUPPORTED_EXTENSIONS, get_file_type, is_supported
from secondbrain.document.worker import (
    extract_and_chunk_file,
    extract_chunk_and_embed_file,
    init_worker,
    init_worker_with_queue,
)
from secondbrain.exceptions import DocumentExtractionError, UnsupportedFileError

# Internal exports for testing (underscore-prefixed for backward compatibility)
_chunk_segments = chunk_segments
_extract_and_chunk_file = extract_and_chunk_file
_extract_and_chunk_file.__module__ = "secondbrain.document"
_extract_chunk_and_embed_file = extract_chunk_and_embed_file
from secondbrain.document.worker import (  # noqa: E402
    extract_and_chunk_file_with_progress as _extract_and_chunk_file_with_progress,
)

# Module-level globals for worker processes (for backward compatibility with tests)
_worker_converter: Any = None
_worker_progress_queue: Any = None
_worker_embedding_model: Any = None


def _init_worker() -> None:
    """Initialize worker process with DocumentConverter."""
    global _worker_converter
    from docling.document_converter import DocumentConverter

    _worker_converter = DocumentConverter()


def _init_worker_with_queue(
    queue: Any, embedding_model_name: str, num_workers: int
) -> None:
    """Initialize worker process with DocumentConverter, progress queue, and embedding model."""
    global _worker_converter, _worker_progress_queue, _worker_embedding_model
    import os

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


__all__ = [
    "MAX_MEMORY_BATCH_SIZE",
    "SUPPORTED_EXTENSIONS",
    "AsyncDocumentIngestor",
    "DocumentExtractionError",
    "DocumentIngestor",
    "Segment",
    "UnsupportedFileError",
    "_chunk_segments",
    "_extract_and_chunk_file",
    "_extract_and_chunk_file_with_progress",
    "_extract_chunk_and_embed_file",
    "_init_worker",
    "_init_worker_with_queue",
    "_worker_converter",
    "_worker_embedding_model",
    "_worker_progress_queue",
    "chunk_segments",
    "extract_and_chunk_file",
    "extract_chunk_and_embed_file",
    "get_config",
    "get_file_type",
    "init_worker",
    "init_worker_with_queue",
    "is_supported",
]
