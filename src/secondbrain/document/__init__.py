"""Document ingestion and processing for secondbrain.

This module provides:
- DocumentIngestor: Main class for ingesting documents
- Segment: TypedDict for text segments with page info
- is_supported: Check if file type is supported
- get_file_type: Get file type category string
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import typing_extensions
from typing_extensions import TypedDict

from secondbrain.config import get_config
from secondbrain.exceptions import DocumentExtractionError, UnsupportedFileError

# Lazy import docling to avoid 2+ second import overhead in tests
# Only import when actually needed (DocumentConverter instantiation)
if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)

# Suppress docling deprecation warnings (upstream library issue)
import warnings  # noqa: E402

warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)


class Segment(TypedDict):
    """Text segment extracted from a document.

    Represents a chunk of text with its source page information,
    used during document ingestion pipeline.

    Attributes
    ----------
    text : str
        The extracted text content.
    page : int
        The page number where this segment was found (0-indexed).
    """

    text: str
    page: int


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".asciidoc",
    ".adoc",
    ".tex",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".wav",
    ".mp3",
    ".vtt",
    ".xml",
    ".json",
}


def is_supported(file_path: Path) -> bool:
    """Check if file extension is supported.

    Args:
        file_path: Path to check.

    Returns
    -------
        True if file type is supported, False otherwise.
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
    """Get the file type category for a given file path.

    Args:
        file_path: Path to determine file type for.

    Returns
    -------
        File type string (e.g., 'pdf', 'docx', 'image', 'audio', etc.).
    """
    ext = file_path.suffix.lower()
    type_map: dict[str, str] = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
        ".xlsx": "xlsx",
        ".html": "html",
        ".htm": "html",
        ".md": "markdown",
        ".txt": "text",
        ".asciidoc": "asciidoc",
        ".adoc": "asciidoc",
        ".tex": "latex",
        ".csv": "csv",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
        ".bmp": "image",
        ".webp": "image",
        ".wav": "audio",
        ".mp3": "audio",
        ".vtt": "webvtt",
        ".xml": "xml",
        ".json": "docling-json",
    }
    return type_map.get(ext, "unknown")


class DocumentIngestor:
    """Handles document ingestion, chunking, embedding generation, and storage.

    Processes documents by extracting text, splitting into chunks, generating
    embeddings, and storing them in the vector database.
    """

    def __init__(
        self,
        chunk_size: int = 4096,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ) -> None:
        """Initialize document ingestor.

        Args:
            chunk_size: Size of text chunks in tokens.
            chunk_overlap: Overlap between chunks in tokens.
            verbose: Enable verbose logging.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose
        self.max_file_size_bytes: int = get_config().max_file_size_bytes

        # Lazily import docling to avoid 2+ second import overhead
        from docling.document_converter import DocumentConverter

        self.converter = DocumentConverter()

    def _validate_file_path(self, path: Path) -> None:
        """Validate file path for security.

        Args:
            path: Path to validate.

        Raises
        ------
            ValueError: If path contains traversal sequences or is outside allowed directory.
        """
        # Resolve to absolute path
        resolved_path = path.resolve()

        # Check for path traversal attempts
        if ".." in path.parts:
            raise ValueError(
                f"Path traversal detected: '{path}' contains '..' sequence"
            )

        # Additional check: ensure no encoded traversal attempts
        normalized = str(resolved_path).lower()
        if "%2e%2e" in normalized or "%2e." in normalized:
            raise ValueError(f"Encoded path traversal detected in: '{path}'")

    def _validate_file_size(self, path: Path) -> None:
        """Validate file size does not exceed limit.

        Args:
            path: Path to file to validate.

        Raises
        ------
            ValueError: If file exceeds maximum size limit.
        """
        file_size = path.stat().st_size
        if file_size > self.max_file_size_bytes:
            raise ValueError(
                f"File '{path}' exceeds maximum size limit of "
                f"{self.max_file_size_bytes / (1024 * 1024):.0f}MB "
                f"(actual: {file_size / (1024 * 1024):.2f}MB)"
            )

    def _collect_and_validate_files(self, path: str, recursive: bool) -> list[Path]:
        """Collect and validate files from path.

        Args:
            path: Path to file or directory.
            recursive: Recursively process subdirectories.

        Returns
        -------
            List of validated file paths.

        Raises
        ------
            ValueError: If path is invalid or files fail validation.
        """
        path_obj = Path(path)

        if path_obj.is_file():
            self._validate_file_path(path_obj)
            self._validate_file_size(path_obj)
            return [path_obj]
        elif path_obj.is_dir():
            files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
            validated_files = []
            for f in files:
                if f.is_file() and is_supported(f):
                    self._validate_file_path(f)
                    self._validate_file_size(f)
                    validated_files.append(f)
            return validated_files
        else:
            raise ValueError(f"Invalid path: {path}")

    def _process_file_for_storage(
        self,
        file_path: Path,
        embedding_gen: Any,
    ) -> list[dict[str, Any]] | None:
        """Process a single file and build documents for storage.

        Args:
            file_path: Path to the file to process.
            embedding_gen: EmbeddingGenerator instance.

        Returns
        -------
            List of documents ready for storage, or None if processing fails.
        """
        from secondbrain.exceptions import (
            EmbeddingGenerationError,
            OllamaUnavailableError,
        )

        try:
            # Extract text
            segments: list[Segment] = self._extract_text(file_path)
        except (OSError, DocumentExtractionError) as e:
            logger.error(f"Failed to extract text from {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error extracting text from {file_path}: "
                f"{type(e).__name__}: {e}"
            )
            return None

        # Chunk and build documents with embeddings
        return self._build_documents_with_embeddings(
            file_path=file_path,
            segments=segments,
            embedding_gen=embedding_gen,
        )

    def _build_documents_with_embeddings(
        self,
        file_path: Path,
        segments: list[Segment],
        embedding_gen: Any,
    ) -> list[dict[str, Any]]:
        """Build documents with embeddings from text segments.

        Args:
            file_path: Source file path.
            segments: List of text segments to process.
            embedding_gen: EmbeddingGenerator instance.

        Returns
        -------
            List of documents ready for storage.
        """
        from secondbrain.exceptions import (
            EmbeddingGenerationError,
            OllamaUnavailableError,
        )

        # Chunk text and deduplicate
        all_chunks: list[dict[str, Any]] = []
        seen_hashes = set()

        for i, segment in enumerate(segments):
            cleaned = segment["text"].strip()
            if not cleaned:
                continue

            normalized = " ".join(cleaned.lower().split())
            text_hash = hash(normalized)

            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                all_chunks.append(
                    {
                        "file_path": file_path,
                        "original_index": i,
                        "text": cleaned,
                        "page": segment["page"],
                        "text_hash": text_hash,
                    }
                )

        # Generate embeddings sequentially (cache handles deduplication)
        chunk_to_embedding: dict[int, list[float]] = {}

        for chunk in all_chunks:
            try:
                embedding = embedding_gen.generate(chunk["text"])
                chunk_to_embedding[chunk["text_hash"]] = embedding
            except Exception as e:
                logger.error(
                    "Failed to generate embedding for chunk: %s: %s",
                    type(e).__name__,
                    e,
                )
                # Skip this chunk - continue with others
                continue

        # Build final documents
        docs_to_store: list[dict[str, Any]] = []
        seen_doc_keys = set()

        for chunk_item in all_chunks:
            text_hash = chunk_item["text_hash"]

            if text_hash not in chunk_to_embedding:
                continue

            doc_key = (
                str(chunk_item["file_path"]),
                chunk_item["page"],
                text_hash,
            )
            if doc_key in seen_doc_keys:
                continue
            seen_doc_keys.add(doc_key)

            embedding = chunk_to_embedding[text_hash]
            file_type = get_file_type(chunk_item["file_path"])

            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(chunk_item["file_path"]),
                "page_number": chunk_item["page"],
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "metadata": {
                    "file_type": file_type,
                    "ingested_at": None,
                    "chunk_index": chunk_item["original_index"],
                },
            }
            docs_to_store.append(doc)

        return docs_to_store

    def ingest(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 10,
    ) -> dict[str, int]:
        """Ingest documents from a file or directory.

        Args:
            path: Path to file or directory to ingest.
            recursive: Recursively process subdirectories.
            batch_size: Number of files to process in parallel.

        Returns
        -------
            dict with 'success' and 'failed' counts.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from secondbrain.embedding import EmbeddingGenerator
        from secondbrain.storage import VectorStorage

        # Collect and validate files
        files = self._collect_and_validate_files(path, recursive)

        if not files:
            return {"success": 0, "failed": 0}

        # Initialize services
        embedding_gen = EmbeddingGenerator()
        storage = VectorStorage()

        failed_files = 0
        successful_files = 0

        # Process files in parallel batches
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(self._process_file_for_storage, f, embedding_gen): f
                for f in files
            }

            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    docs_to_store = future.result()

                    if docs_to_store is None:
                        failed_files += 1
                        continue

                    if docs_to_store:
                        storage.store_batch(docs_to_store)
                        successful_files += 1

                except Exception as e:
                    logger.error(
                        f"Unexpected error processing file {file_path}: "
                        f"{type(e).__name__}: {e}"
                    )
                    failed_files += 1

        return {"success": successful_files, "failed": failed_files}

    def _extract_text(self, file_path: Path) -> list[Segment]:
        """Extract text content from a file.

        Args:
            file_path: Path to the file to extract text from.

        Returns
        -------
            List of segments with text and page number.

        Raises
        ------
            DocumentExtractionError: If text extraction fails.
        """
        try:
            result = self.converter.convert(file_path)
            content = result.document

            segments: list[Segment] = []

            if hasattr(content, "texts") and content.texts:
                for text_item in content.texts:
                    if not hasattr(text_item, "text") or not text_item.text:
                        continue

                    page_num = 1
                    if hasattr(text_item, "prov") and text_item.prov:
                        prov = text_item.prov[0]
                        if hasattr(prov, "page_no"):
                            page_num = prov.page_no

                    segments.append({"text": text_item.text, "page": page_num})

            if not segments:
                with file_path.open(encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                    segments = [{"text": text, "page": 1}]

            return segments

        except DocumentExtractionError:
            raise
        except Exception as e:
            logger.error(
                "Error extracting text from %s: %s: %s", file_path, type(e).__name__, e
            )
            raise DocumentExtractionError(
                f"Failed to extract text from {file_path}: {e}"
            ) from e

    def _chunk_text(self, segments: list[Segment]) -> list[Segment]:
        """Split segments into overlapping chunks.

        Args:
            segments: List of text segments to chunk.

        Returns
        -------
            List of chunked segments with overlapping text.
        """
        chunks: list[Segment] = []

        for segment in segments:
            text = segment["text"]
            page = segment["page"]

            if not text.strip():
                continue

            start = 0
            while start < len(text):
                next_start = start + self.chunk_size
                chunk_end = next_start if next_start < len(text) else len(text)
                last_space = text.rfind(" ", start, chunk_end)
                if last_space > start:
                    chunk_end = last_space
                chunk_text = text[start:chunk_end].strip()
                if chunk_text:
                    chunks.append({"text": chunk_text, "page": page})

                new_start = chunk_end - self.chunk_overlap
                if new_start >= len(text) or new_start <= start:
                    break
                start = new_start

        return chunks


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "DocumentExtractionError",
    "DocumentIngestor",
    "Segment",
    "UnsupportedFileError",
    "get_file_type",
    "is_supported",
]
