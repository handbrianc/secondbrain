"""Vector storage module for Qdrant integration.

Re-exports public API from submodules.
"""

from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.factory import StorageFactory
from secondbrain.storage.mock import MockVectorStorage
from secondbrain.storage.models import DatabaseStats
from secondbrain.storage.protocol import VectorStorageProtocol
from secondbrain.storage.qdrant import QdrantVectorStorage
from secondbrain.types import ChunkInfo, SearchResult

__all__ = [
    "ChunkInfo",
    "DatabaseStats",
    "MockVectorStorage",
    "QdrantVectorStorage",
    "SearchResult",
    "StorageConnectionError",
    "StorageFactory",
    "VectorStorageProtocol",
]
