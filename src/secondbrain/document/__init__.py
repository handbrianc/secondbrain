from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from docling.document_converter import DocumentConverter
from typing_extensions import TypedDict

from secondbrain.config import get_config
from secondbrain.exceptions import DocumentExtractionError, UnsupportedFileError

logger = logging.getLogger(__name__)


class Segment(TypedDict):
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

    Returns:
        True if file type is supported, False otherwise.
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
    """Get the file type category for a given file path.

    Args:
        file_path: Path to determine file type for.

    Returns:
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

        self.converter = DocumentConverter()

    def _validate_file_path(self, path: Path) -> None:
        """Validate file path for security.

        Args:
            path: Path to validate.

        Raises:
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

        Raises:
            ValueError: If file exceeds maximum size limit.
        """
        file_size = path.stat().st_size
        if file_size > self.max_file_size_bytes:
            raise ValueError(
                f"File '{path}' exceeds maximum size limit of "
                f"{self.max_file_size_bytes / (1024 * 1024):.0f}MB "
                f"(actual: {file_size / (1024 * 1024):.2f}MB)"
            )

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

        Returns:
            dict with 'success' and 'failed' counts.
        """
        from secondbrain.embedding import EmbeddingGenerator
        from secondbrain.storage import VectorStorage

        path_obj = Path(path)

        if path_obj.is_file():
            self._validate_file_path(path_obj)
            self._validate_file_size(path_obj)
            files = [path_obj]
        elif path_obj.is_dir():
            files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
            validated_files = []
            for f in files:
                if f.is_file() and is_supported(f):
                    self._validate_file_path(f)
                    self._validate_file_size(f)
                    validated_files.append(f)
            files = validated_files
        else:
            raise ValueError(f"Invalid path: {path}")

        if not files:
            return {"success": 0, "failed": 0}

        failed_files = 0
        successful_files = 0

        embedding_gen = EmbeddingGenerator()
        storage = VectorStorage()

        # Process files in streaming batches
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from secondbrain.exceptions import (
            EmbeddingGenerationError,
            OllamaUnavailableError,
        )

        def process_single_file(
            file_path: Path,
        ) -> tuple[Path, list[Segment], list[str]] | None:
            try:
                segments: list[Segment] = self._extract_text(file_path)
                texts = [s["text"] for s in segments]
                return (file_path, segments, texts)
            except (OSError, DocumentExtractionError) as e:
                logger.error(f"Failed to extract text from {file_path}: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error extracting text from {file_path}: {e}")
                return None

        def chunk_and_process(
            file_path: Path,
            segments: list[Segment],
            texts: list[str],
        ) -> list[dict[str, Any]]:

            all_chunks: list[dict[str, Any]] = []
            seen_hashes = set()

            for i, (chunk, text) in enumerate(zip(segments, texts, strict=True)):
                cleaned = text.strip()
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
                            "page": chunk["page"],
                            "text_hash": text_hash,
                        }
                    )

            # Generate embeddings for this file's chunks
            chunk_to_embedding: dict[int, list[float]] = {}
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_hash: dict[Any, int] = {}
                for c in all_chunks:
                    future = executor.submit(embedding_gen.generate, c["text"])
                    future_to_hash[future] = c["text_hash"]

                for future in as_completed(future_to_hash):
                    text_hash = future_to_hash.pop(future)
                    try:
                        embedding = future.result()
                        chunk_to_embedding[text_hash] = embedding
                    except (OllamaUnavailableError, EmbeddingGenerationError) as e:
                        logger.error(f"Failed to generate embedding for chunk: {e}")
                    except Exception as e:
                        logger.error(
                            f"Unexpected error generating embedding for chunk: {e}"
                        )

            # Build documents for storage
            docs_to_store: list[dict[str, Any]] = []
            seen_doc_keys = set()

            for chunk_item in all_chunks:
                file_path_loc = chunk_item["file_path"]
                text = chunk_item["text"]
                page = chunk_item["page"]
                text_hash = chunk_item["text_hash"]

                if text_hash not in chunk_to_embedding:
                    continue

                doc_key = (str(file_path_loc), page, text_hash)
                if doc_key in seen_doc_keys:
                    continue
                seen_doc_keys.add(doc_key)

                embedding = chunk_to_embedding[text_hash]

                file_type = get_file_type(file_path_loc)
                doc = {
                    "chunk_id": str(uuid4()),
                    "source_file": str(file_path_loc),
                    "page_number": page,
                    "chunk_text": text,
                    "embedding": embedding,
                    "metadata": {
                        "file_type": file_type,
                        "ingested_at": None,
                        "chunk_index": chunk_item["original_index"],
                    },
                }
                docs_to_store.append(doc)

            return docs_to_store

        # Process files in parallel batches
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(process_single_file, file_path): file_path
                for file_path in files
            }

            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    result = future.result()
                    if result is None:
                        failed_files += 1
                        continue

                    file_path_proc, segments, texts = result
                    docs_to_store = chunk_and_process(file_path_proc, segments, texts)

                    if docs_to_store:
                        storage.store_batch(docs_to_store)
                        successful_files += 1

                except Exception as e:
                    logger.error(f"Unexpected error processing file {file_path}: {e}")
                    failed_files += 1

        return {"success": successful_files, "failed": failed_files}

    def _extract_text(self, file_path: Path) -> list[Segment]:
        """Extract text content from a file.

        Args:
            file_path: Path to the file to extract text from.

        Returns:
            List of segments with text and page number.

        Raises:
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

        except OSError as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise DocumentExtractionError(
                f"Failed to read file '{file_path}': {type(e).__name__}: {e}"
            ) from e
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise DocumentExtractionError(
                f"Failed to extract text from '{file_path}': {type(e).__name__}: {e}"
            ) from e

    def _chunk_text(self, segments: list[Segment]) -> list[Segment]:
        """Split segments into overlapping chunks.

        Args:
            segments: List of text segments to chunk.

        Returns:
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
