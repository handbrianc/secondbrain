"""Document ingestion and processing for secondbrain.

This module provides:
- DocumentIngestor: Main class for ingesting documents
- Segment: TypedDict for text segments with page info
- is_supported: Check if file type is supported
- get_file_type: Get file type category string
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

import typing_extensions
from typing_extensions import TypedDict

from secondbrain.config import get_config
from secondbrain.exceptions import DocumentExtractionError, UnsupportedFileError
from secondbrain.utils.embedding_cache import EmbeddingCache
from secondbrain.utils.tracing import trace_operation

# Lazy import docling to avoid 2+ second import overhead in tests
# Only import when actually needed (DocumentConverter instantiation)
if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

    from secondbrain.embedding.local import LocalEmbeddingGenerator

logger = logging.getLogger(__name__)

# Suppress docling deprecation warnings (upstream library issue)
import warnings  # noqa: E402

warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)

# Memory management constant for batch sizes
# Rationale: 100 chunks x 384-dim embeddings (float32) ~150MB RAM peak
# - Each embedding: 384 floats x 4 bytes = 1.5KB
# - 100 embeddings: 150KB (negligible)
# - Main memory cost: storing full text chunks + metadata during batch processing
# - 100 is a conservative limit that prevents OOM on large document batches
# - Can be tuned based on available RAM and typical document sizes
MAX_MEMORY_BATCH_SIZE = 100

# Global variable for worker converter (set by ProcessPoolExecutor initializer)
_worker_converter: DocumentConverter | None = None
_worker_progress_queue: Any = None


def _init_worker() -> None:
    """Initialize worker process with DocumentConverter."""
    global _worker_converter
    from docling.document_converter import DocumentConverter

    _worker_converter = DocumentConverter()


def _init_worker_with_queue(queue: Any, embedding_model_name: str) -> None:
    """Initialize worker process with DocumentConverter, progress queue, and embedding model."""
    global _worker_converter, _worker_progress_queue, _worker_embedding_model
    from docling.document_converter import DocumentConverter
    from secondbrain.embedding.local import LocalEmbeddingGenerator

    _worker_converter = DocumentConverter()
    _worker_progress_queue = queue
    _worker_embedding_model = LocalEmbeddingGenerator(model_name=embedding_model_name)


def _extract_and_chunk_file(
    file_path_str: str, chunk_size: int, chunk_overlap: int
) -> dict[str, Any]:
    """Worker function for multiprocessing: extract and chunk a single file.

    This function runs in a separate process and returns extracted chunks.
    Must be at module level to be picklable for ProcessPoolExecutor.
    Uses the global _worker_converter if initialized, otherwise creates one.

    Args:
        file_path_str: String path to the file to process.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'chunks' (list[Segment]), 'error' (str | None).
    """
    file_path = Path(file_path_str)
    try:
        # Use pre-initialized converter if available, otherwise create one
        # This allows the function to work both in ProcessPoolExecutor workers
        # (where _init_worker is called) and in tests (where it's called directly)
        converter = _worker_converter
        if converter is None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()

        result = converter.convert(file_path)
        content = result.document

        # Extract segments from document (don't chunk yet - let main process handle streaming)
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

        # Fallback: read file directly for plain text formats
        if not segments:
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                text = f.read()
            segments = [{"text": text, "page": 1}]

        return {
            "success": True,
            "file_path": file_path,
            "segments": segments,  # Return segments, not chunks
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": file_path,
            "segments": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _extract_chunk_and_embed_file(
    file_path_str: str,
    chunk_size: int,
    chunk_overlap: int,
    progress_queue: Any,
    embedding_model_name: str,
) -> dict[str, Any]:
    """Worker function that extracts, chunks, embeds, and reports progress.

    This function runs in a separate process and returns documents with embeddings.
    All CPU/GPU intensive work (extraction, chunking, embedding) happens in worker.
    Main process only handles storage.

    Args:
        file_path_str: String path to the file to process.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        progress_queue: Multiprocessing Queue for progress updates.
        embedding_model_name: Name of embedding model to use.

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'documents' (list[dict]), 'error' (str | None).
    """
    file_path = Path(file_path_str)
    try:
        converter = _worker_converter
        if converter is None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()

        result = converter.convert(file_path)
        content = result.document

        # Extract segments
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

        # Chunk segments
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        # Generate embeddings using worker's pre-loaded model
        embedding_model = _worker_embedding_model
        if embedding_model is None:
            from secondbrain.embedding.local import LocalEmbeddingGenerator

            embedding_model = LocalEmbeddingGenerator(model_name=embedding_model_name)

        # Deduplicate chunks
        seen_hashes = set()
        unique_chunks = []
        for chunk in chunks:
            cleaned = chunk["text"].strip()
            if not cleaned:
                continue
            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                unique_chunks.append(
                    {
                        "text": cleaned,
                        "page": chunk["page"],
                        "text_hash": text_hash,
                    }
                )

        # Generate embeddings in batch (GPU efficient)
        if unique_chunks:
            texts = [c["text"] for c in unique_chunks]
            embeddings = embedding_model.generate_batch(texts)
        else:
            embeddings = []

        # Build documents with embeddings
        from datetime import UTC, datetime
        from uuid import uuid4

        documents = []
        for chunk_item, embedding in zip(unique_chunks, embeddings, strict=True):
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(file_path),
                "page_number": chunk_item["page"],
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "metadata": {
                    "file_type": get_file_type(file_path),
                    "ingested_at": datetime.now(UTC).isoformat(),
                    "chunk_index": chunk_item["text_hash"],
                },
            }
            documents.append(doc)

        # Send progress update
        if _worker_progress_queue is not None:
            try:
                _worker_progress_queue.put_nowait((str(file_path), len(documents) > 0))
            except Exception:
                pass

        return {
            "success": True,
            "file_path": file_path,
            "documents": documents,
            "error": None,
        }
    except Exception as e:
        if _worker_progress_queue is not None:
            try:
                _worker_progress_queue.put_nowait((str(file_path), False))
            except Exception:
                pass
        return {
            "success": False,
            "file_path": file_path,
            "documents": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _extract_and_chunk_file_with_progress(
    file_path_str: str,
    chunk_size: int,
    chunk_overlap: int,
    progress_queue: Any,
) -> dict[str, Any]:
    """Worker function that extracts, chunks, and reports progress via queue.

    This function runs in a separate process and returns extracted chunks.
    Additionally sends progress updates to the main process via the queue.
    Must be at module level to be picklable for ProcessPoolExecutor.

    Args:
        file_path_str: String path to the file to process.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        progress_queue: Multiprocessing Queue for progress updates.

    Returns
    -------
        Dict with keys: 'success' (bool), 'file_path' (str),
        'segments' (list[Segment]), 'error' (str | None).
    """
    file_path = Path(file_path_str)
    try:
        # Use pre-initialized converter if available, otherwise create one
        converter = _worker_converter
        if converter is None:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()

        result = converter.convert(file_path)
        content = result.document

        # Extract segments from document
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

        # Fallback: read file directly for plain text formats
        if not segments:
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                text = f.read()
            segments = [{"text": text, "page": 1}]

        # Send progress update before returning
        if _worker_progress_queue is not None:
            try:
                _worker_progress_queue.put_nowait((str(file_path), True))
            except Exception:
                pass  # Queue might be full or closed, ignore

        return {
            "success": True,
            "file_path": file_path,
            "segments": segments,
            "error": None,
        }
    except Exception as e:
        # Send failure progress update
        if _worker_progress_queue is not None:
            try:
                _worker_progress_queue.put_nowait((str(file_path), False))
            except Exception:
                pass

        return {
            "success": False,
            "file_path": file_path,
            "segments": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _chunk_segments(
    segments: list[Segment], chunk_size: int, chunk_overlap: int
) -> list[Segment]:
    """Chunk segments into smaller pieces respecting size limits.

    Args:
        segments: List of extracted text segments.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns
    -------
        List of chunked segments.
    """
    chunks: list[Segment] = []

    for segment in segments:
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        start = 0
        while start < len(text):
            next_start = start + chunk_size
            chunk_end = next_start if next_start < len(text) else len(text)
            last_space = text.rfind(" ", start, chunk_end)
            if last_space > start:
                chunk_end = last_space
            chunk_text = text[start:chunk_end].strip()
            if chunk_text:
                chunks.append({"text": chunk_text, "page": page})

            new_start = chunk_end - chunk_overlap
            if new_start >= len(text) or new_start <= start:
                break
            start = new_start

    return chunks


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
        progress_callback: Callable[[Path, bool], None] | None = None,
    ) -> None:
        """Initialize document ingestor.

        Args:
            chunk_size: Size of text chunks in tokens.
            chunk_overlap: Overlap between chunks in tokens.
            verbose: Enable verbose logging.
            progress_callback: Optional callback(file_path: Path, success: bool) called after each file.
        """
        config = get_config()

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose
        self.max_file_size_bytes: int = config.max_file_size_bytes
        self.progress_callback = progress_callback

        # Initialize embedding cache for deduplication
        self.embedding_cache = EmbeddingCache(max_size=config.embedding_cache_size)

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
        self, file_path: Path, embedding_gen: Any
    ) -> list[dict[str, Any]] | None:
        """Process a single file - uses streaming if enabled.

        Streaming Processing Flow (when enabled):
        -----------------------------------------
        1. Extract text segments from document (PDF pages, docx paragraphs, etc.)
        2. Chunk segments into manageable pieces (chunk_size characters with overlap)
        3. Deduplicate chunks using SHA256 hash of normalized text
        4. Generate embeddings in small batches (streaming_chunk_batch_size)
        5. Store each batch immediately to MongoDB, then discard from memory
        6. Repeat until all chunks processed

        Why Streaming?
        --------------
        - Memory efficiency: Large documents (100+ pages) can be processed
          without holding all embeddings in RAM simultaneously
        - Scalability: Can process arbitrarily large documents with constant memory
        - Early persistence: Data is stored incrementally, not all at once at the end

        Deduplication Strategy:
        -----------------------
        - Normalizes text (lowercase, single spaces) before hashing
        - SHA256 hash of normalized text serves as unique identifier
        - Prevents storing duplicate content (e.g., repeated headers, boilerplate)
        - Hash stored with document for future deduplication checks

        Args:
            file_path: Path to document to process.
            embedding_gen: Embedding generator instance.

        Returns
        -------
            Empty list if streaming used (docs stored directly),
            list of documents if batch processing,
            None if processing failed.
        """
        from secondbrain.config import get_config
        from secondbrain.storage import VectorStorage

        config = get_config()

        try:
            segments: list[Segment] = self._extract_text(file_path)
        except (OSError, DocumentExtractionError) as e:
            logger.error("Failed to extract text from %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.error(
                "Unexpected error extracting text from %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
            return None

        # Use streaming if enabled (memory-efficient batch processing)
        if config.streaming_enabled:
            storage = VectorStorage()
            docs_count = self._stream_process_chunks(
                file_path, segments, embedding_gen, storage
            )
            # Return empty list to signal success (documents stored via streaming)
            return [] if docs_count > 0 else None
        else:
            # Fall back to original batch processing
            return self._build_documents_with_embeddings(
                file_path=file_path,
                segments=segments,
                embedding_gen=embedding_gen,
            )

    def _deduplicate_and_chunk_segments(
        self,
        file_path: Path,
        segments: list[Segment],
    ) -> list[dict[str, Any]]:
        """Deduplicate and chunk text segments into processed chunks.

        Args:
            file_path: Source file path.
            segments: List of text segments to process.

        Returns
        -------
            List of chunk dictionaries with metadata.
        """
        all_chunks: list[dict[str, Any]] = []
        seen_hashes = set()

        for i, segment in enumerate(segments):
            cleaned = segment["text"].strip()
            if not cleaned:
                continue

            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()

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

        return all_chunks

    def _generate_embeddings_with_cache(
        self,
        chunks: list[dict[str, Any]],
        embedding_gen: Any,
    ) -> dict[int, list[float]]:
        """Generate embeddings for chunks with caching and batch processing.

        Args:
            chunks: List of chunk dictionaries to process.
            embedding_gen: EmbeddingGenerator instance.

        Returns
        -------
            Dictionary mapping text_hash to embedding.
        """
        from secondbrain.config import get_config

        config = get_config()
        batch_size = config.embedding_batch_size
        chunk_to_embedding: dict[int, list[float]] = {}

        # Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [chunk["text"] for chunk in batch]

            try:
                # Check cache first, generate only for uncached texts
                texts_to_embed = []
                cached_indices = []

                for idx, text in enumerate(texts):
                    cached = self.embedding_cache.get(text)
                    if cached is not None:
                        chunk_to_embedding[batch[idx]["text_hash"]] = cached
                    else:
                        texts_to_embed.append(text)
                        cached_indices.append(idx)

                # Generate embeddings only for uncached texts
                if texts_to_embed:
                    embeddings = embedding_gen.generate_batch(texts_to_embed)

                    # Cache and map embeddings
                    for idx, embedding in zip(cached_indices, embeddings, strict=True):
                        text = texts[idx]
                        self.embedding_cache.set(text, embedding)
                        chunk_to_embedding[batch[idx]["text_hash"]] = embedding

            except Exception as e:
                logger.error(
                    "Failed to generate batch embeddings: %s: %s",
                    type(e).__name__,
                    e,
                )
                # Fall back to sequential for this batch
                for chunk in batch:
                    try:
                        # Check cache first
                        cached = self.embedding_cache.get(chunk["text"])
                        if cached is not None:
                            chunk_to_embedding[chunk["text_hash"]] = cached
                            continue

                        embedding = embedding_gen.generate(chunk["text"])
                        # Cache the embedding
                        self.embedding_cache.set(chunk["text"], embedding)
                        chunk_to_embedding[chunk["text_hash"]] = embedding
                    except Exception as e2:
                        logger.error(
                            "Failed to generate embedding for chunk: %s: %s",
                            type(e2).__name__,
                            e2,
                        )
                        continue

        return chunk_to_embedding

    def _build_documents_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        chunk_to_embedding: dict[int, list[float]],
    ) -> list[dict[str, Any]]:
        """Build document dictionaries from chunks with embeddings.

        Args:
            chunks: List of chunk dictionaries with metadata.
            chunk_to_embedding: Dictionary mapping text_hash to embedding.

        Returns
        -------
            List of document dictionaries ready for storage.
        """
        docs_to_store: list[dict[str, Any]] = []
        seen_doc_keys = set()

        for chunk_item in chunks:
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
                    "ingested_at": datetime.now(UTC).isoformat(),
                    "chunk_index": chunk_item["original_index"],
                },
            }
            docs_to_store.append(doc)

        return docs_to_store

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
        # Deduplicate and chunk segments
        all_chunks = self._deduplicate_and_chunk_segments(file_path, segments)

        # Generate embeddings with caching
        chunk_to_embedding = self._generate_embeddings_with_cache(
            all_chunks, embedding_gen
        )

        # Build final documents
        return self._build_documents_from_chunks(all_chunks, chunk_to_embedding)

    def _stream_process_chunks(
        self,
        file_path: Path,
        segments: list[Segment],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Stream process chunks: extract -> chunk -> embed -> store per batch.

        Streaming Batch Processing Flow:
        --------------------------------
        1. Iterate through text segments (pages, paragraphs, etc.)
        2. For each segment:
           - Clean and normalize text
           - Compute SHA256 hash for deduplication
           - Skip if duplicate (hash already seen)
           - Add to current batch
        3. When batch reaches streaming_chunk_batch_size (default: 50):
           - Generate embeddings for all chunks in batch
           - Store batch to MongoDB
           - Clear batch from memory
           - Repeat from step 1
        4. Process remaining chunks (< batch_size) at the end

        Why Batch Size = 50 (configurable)?
        -----------------------------------
        - Memory: 50 chunks x ~1KB each ~50KB RAM per batch (negligible)
        - Throughput: Batching improves embedding API efficiency
        - Responsiveness: Frequent storage prevents data loss on crash
        - Balance: Larger = better throughput, smaller = lower memory

        Deduplication:
        --------------
        - SHA256 hash of normalized text (lowercase, single spaces)
        - Prevents storing identical content (headers, boilerplate, etc.)
        - Hash persisted with document for future dedup checks

        Args:
            file_path: Source file path.
            segments: List of text segments to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.

        Returns
        -------
            Number of documents successfully stored.
        """
        from secondbrain.config import get_config

        config = get_config()
        batch_size = config.streaming_chunk_batch_size  # Default: 50 chunks/batch

        # Deduplicate chunks across all segments
        seen_hashes = set()
        batch_chunks: list[dict[str, Any]] = []
        docs_stored = 0

        for i, segment in enumerate(segments):
            cleaned = segment["text"].strip()
            if not cleaned:
                continue

            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()

            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)

            batch_chunks.append(
                {
                    "file_path": file_path,
                    "original_index": i,
                    "text": cleaned,
                    "page": segment["page"],
                    "text_hash": text_hash,
                }
            )

            # Process batch when full
            if len(batch_chunks) >= batch_size:
                docs_stored += self._store_embedding_batch(
                    file_path, batch_chunks, embedding_gen, storage
                )
                batch_chunks = []

        # Process remaining chunks
        if batch_chunks:
            docs_stored += self._store_embedding_batch(
                file_path, batch_chunks, embedding_gen, storage
            )

        return docs_stored

    def _store_embedding_batch(
        self,
        file_path: Path,
        chunks: list[dict[str, Any]],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Generate embeddings and store a batch of chunks.

        Uses batch embedding generation for improved throughput.

        Args:
            file_path: Source file path.
            chunks: List of chunk dicts to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.

        Returns
        -------
            Number of documents stored.
        """
        # Generate embeddings with cache - use batch processing for efficiency
        chunk_to_embedding: dict[int, list[float]] = {}
        texts_to_embed: list[str] = []
        text_to_chunk: dict[str, dict[str, Any]] = {}

        # First pass: check cache and collect uncached texts
        for chunk in chunks:
            cached = self.embedding_cache.get(chunk["text"])
            if cached is not None:
                chunk_to_embedding[chunk["text_hash"]] = cached
                continue
            texts_to_embed.append(chunk["text"])
            text_to_chunk[chunk["text"]] = chunk

        # Second pass: generate embeddings in batch for uncached texts
        if texts_to_embed:
            try:
                embeddings = embedding_gen.generate_batch(texts_to_embed)
                for text, embedding in zip(texts_to_embed, embeddings, strict=True):
                    self.embedding_cache.set(text, embedding)
                    chunk = text_to_chunk[text]
                    chunk_to_embedding[chunk["text_hash"]] = embedding
            except Exception as e:
                logger.error(
                    "Failed to generate batch embeddings: %s: %s",
                    type(e).__name__,
                    e,
                )
                # Fall back to sequential for failed batch
                for text in texts_to_embed:
                    chunk = text_to_chunk[text]
                    try:
                        cached = self.embedding_cache.get(text)
                        if cached is not None:
                            chunk_to_embedding[chunk["text_hash"]] = cached
                            continue
                        embedding = embedding_gen.generate(text)
                        self.embedding_cache.set(text, embedding)
                        chunk_to_embedding[chunk["text_hash"]] = embedding
                    except Exception as e2:
                        logger.error(
                            "Failed to generate embedding: %s: %s",
                            type(e2).__name__,
                            e2,
                        )
                        continue

        # Build and store documents
        docs_to_store: list[dict[str, Any]] = []
        seen_doc_keys = set()

        for chunk_item in chunks:
            text_hash = chunk_item["text_hash"]
            if text_hash not in chunk_to_embedding:
                continue

            doc_key = (str(chunk_item["file_path"]), chunk_item["page"], text_hash)
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
                    "ingested_at": datetime.now(UTC).isoformat(),
                    "chunk_index": chunk_item["original_index"],
                },
            }
            docs_to_store.append(doc)

        if docs_to_store:
            storage.store_batch(docs_to_store)

        return len(docs_to_store)

    def _resolve_core_count(self, cores: int | None) -> int:
        """Resolve and validate core count for parallel processing.

        Args:
            cores: Requested core count, or None for auto-detection.

        Returns
        -------
            Validated core count (positive integer).

        Raises
        ------
            ValueError: If cores is non-positive after resolution.
        """
        config = get_config()
        if cores is None:
            cores = config.max_workers or os.cpu_count() or 1

        if cores <= 0:
            raise ValueError("cores must be positive")

        return cores

    def _process_parallel_with_progress(
        self,
        files: list[Path],
        embedding_gen: Any,
        storage: Any,
        max_workers: int,
    ) -> tuple[int, int]:
        """Process files using multiprocessing with progress callback support.

        Uses ProcessPoolExecutor with a Queue for progress updates. Worker processes
        send completion status via Queue, and the main process updates the progress
        bar. This enables true CPU parallelism while maintaining real-time progress.

        Args:
            files: List of file paths to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.
            max_workers: Number of worker processes.

        Returns
        -------
            Tuple of (successful_files, failed_files) counts.
        """
        from concurrent.futures import (
            ProcessPoolExecutor,
            as_completed,
        )
        from multiprocessing import Manager

        successful_files = 0
        failed_files = 0

        # Use a Manager to create a shared Queue for progress updates
        from secondbrain.config import get_config

        config = get_config()

        with Manager() as manager:
            progress_queue = manager.Queue()
            embedding_model_name = config.local_embedding_model

            with (
                trace_operation("ingest_multiprocess_progress"),
                ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=_init_worker_with_queue,
                    initargs=(progress_queue, embedding_model_name),
                ) as executor,
            ):
                futures = {
                    executor.submit(
                        _extract_chunk_and_embed_file,
                        str(f),
                        self.chunk_size,
                        self.chunk_overlap,
                        progress_queue,
                        embedding_model_name,
                    ): f
                    for f in files
                }

                # Process futures and handle progress updates from queue
                completed = 0
                total = len(files)
                pending_futures = dict(futures)

                while pending_futures:
                    # Drain any pending queue messages
                    while not progress_queue.empty():
                        try:
                            progress_queue.get_nowait()
                        except Exception:
                            break

                    # Process completed futures
                    done_futures = []
                    for future in as_completed(pending_futures, timeout=3600):
                        file_path = futures[future]
                        try:
                            result = future.result(timeout=300)

                            if not result["success"]:
                                if self.verbose:
                                    logger.error(
                                        "Failed to process %s: %s",
                                        file_path,
                                        result.get("error", "Unknown error"),
                                    )
                                failed_files += 1
                                completed += 1
                                if self.progress_callback:
                                    self.progress_callback(file_path, False)
                                done_futures.append(future)
                                continue

                            documents = result.get("documents", [])
                            if not documents:
                                if self.verbose:
                                    logger.warning(
                                        "No documents produced from %s", file_path
                                    )
                                failed_files += 1
                                completed += 1
                                if self.progress_callback:
                                    self.progress_callback(file_path, False)
                                done_futures.append(future)
                                continue

                            for i in range(0, len(documents), MAX_MEMORY_BATCH_SIZE):
                                storage.store_batch(
                                    documents[i : i + MAX_MEMORY_BATCH_SIZE]
                                )

                            successful_files += 1
                            completed += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, True)
                            done_futures.append(future)

                        except Exception as e:
                            if self.verbose:
                                logger.error(
                                    "Unexpected error processing file %s: %s: %s",
                                    file_path,
                                    type(e).__name__,
                                    e,
                                )
                            failed_files += 1
                            completed += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, False)
                            done_futures.append(future)

                    for future in done_futures:
                        del pending_futures[future]

                    if pending_futures:
                        import time

                        time.sleep(0.01)

        return successful_files, failed_files

    def _process_multiprocessing_batch(
        self,
        files: list[Path],
        embedding_gen: Any,
        storage: Any,
        cores: int,
    ) -> tuple[int, int]:
        """Process files using multiprocessing with ProcessPoolExecutor.

        Args:
            files: List of file paths to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.
            cores: Number of CPU cores to use.

        Returns
        -------
            Tuple of (successful_files, failed_files) counts.
        """
        from concurrent.futures import (
            ProcessPoolExecutor,
            as_completed,
        )

        from secondbrain.config import get_config

        successful_files = 0
        failed_files = 0

        with (
            trace_operation("ingest_multiprocess"),
            ProcessPoolExecutor(
                max_workers=cores,
                initializer=_init_worker,
            ) as executor,
        ):
            futures = {
                executor.submit(
                    _extract_and_chunk_file,
                    str(f),
                    self.chunk_size,
                    self.chunk_overlap,
                ): f
                for f in files
            }

            for future in as_completed(futures, timeout=3600):
                file_path = futures[future]
                try:
                    result = future.result(timeout=300)

                    if not result["success"]:
                        if self.verbose:
                            logger.error(
                                "Failed to process %s: %s", file_path, result["error"]
                            )
                        failed_files += 1
                        if self.progress_callback:
                            self.progress_callback(file_path, False)
                        continue

                    segments = result["segments"]
                    if not segments:
                        if self.verbose:
                            logger.warning(
                                "File %s produced no segments (may be empty, image-only, or extraction failed)",
                                file_path,
                            )
                        failed_files += 1
                        if self.progress_callback:
                            self.progress_callback(file_path, False)
                        continue

                    config = get_config()

                    if config.streaming_enabled:
                        with trace_operation("ingest_stream_process"):
                            docs_count = self._stream_process_chunks(
                                file_path, segments, embedding_gen, storage
                            )
                        if docs_count > 0:
                            successful_files += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, True)
                        else:
                            failed_files += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, False)
                    else:
                        with trace_operation("ingest_batch_process"):
                            docs_to_store = self._build_documents_with_embeddings(
                                file_path, segments, embedding_gen
                            )
                        if docs_to_store:
                            for i in range(
                                0, len(docs_to_store), MAX_MEMORY_BATCH_SIZE
                            ):
                                batch = docs_to_store[i : i + MAX_MEMORY_BATCH_SIZE]
                                storage.store_batch(batch)
                            successful_files += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, True)
                        else:
                            failed_files += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, False)

                except Exception as e:
                    if self.verbose:
                        logger.error(
                            "Unexpected error processing file %s: %s: %s",
                            file_path,
                            type(e).__name__,
                            e,
                        )
                    failed_files += 1
                    if self.progress_callback:
                        self.progress_callback(file_path, False)

        return successful_files, failed_files

    def _process_threadpool_batch(
        self,
        files: list[Path],
        embedding_gen: Any,
        storage: Any,
        batch_size: int,
    ) -> tuple[int, int]:
        """Process files using ThreadPoolExecutor for sequential/batch processing.

        Args:
            files: List of file paths to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.
            batch_size: Number of concurrent threads.

        Returns
        -------
            Tuple of (successful_files, failed_files) counts.
        """
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
        )

        successful_files = 0
        failed_files = 0

        with (
            trace_operation("ingest_thread_process"),
            ThreadPoolExecutor(max_workers=batch_size) as executor,
        ):
            futures_dict: dict[Any, Path] = {}
            for f in files:
                future = executor.submit(
                    self._process_file_for_storage, f, embedding_gen
                )
                futures_dict[future] = f

        for future in as_completed(futures_dict, timeout=3600):
            file_path = futures_dict[future]
            try:
                result = future.result(timeout=300)
                if result is None or not result:
                    failed_files += 1
                    if self.progress_callback:
                        self.progress_callback(file_path, False)
                    continue

                storage.store_batch(result)
                successful_files += 1
                if self.progress_callback:
                    self.progress_callback(file_path, True)

            except Exception as e:
                if self.verbose:
                    logger.error(
                        "Unexpected error processing file %s: %s: %s",
                        file_path,
                        type(e).__name__,
                        e,
                    )
                failed_files += 1
                if self.progress_callback:
                    self.progress_callback(file_path, False)

        return successful_files, failed_files

    def ingest(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 10,
        cores: int | None = None,
    ) -> dict[str, int]:
        """Ingest documents from a file or directory.

        Args:
            path: Path to file or directory to ingest.
            recursive: Recursively process subdirectories.
            batch_size: Number of files to process in parallel (ThreadPool).
            cores: Number of CPU cores for multiprocessing. If None, uses
                config.max_workers or auto-detects CPU count.

        Returns
        -------
            dict with 'success' and 'failed' counts.
        """
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
        )

        from secondbrain.embedding import LocalEmbeddingGenerator
        from secondbrain.storage import VectorStorage

        # Initialize services
        embedding_gen = LocalEmbeddingGenerator()
        storage = VectorStorage()

        # Collect and validate files
        with trace_operation("ingest_collect_files"):
            files = self._collect_and_validate_files(path, recursive)

        if not files:
            return {"success": 0, "failed": 0}

        cores = self._resolve_core_count(cores)

        # Multiprocessing with in-worker embedding for maximum CPU/GPU utilization
        successful, failed = self._process_parallel_with_progress(
            files, embedding_gen, storage, cores
        )

        return {"success": successful, "failed": failed}

    def _extract_text(self, file_path: Path) -> list[Segment]:
        """Extract text content from a file."""
        try:
            with trace_operation("extract_text"):
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


class AsyncDocumentIngestor(DocumentIngestor):
    """Async version of DocumentIngestor for non-blocking document ingestion.

    This class provides asynchronous versions of key document ingestion methods,
    using asyncio.to_thread() to run blocking I/O operations (file reading,
    embedding generation, storage) without blocking the event loop.

    Key Features:
    - Async context manager support (__aenter__, __aexit__)
    - Concurrency control via asyncio.Semaphore for backpressure
    - Streaming mode support for memory-efficient processing
    - Follows storage.py pattern: wrap blocking ops with asyncio.to_thread()
    - Inherits all helper methods from DocumentIngestor
    """

    def __init__(
        self,
        chunk_size: int = 4096,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ) -> None:
        """Initialize async document ingestor.

        Args:
            chunk_size: Size of text chunks in tokens.
            chunk_overlap: Overlap between chunks in tokens.
            verbose: Enable verbose logging.
        """
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            verbose=verbose,
        )

    async def __aenter__(self) -> AsyncDocumentIngestor:
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager - cleanup if needed."""
        # No async cleanup needed currently, but reserved for future use
        pass

    async def ingest_async(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 10,
        max_concurrent: int = 5,
    ) -> dict[str, int]:
        """Ingest documents asynchronously from a file or directory.

        Args:
            path: Path to file or directory to ingest.
            recursive: Recursively process subdirectories.
            batch_size: Number of files to process in parallel.
            max_concurrent: Maximum concurrent file processing tasks (semaphore).

        Returns
        -------
            dict with 'success' and 'failed' counts.
        """
        from secondbrain.config import get_config
        from secondbrain.embedding import LocalEmbeddingGenerator
        from secondbrain.storage import VectorStorage

        # Initialize services
        embedding_gen = LocalEmbeddingGenerator()
        storage = VectorStorage()

        # Collect and validate files
        files = await asyncio.to_thread(
            self._collect_and_validate_files, path, recursive
        )  # type: ignore[attr-defined]

        if not files:
            return {"success": 0, "failed": 0}

        # Semaphore for concurrency control (backpressure)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(file_path: Path) -> bool:
            """Process a single file with semaphore control."""
            async with semaphore:
                return await self.process_file_async(file_path, embedding_gen, storage)

        # Create tasks for all files
        tasks = [process_with_semaphore(f) for f in files]

        # Run all tasks concurrently (limited by semaphore)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        successful = sum(1 for r in results if r is True)
        failed = len(results) - successful

        return {"success": successful, "failed": failed}

    async def process_file_async(
        self,
        file_path: Path,
        embedding_gen: Any,
        storage: Any,
    ) -> bool:
        """Process a single file asynchronously.

        Args:
            file_path: Path to file to process.
            embedding_gen: Embedding generator instance.
            storage: VectorStorage instance.

        Returns
        -------
            True if processing succeeded, False otherwise.
        """
        try:
            # Extract text using to_thread for blocking I/O
            segments = await asyncio.to_thread(self._extract_text, file_path)  # type: ignore[attr-defined]

            if not segments:
                logger.warning(
                    "File %s produced no segments (may be empty, image-only, or extraction failed)",
                    file_path,
                )
                return False

            # Use streaming if enabled (memory-efficient batch processing)
            from secondbrain.config import get_config

            config = get_config()

            if config.streaming_enabled:
                # Streaming handles storage internally via _stream_process_chunks
                docs_count = await asyncio.to_thread(
                    self._stream_process_chunks,
                    file_path,
                    segments,
                    embedding_gen,
                    storage,
                )  # type: ignore[attr-defined]
                return docs_count > 0  # type: ignore[no-any-return]
            else:
                # Legacy batch processing
                docs_to_store = await asyncio.to_thread(
                    self._build_documents_with_embeddings,
                    file_path,
                    segments,
                    embedding_gen,
                )  # type: ignore[attr-defined]
                if docs_to_store:
                    await asyncio.to_thread(storage.store_batch, docs_to_store)
                    return True
                return False

        except (OSError, DocumentExtractionError) as e:
            logger.error("Failed to process %s: %s", file_path, e)
            return False
        except Exception as e:
            logger.error(
                "Unexpected error processing file %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
            return False


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
