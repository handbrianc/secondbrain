"""Vector storage module for MongoDB integration.

Re-exports public API from submodules for backward compatibility.
"""

from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.async_storage import AsyncVectorStorage
from secondbrain.storage.models import DatabaseStats
from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.storage.sync import VectorStorage
from secondbrain.types import ChunkInfo, SearchResult

__all__ = [
    "AsyncVectorStorage",
    "ChunkInfo",
    "DatabaseStats",
    "SearchResult",
    "StorageConnectionError",
    "VectorStorage",
    "build_search_pipeline",
]
