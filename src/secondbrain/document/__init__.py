"""Document ingestion and processing for secondbrain.

Public exports re-exported from submodules for backward compatibility.

Public API:
- DocumentIngestor: Main class for ingesting documents
- AsyncDocumentIngestor: Async version of the ingestor
- Segment: TypedDict for text segments with page info
- is_supported: Check if file type is supported
- get_file_type: Get file type category string
- SUPPORTED_EXTENSIONS: Set of supported file extensions
"""

from __future__ import annotations

# Re-export config so patches like `patch("secondbrain.document.config")` still work
from secondbrain.config import config

# Re-export Segment from protocols so existing importers are unaffected
from secondbrain.document.chunker import (
    _chunk_segments,
    chunk_segments,
    deduplicate_segments,
    docling_item_label,
    label_to_element_type,
)
from secondbrain.document.ingestor import (
    SUPPORTED_EXTENSIONS,
    AsyncDocumentIngestor,
    DocumentIngestor,
    get_file_type,
    is_supported,
)

# Re-export worker functions from processor (the live consumer uses these)
from secondbrain.document.processor import (
    _extract_and_chunk_file,
    _extract_chunk_and_embed_file,
)
from secondbrain.document.protocols import Segment

# Re-export exceptions that were previously in this module
from secondbrain.exceptions import (
    DocumentExtractionError,
    UnsupportedFileError,
)

# Memory management constant (was previously in __init__.py directly)
MAX_MEMORY_BATCH_SIZE = 100

# NOTE: The transformers MPS patch is applied by the docling factory on the
# converter's first pipeline initialization (see
# ``docling_factory._install_pdf_conversion_hooks``), not at import time —
# this keeps torch/transformers out of the import path entirely.


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "AsyncDocumentIngestor",
    "DocumentExtractionError",
    "DocumentIngestor",
    "Segment",
    "UnsupportedFileError",
    "config",
    "get_file_type",
    "is_supported",
]
