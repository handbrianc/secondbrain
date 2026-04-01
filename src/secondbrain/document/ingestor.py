"""Document ingestion class for processing and embedding documents."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# get_config imported at runtime
from secondbrain.document.converter import DocumentConverterWrapper
from secondbrain.document.segment import Segment
from secondbrain.document.utils import get_file_type
from secondbrain.document.worker import init_worker_with_queue
from secondbrain.embedding.local import LocalEmbeddingGenerator
from secondbrain.exceptions import DocumentExtractionError, ValidationError
from secondbrain.storage import VectorStorage
from secondbrain.utils.embedding_cache import EmbeddingCache
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)
MAX_MEMORY_BATCH_SIZE = 100


class DocumentIngestor:
    """Handles document ingestion, chunking, embedding generation, and storage."""

    def __init__(
        self,
        chunk_size: int = 4096,
        chunk_overlap: int = 50,
        verbose: bool = False,
        progress_callback: Callable[[Path, bool], None] | None = None,
    ) -> None:
        """Initialize document ingestor."""
        from secondbrain.document import get_config

        config = get_config()

        if chunk_size <= 0:
            raise ValidationError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValidationError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValidationError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose
        self.max_file_size_bytes: int = config.max_file_size_bytes
        self.progress_callback = progress_callback
        self.embedding_cache = EmbeddingCache(max_size=config.embedding_cache_size)
        self.converter = DocumentConverterWrapper()

    def _validate_file_path(self, path: Path) -> None:
        """Validate file path for security."""
        resolved_path = path.resolve()
        if ".." in path.parts:
            raise ValueError(
                f"Path traversal detected: '{path}' contains '..' sequence"
            )
        normalized = str(resolved_path).lower()
        if "%2e%2e" in normalized or "%2e." in normalized:
            raise ValueError(f"Encoded path traversal detected in: '{path}'")

    def _validate_file_size(self, path: Path) -> None:
        """Validate file size does not exceed limit."""
        file_size = path.stat().st_size
        if file_size > self.max_file_size_bytes:
            raise ValueError(
                f"File '{path}' exceeds maximum size limit of "
                f"{self.max_file_size_bytes / (1024 * 1024):.0f}MB "
                f"(actual: {file_size / (1024 * 1024):.2f}MB)"
            )

    def _collect_and_validate_files(self, path: str, recursive: bool) -> list[Path]:
        """Collect and validate files from path."""
        from secondbrain.document.utils import is_supported

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

    def _extract_text(self, file_path: Path) -> list[Segment]:
        """Extract text content from a file."""
        return self.converter.extract_text(file_path)

    def _chunk_text(self, segments: list[Segment]) -> list[Segment]:
        """Chunk segments into smaller pieces (backward compatibility alias).

        This is an alias for _deduplicate_and_chunk_segments without the file_path.
        Used by tests for backward compatibility.
        """
        from secondbrain.document.segment import chunk_segments

        return list(chunk_segments(segments, self.chunk_size, self.chunk_overlap))

    def _deduplicate_and_chunk_segments(
        self, file_path: Path, segments: list[Segment]
    ) -> list[dict[str, Any]]:
        """Deduplicate and chunk text segments, adding metadata.

        First deduplicates segments based on normalized text content,
        then chunks the unique segments.
        """
        from secondbrain.document.segment import chunk_segments

        # First, deduplicate segments based on normalized text
        seen_hashes: dict[str, dict[str, Any]] = {}
        for segment in segments:
            cleaned = segment["text"].strip()
            if not cleaned:
                continue
            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()
            if text_hash not in seen_hashes:
                seen_hashes[text_hash] = {
                    "text": cleaned,
                    "page": segment["page"],
                }

        # Then chunk the deduplicated segments
        unique_segments: list[Segment] = [
            {"text": item["text"], "page": item["page"]}
            for item in seen_hashes.values()
        ]

        chunks = chunk_segments(unique_segments, self.chunk_size, self.chunk_overlap)

        # Add file_path and text_hash to each chunk
        result = []
        for chunk in chunks:
            cleaned = chunk["text"].strip()
            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()
            result.append(
                {
                    "text": cleaned,
                    "page": chunk["page"],
                    "file_path": file_path,
                    "text_hash": text_hash,
                }
            )

        return result

    def _generate_embeddings_with_cache(
        self, chunks: list[dict[str, Any]], embedding_gen: Any
    ) -> dict[int, list[float]]:
        """Generate embeddings for chunks with caching."""
        # get_config imported at runtime

        from secondbrain.document import get_config

        config = get_config()
        batch_size = config.embedding_batch_size
        chunk_to_embedding: dict[int, list[float]] = {}

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [chunk["text"] for chunk in batch]
            try:
                texts_to_embed, cached_indices = [], []
                for idx, text in enumerate(texts):
                    cached = self.embedding_cache.get(text)
                    if cached is not None:
                        chunk_to_embedding[batch[idx]["text_hash"]] = cached
                    else:
                        texts_to_embed.append(text)
                        cached_indices.append(idx)
                if texts_to_embed:
                    embeddings = embedding_gen.generate_batch(texts_to_embed)
                    for idx, embedding in zip(cached_indices, embeddings, strict=True):
                        text = texts[idx]
                        self.embedding_cache.set(text, embedding)
                        chunk_to_embedding[batch[idx]["text_hash"]] = embedding
            except Exception as e:
                logger.error(
                    "Failed to generate batch embeddings: %s: %s", type(e).__name__, e
                )
                for chunk in batch:
                    try:
                        cached = self.embedding_cache.get(chunk["text"])
                        if cached is not None:
                            chunk_to_embedding[chunk["text_hash"]] = cached
                            continue
                        embedding = embedding_gen.generate(chunk["text"])
                        self.embedding_cache.set(chunk["text"], embedding)
                        chunk_to_embedding[chunk["text_hash"]] = embedding
                    except Exception as e:
                        logger.warning("Failed to generate embedding for chunk: {e}")
                        continue
        return chunk_to_embedding

    def _build_documents_from_chunks(
        self, chunks: list[dict[str, Any]], chunk_to_embedding: dict[int, list[float]]
    ) -> list[dict[str, Any]]:
        """Build document dictionaries from chunks with embeddings."""
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
            ingested_at = datetime.now(UTC).isoformat()
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(chunk_item["file_path"]),
                "page_number": chunk_item["page"],
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
            }
            docs_to_store.append(doc)
        return docs_to_store

    def _build_documents_with_embeddings(
        self, file_path: Path, segments: list[Segment], embedding_gen: Any
    ) -> list[dict[str, Any]]:
        """Build documents with embeddings from text segments."""
        all_chunks = self._deduplicate_and_chunk_segments(file_path, segments)
        chunk_to_embedding = self._generate_embeddings_with_cache(
            all_chunks, embedding_gen
        )
        return self._build_documents_from_chunks(all_chunks, chunk_to_embedding)

    def _stream_process_chunks(
        self,
        file_path: Path,
        segments: list[Segment],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Stream process chunks for memory efficiency."""
        # get_config imported at runtime

        from secondbrain.document import get_config

        config = get_config()
        batch_size = config.streaming_chunk_batch_size
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
            if len(batch_chunks) >= batch_size:
                docs_stored += self._store_embedding_batch(
                    file_path, batch_chunks, embedding_gen, storage
                )
                batch_chunks = []
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
        """Generate embeddings and store a batch of chunks."""
        chunk_to_embedding: dict[int, list[float]] = {}
        texts_to_embed: list[str] = []
        text_to_chunk: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            cached = self.embedding_cache.get(chunk["text"])
            if cached is not None:
                chunk_to_embedding[chunk["text_hash"]] = cached
                continue
            texts_to_embed.append(chunk["text"])
            text_to_chunk[chunk["text"]] = chunk
        if texts_to_embed:
            try:
                embeddings = embedding_gen.generate_batch(texts_to_embed)
                for text, embedding in zip(texts_to_embed, embeddings, strict=True):
                    self.embedding_cache.set(text, embedding)
                    chunk = text_to_chunk[text]
                    chunk_to_embedding[chunk["text_hash"]] = embedding
            except Exception as e:
                logger.error(
                    "Failed to generate batch embeddings: %s: %s", type(e).__name__, e
                )
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
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate embedding for chunk in streaming: {e}"
                        )
                        continue
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
            ingested_at = datetime.now(UTC).isoformat()
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(chunk_item["file_path"]),
                "page_number": chunk_item["page"],
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
            }
            docs_to_store.append(doc)
        if docs_to_store:
            storage.store_batch(docs_to_store)
        return len(docs_to_store)

    def _process_file_for_storage(
        self, file_path: Path, embedding_gen: Any
    ) -> list[dict[str, Any]] | None:
        """Process a single file - uses streaming if enabled."""
        # get_config imported at runtime

        from secondbrain.document import get_config

        config = get_config()
        try:
            segments = self._extract_text(file_path)
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
        if config.streaming_enabled:
            storage = VectorStorage()
            docs_count = self._stream_process_chunks(
                file_path, segments, embedding_gen, storage
            )
            return [] if docs_count > 0 else None
        else:
            return self._build_documents_with_embeddings(
                file_path, segments, embedding_gen
            )

    def _resolve_core_count(self, cores: int | None) -> int:
        """Resolve and validate core count for parallel processing."""
        from secondbrain.document import get_config

        config = get_config()
        if cores is None:
            cores = config.max_workers or os.cpu_count() or 1
        if cores <= 0:
            raise ValueError("cores must be positive")
        return cores

    def _get_safe_worker_count(self, cores: int) -> int:
        """Calculate safe worker count based on memory constraints.

        Args:
            cores: CPU cores available.

        Returns:
            Safe number of worker processes considering memory limits.
        """
        from secondbrain.config import get_config
        from secondbrain.utils.memory_utils import (
            calculate_safe_worker_count,
            get_memory_limit_gb,
        )

        config = get_config()

        # Calculate memory limit in GB
        memory_limit_gb = get_memory_limit_gb(config.memory_limit_percent)

        # Convert per-worker estimate to GB
        memory_per_worker_gb = config.estimated_memory_per_worker_mb / 1024

        # Calculate safe worker count based on memory
        safe_workers = calculate_safe_worker_count(
            memory_limit_gb=memory_limit_gb,
            estimated_memory_per_worker_gb=memory_per_worker_gb,
            min_workers=1,
            max_workers=cores,
        )

        logger.info(
            "Worker count: %d (CPU cores: %d, memory limit: %.2fGB, "
            "memory per worker: %.2fGB, limit: %.0f%%)",
            safe_workers,
            cores,
            memory_limit_gb,
            memory_per_worker_gb,
            config.memory_limit_percent * 100,
        )

        return safe_workers

    def _process_parallel_with_progress(
        self, files: list[Path], embedding_gen: Any, storage: Any, max_workers: int
    ) -> tuple[int, int]:
        """Process files using multiprocessing with progress callback support."""
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from multiprocessing import Manager

        # get_config imported at runtime
        from secondbrain.document.worker import extract_chunk_and_embed_file

        successful_files, failed_files = 0, 0
        from secondbrain.document import get_config

        config = get_config()
        with Manager() as manager:
            progress_queue = manager.Queue()
            embedding_model_name = config.local_embedding_model
            with (
                trace_operation("ingest_multiprocess_progress"),
                ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=init_worker_with_queue,
                    initargs=(progress_queue, embedding_model_name, max_workers),
                ) as executor,
            ):
                futures = {
                    executor.submit(
                        extract_chunk_and_embed_file,
                        str(f),
                        self.chunk_size,
                        self.chunk_overlap,
                        progress_queue,
                        embedding_model_name,
                    ): f
                    for f in files
                }
                pending_futures = dict(futures)
                while pending_futures:
                    while not progress_queue.empty():
                        try:
                            progress_queue.get_nowait()
                        except Exception:
                            break
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
                                if self.progress_callback:
                                    self.progress_callback(file_path, False)
                                done_futures.append(future)
                                continue
                            for i in range(0, len(documents), MAX_MEMORY_BATCH_SIZE):
                                storage.store_batch(
                                    documents[i : i + MAX_MEMORY_BATCH_SIZE]
                                )
                            successful_files += 1
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
                            if self.progress_callback:
                                self.progress_callback(file_path, False)
                            done_futures.append(future)
                    for future in done_futures:
                        del pending_futures[future]
                    if pending_futures:
                        time.sleep(0.01)
        return successful_files, failed_files

    def ingest(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 10,
        cores: int | None = None,
        progress_callback: Callable[[Path, bool], None] | None = None,
    ) -> dict[str, int]:
        """Ingest documents from a file or directory."""
        if progress_callback is not None:
            self.progress_callback = progress_callback
        embedding_gen = LocalEmbeddingGenerator()
        storage = VectorStorage()
        with trace_operation("ingest_collect_files"):
            files = self._collect_and_validate_files(path, recursive)
        if not files:
            return {"success": 0, "failed": 0}
        cores = self._resolve_core_count(cores)
        # Calculate safe worker count based on memory constraints
        safe_workers = self._get_safe_worker_count(cores)
        successful, failed = self._process_parallel_with_progress(
            files, embedding_gen, storage, safe_workers
        )
        return {"success": successful, "failed": failed}
