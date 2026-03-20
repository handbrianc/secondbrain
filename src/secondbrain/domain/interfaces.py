"""Domain interfaces for infrastructure components.

These protocols define the contracts that infrastructure implementations
must satisfy, enabling dependency inversion and testability.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from secondbrain.domain.entities import DocumentChunk


@runtime_checkable
class DocumentConverter(Protocol):
    """Protocol for document extraction and conversion.

    Implementations: DoclingConverter, TikaConverter, etc.
    """

    def convert(self, file_path: Path) -> dict[str, str]:
        """Extract text content from a document file.

        Parameters
        ----------
        file_path : Path
            Path to the document file

        Returns
        -------
        dict[str, str]
            Dictionary mapping page numbers to extracted text
        """
        ...

    def supports_format(self, file_path: Path) -> bool:
        """Check if this converter supports the given file format.

        Parameters
        ----------
        file_path : Path
            Path to check

        Returns
        -------
        bool
            True if converter can handle this file type
        """
        ...


@runtime_checkable
class EmbeddingGenerator(Protocol):
    """Protocol for generating text embeddings.

    Implementations: SentenceTransformersEmbedder, OllamaEmbedder, etc.
    """

    def generate(self, text: str) -> list[float]:
        """Generate embedding vector for a single text.

        Parameters
        ----------
        text : str
            Text to embed

        Returns
        -------
        list[float]
            Embedding vector (float32 values)
        """
        ...

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts efficiently.

        Parameters
        ----------
        texts : list[str]
            List of texts to embed

        Returns
        -------
        list[list[float]]
            List of embedding vectors, same order as input
        """
        ...

    @property
    def dimensions(self) -> int:
        """Dimensionality of generated embeddings."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector database operations.

    Implementations: MongoDBVectorStore, PineconeStore, etc.
    """

    def store(self, chunk: DocumentChunk) -> str:
        """Store a single document chunk.

        Parameters
        ----------
        chunk : DocumentChunk
            Chunk to store

        Returns
        -------
        str
            Database ID of stored document
        """
        ...

    def store_batch(self, chunks: list[DocumentChunk]) -> int:
        """Store multiple chunks efficiently.

        Parameters
        ----------
        chunks : list[DocumentChunk]
            List of chunks to store

        Returns
        -------
        int
            Number of chunks successfully stored
        """
        ...

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
    ) -> Sequence[DocumentChunk]:
        """Search for similar chunks using vector similarity.

        Parameters
        ----------
        embedding : list[float]
            Query embedding vector
        top_k : int
            Number of results to return
        source_filter : str | None
            Optional filter by source file path

        Returns
        -------
        Sequence[DocumentChunk]
            Similar chunks sorted by similarity score
        """
        ...

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file.

        Parameters
        ----------
        source : str
            Source file path

        Returns
        -------
        int
            Number of deleted chunks
        """
        ...

    def delete_all(self) -> int:
        """Delete all stored chunks.

        Returns
        -------
        int
            Number of deleted chunks
        """
        ...
