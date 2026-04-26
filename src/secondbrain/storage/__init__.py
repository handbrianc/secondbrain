"""Vector storage module for MongoDB integration.

Re-exports public API from submodules.
"""

import time

from pymongo import MongoClient

from secondbrain.config import config, get_config
from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.models import DatabaseStats
from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.storage.storage import VectorStorage
from secondbrain.storage.mock import MockVectorStorage
from secondbrain.types import ChunkInfo, SearchResult

__all__ = [
    "ChunkInfo",
    "DatabaseStats",
    "MongoClient",
    "MockVectorStorage",
    "SearchResult",
    "StorageConnectionError",
    "VectorStorage",
    "build_search_pipeline",
    "get_config",
    "time",
]
