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
)
from secondbrain.document.extractor import (
    _extract_and_chunk_file,
    _extract_chunk_and_embed_file,
)
from secondbrain.document.ingestor import (
    SUPPORTED_EXTENSIONS,
    AsyncDocumentIngestor,
    DocumentIngestor,
    get_file_type,
    is_supported,
)
from secondbrain.document.protocols import Segment

# Re-export exceptions that were previously in this module
from secondbrain.exceptions import (
    DocumentExtractionError,
    UnsupportedFileError,
)

# Memory management constant (was previously in __init__.py directly)
MAX_MEMORY_BATCH_SIZE = 100


# Deferred MPS patch — avoids import side-effect at module load time
def _deferred_patch_transformers() -> None:
    if not hasattr(_deferred_patch_transformers, "_applied"):
        from secondbrain.utils.mps_patch import patch_transformers_for_mps

        patch_transformers_for_mps()
        _deferred_patch_transformers._applied = True  # type: ignore[attr-defined]


# Trigger MPS patch lazily when accessing any public entrypoint
def __getattr__(name: str) -> object:
    if name in (
        "DocumentIngestor",
        "AsyncDocumentIngestor",
        "is_supported",
        "get_file_type",
        "SUPPORTED_EXTENSIONS",
    ):
        _deferred_patch_transformers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "AsyncDocumentIngestor",
    "DocumentExtractionError",
    "DocumentIngestor",
    "Segment",
    "UnsupportedFileError",
    "get_file_type",
    "is_supported",
]
