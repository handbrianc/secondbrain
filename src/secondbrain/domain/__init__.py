"""Domain models and core business logic for SecondBrain.

This module contains the core domain entities, value objects, and interfaces
that represent the business concepts of the document intelligence system,
separated from infrastructure concerns (storage, embedding generation, etc.).

Module Structure:
- entities.py: Core domain entities with identity and lifecycle
- value_objects.py: Immutable value objects (chunks, embeddings, etc.)
- interfaces.py: Abstract protocols for infrastructure components
- events.py: Domain events for event-driven architecture
"""

from secondbrain.domain.entities import DocumentChunk, DocumentMetadata
from secondbrain.domain.interfaces import (
    DocumentConverter,
    EmbeddingGenerator,
    VectorStore,
)
from secondbrain.domain.value_objects import ChunkId, EmbeddingVector, SourcePath

__all__ = [
    # Value Objects
    "ChunkId",
    # Entities
    "DocumentChunk",
    # Interfaces
    "DocumentConverter",
    "DocumentMetadata",
    "EmbeddingGenerator",
    "EmbeddingVector",
    "SourcePath",
    "VectorStore",
]
