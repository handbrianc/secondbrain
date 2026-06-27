"""SecondBrain - A local document intelligence CLI tool for semantic search.

This package provides a CLI tool that ingests documents, generates embeddings
using sentence-transformers, and stores vectors in MongoDB for semantic search.
"""

from importlib.metadata import version as _get_version

from secondbrain import config, conversation, document, rag, search, storage, utils

__all__ = ["config", "conversation", "document", "rag", "search", "storage", "utils"]
__version__ = _get_version("secondbrain")
