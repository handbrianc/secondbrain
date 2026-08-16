"""Document ingestion pipeline.

Splits the ingestor into:
- ``_constants``: pure helpers, constants, and file-type detection
- ``_sync``: synchronous :class:`DocumentIngestor`
- ``_async``: asynchronous :class:`AsyncDocumentIngestor`

This module re-exports the public API so ``secondbrain.document.ingestor``
(and consumers importing from it) keep working unchanged.
"""

from secondbrain.document.ingestor._async import AsyncDocumentIngestor
from secondbrain.document.ingestor._constants import (
    MAX_MEMORY_BATCH_SIZE,
    SUPPORTED_EXTENSIONS,
    get_file_type,
    is_supported,
)
from secondbrain.document.ingestor._sync import DocumentIngestor

__all__ = [
    "MAX_MEMORY_BATCH_SIZE",
    "SUPPORTED_EXTENSIONS",
    "AsyncDocumentIngestor",
    "DocumentIngestor",
    "get_file_type",
    "is_supported",
]
