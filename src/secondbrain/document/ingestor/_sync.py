"""Synchronous document ingestion pipeline (extract -> chunk -> embed -> store)."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from secondbrain.config import config
from secondbrain.document.chunker import classify_chunk_role
from secondbrain.document.ingestor._constants import (
    MAX_MEMORY_BATCH_SIZE,
    _detect_cpu_count,
    _element_text,
    get_file_type,
    is_supported,
)
from secondbrain.exceptions import DocumentExtractionError
from secondbrain.storage import VectorStorage
from secondbrain.utils.embedding_cache import EmbeddingCache
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)


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
        import secondbrain.document

        cfg = secondbrain.document.config()

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose
        self.max_file_size_bytes: int = cfg.max_file_size_bytes
        self.progress_callback = progress_callback
        self._cpu_count_fn = _detect_cpu_count

        self.embedding_cache = EmbeddingCache(max_size=cfg.embedding_cache_size)

        # Lazily import docling via the shared factory to avoid 2+ second import
        # overhead. The heavyweight docling imports happen inside the factory on
        # first call, not at module import time.
        import logging

        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        logging.getLogger("docling").setLevel(logging.WARNING)

        from secondbrain.document.docling_factory import get_shared_converter

        self.converter = get_shared_converter()

    def _validate_file_path(self, path: Path) -> None:
        """Validate file path for security.

        Args:
            path: Path to validate.

        Raises
        ------
            ValueError: If path contains traversal sequences or is outside allowed directory.
        """
        resolved_path = path.resolve()

        if ".." in path.parts:
            raise ValueError(
                f"Path traversal detected: '{path}' contains '..' sequence"
            )

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
        from secondbrain.config import config

        cfg = config()

        try:
            segments: list[dict[str, Any]] = self._extract_text(file_path)
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

        if cfg.streaming_enabled:
            storage = VectorStorage()
            docs_count = self._stream_process_chunks(
                file_path, segments, embedding_gen, storage
            )
            return [] if docs_count > 0 else None
        else:
            return self._build_documents_with_embeddings(
                file_path=file_path,
                segments=segments,
                embedding_gen=embedding_gen,
            )

    def _deduplicate_and_chunk_segments(
        self,
        file_path: Path,
        segments: list[dict[str, Any]],
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
        from secondbrain.config import config

        cfg = config()
        batch_size = cfg.embedding_batch_size
        chunk_to_embedding: dict[int, list[float]] = {}

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [chunk["text"] for chunk in batch]

            try:
                texts_to_embed = []
                cached_indices = []

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
                    "Failed to generate batch embeddings: %s: %s",
                    type(e).__name__,
                    e,
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
            ingested_at = datetime.now(UTC).isoformat()

            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(chunk_item["file_path"]),
                "page_number": chunk_item["page"],
                "chunk_role": chunk_item.get("chunk_role", "body"),
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
            }
            docs_to_store.append(doc)

        return docs_to_store

    def _build_documents_with_embeddings(
        self,
        file_path: Path,
        segments: list[dict[str, Any]],
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
        all_chunks = self._deduplicate_and_chunk_segments(file_path, segments)
        chunk_to_embedding = self._generate_embeddings_with_cache(
            all_chunks, embedding_gen
        )
        return self._build_documents_from_chunks(all_chunks, chunk_to_embedding)

    def _stream_process_chunks(
        self,
        file_path: Path,
        segments: list[dict[str, Any]],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Stream process chunks for memory efficiency.

        WHY STREAMING PROCESSING?
        -------------------------
        Traditional batch processing loads ALL chunks into memory, generates ALL
        embeddings, THEN stores everything. This causes memory issues for large
        documents (100+ pages) where thousands of embeddings might consume GBs of RAM.

        Streaming processes in small batches:
        1. Collect chunks until batch is full (streaming_chunk_batch_size)
        2. Generate embeddings for batch only
        3. Store batch immediately to MongoDB
        4. Discard batch from memory, repeat

        Memory Impact:
        - Batch processing (1000 chunks): 1000 embeddings in RAM simultaneously
          1000 x 384 floats x 8 bytes = ~3MB per document
          100 documents = 300MB+ RAM
        - Streaming (batch=50): Only 50 embeddings in RAM at once
          50 x 384 floats x 8 bytes = ~150KB per batch
          100 documents = constant ~150KB RAM usage

        Trade-offs:
        - Pros: Constant memory usage regardless of document size
        - Pros: Early persistence (data saved incrementally)
        - Cons: More MongoDB write operations (mitigated by batching)
        - Cons: Slightly more complex code

        When to Enable:
        - Large documents (100+ pages)
        - Memory-constrained environments (<8GB RAM)
        - Batch processing many files
        - Production systems requiring stability

        When to Disable:
        - Small documents (<10 pages)
        - Memory is abundant
        - Need all embeddings in memory for post-processing
        """
        from secondbrain.config import config

        cfg = config()
        batch_size = cfg.streaming_chunk_batch_size  # Default: 50 chunks/batch

        seen_hashes = set()
        batch_chunks: list[dict[str, Any]] = []
        docs_stored = 0

        stream_seg_counter = 0
        stream_total_segs = len(segments)

        for i, segment in enumerate(segments):
            cleaned = segment["text"].strip()
            if not cleaned:
                continue

            normalized = " ".join(cleaned.lower().split())
            text_hash = hashlib.sha256(normalized.encode()).hexdigest()

            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)

            is_likely_title_raw = (
                len(cleaned) < 100
                and not any(p in cleaned for p in [".", ":", "-", "—"])
                and not cleaned.strip().endswith(".")
            )

            batch_chunks.append(
                {
                    "file_path": file_path,
                    "original_index": i,
                    "text": cleaned,
                    "page": segment["page"],
                    "text_hash": text_hash,
                    "chunk_role": classify_chunk_role(
                        cleaned,
                        stream_seg_counter,
                        stream_total_segs,
                        is_likely_title_raw,
                    ),
                }
            )

            stream_seg_counter += 1

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
                    "Failed to generate batch embeddings: %s: %s",
                    type(e).__name__,
                    e,
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
                    except Exception as e2:
                        logger.error(
                            "Failed to generate embedding: %s: %s",
                            type(e2).__name__,
                            e2,
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
                "chunk_role": chunk_item.get("chunk_role", "body"),
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
            }
            docs_to_store.append(doc)

        if docs_to_store:
            with trace_operation("storage.store") as span:
                if span is not None:
                    span.set_attribute("storage.documents_stored", len(docs_to_store))
                start = time.time()
                storage.store_batch(docs_to_store)
                elapsed_ms = (time.time() - start) * 1000
                if span is not None:
                    span.set_attribute("storage.duration_ms", elapsed_ms)

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
        cfg = config()
        if cores is None:
            raw = (
                cfg.max_workers
                if cfg.max_workers is not None
                else self._cpu_count_fn() or 1
            )
            cores = raw
            if (
                cfg.max_workers is None
                and cfg.max_ingest_processes
                and cfg.max_ingest_processes > 0
                and cores > cfg.max_ingest_processes
            ):
                cores = cfg.max_ingest_processes

        if cores <= 0:
            raise ValueError("cores must be positive")

        return cores

    def _process_parallel_with_progress(
        self,
        files: list[Path],
        embedding_gen: Any,
        storage: Any,
        max_workers: int,
        pool: str | None = None,
        skip_existing: bool | None = None,
    ) -> tuple[int, int, list[tuple[str, str]]]:
        """Process files using thread or process pooling with progress support.

        Uses a ThreadPoolExecutor (shared queue + memory, real-time progress) or a
        ProcessPoolExecutor (multicore CPU-bound extraction) depending on the
        configured ``ingest_pool``. The main thread always owns storage: it consumes
        every future and stores batches, so writes stay single-writer for both pools.

        For the process path the threading Queue and the thread-local embedding cache
        are NOT pickleable across process boundaries, so they are replaced with None:
        each child re-initializes its own (empty) embedding cache inside the worker and
        batching still applies. Progress is aggregated by the owner from each returned
        result (success or failure advances the bar exactly once per file).

        Args:
            files: List of file paths to process.
            embedding_gen: EmbeddingGenerator instance.
            storage: VectorStorage instance.
            max_workers: Number of worker threads/processes.
            pool: Pool type: 'process', 'thread', or None to use config().ingest_pool.

        Returns
        -------
            Tuple of (successful_files, failed_files, failure_reasons) counts and reasons.
        """
        import queue
        from concurrent.futures import as_completed

        from secondbrain.config import config

        cfg = config()
        if pool is None:
            pool = cfg.ingest_pool
        if pool not in ("process", "thread"):
            raise ValueError(f"ingest_pool must be 'process' or 'thread', got {pool!r}")

        if skip_existing is None:
            skip_existing = bool(getattr(cfg, "skip_existing_on_reingest", True))

        use_process = pool == "process"

        successful_files = 0
        failed_files = 0
        failure_reasons: list[tuple[str, str]] = []

        progress_queue: queue.Queue[tuple[str, bool]] | None = None
        embedding_model_name = cfg.embedding_model

        # Import worker from processor (not extractor) to avoid cyclic import
        from secondbrain.document.processor import _extract_chunk_and_embed_file

        executor_cls: type[ThreadPoolExecutor] | type[ProcessPoolExecutor] = (
            ProcessPoolExecutor if use_process else ThreadPoolExecutor
        )

        if not use_process:
            progress_queue = queue.Queue()

        # CPU/GPU guard: force-OCR runs OCR (often GPU/MPS-backed) inside every PDF, and
        # many processes contending on one GPU thrash each other. Cap the process pool
        # to a single worker when OCR is forced on (pdf_ocr_enabled=True). On-demand OCR
        # (default) leaves the fast text path untouched, so no cap is applied.
        if use_process and cfg.pdf_ocr_enabled:
            logger.warning(
                "pdf_ocr_enabled is set (force OCR on all PDFs); capping process pool "
                "to 1 worker to avoid GPU/MPS contention between processes."
            )
            max_workers = 1

        with (
            trace_operation("ingest_thread_progress") as span,
            executor_cls(max_workers=max_workers) as executor,
        ):
            if span:
                span.set_attribute("ingestion.files_total", len(files))
                span.set_attribute("ingestion.max_workers", max_workers)
                span.set_attribute("ingestion.pool", pool)

            if use_process:
                # Workers run in child processes. The threading Queue and the
                # thread-local embedding cache (Todo 3) cannot be pickled across the
                # process boundary, so pass None for both. Each child re-initializes
                # its own empty embedding cache inside the worker and batching still
                # applies; progress is aggregated here from returned results.
                def worker_args(f: Path) -> tuple[Any, Any, Any, Any, Any, Any]:
                    return (
                        str(f),
                        self.chunk_size,
                        self.chunk_overlap,
                        None,
                        embedding_model_name,
                        None,
                    )

            else:

                def worker_args(f: Path) -> tuple[Any, Any, Any, Any, Any, Any]:
                    return (
                        str(f),
                        self.chunk_size,
                        self.chunk_overlap,
                        progress_queue,
                        embedding_model_name,
                        self.embedding_cache,
                    )

            futures = {
                executor.submit(
                    _extract_chunk_and_embed_file,
                    *worker_args(f),
                    skip_existing=skip_existing,
                ): f
                for f in files
            }

            completed = 0
            pending_futures = dict(futures)

            while pending_futures:
                if progress_queue is not None:
                    while not progress_queue.empty():
                        try:
                            progress_queue.get_nowait()
                        except queue.Empty:
                            break

                done_futures = []
                for future in as_completed(pending_futures, timeout=3600):
                    file_path = futures[future]
                    try:
                        result = future.result(timeout=300)

                        if not result["success"]:
                            error_msg = result.get("error", "Unknown error")
                            logger.error(
                                "Failed to process %s: %s",
                                file_path,
                                error_msg,
                            )
                            failed_files += 1
                            failure_reasons.append((str(file_path), error_msg))
                            completed += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, False)
                            done_futures.append(future)
                            continue

                        documents = result.get("documents", [])
                        skipped = result.get("skipped", False)
                        if skipped and not documents:
                            successful_files += 1
                            completed += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, True)
                            done_futures.append(future)
                            continue

                        if not documents:
                            reason = "No documents produced (file may be empty, image-only, or extraction failed)"
                            logger.warning("No documents produced from %s", file_path)
                            failed_files += 1
                            failure_reasons.append((str(file_path), reason))
                            completed += 1
                            if self.progress_callback:
                                self.progress_callback(file_path, False)
                            done_futures.append(future)
                            continue

                        for i in range(0, len(documents), MAX_MEMORY_BATCH_SIZE):
                            batch = documents[i : i + MAX_MEMORY_BATCH_SIZE]
                            with trace_operation("storage.store") as span:
                                if span is not None:
                                    span.set_attribute(
                                        "storage.documents_stored", len(batch)
                                    )
                                start = time.time()
                                storage.store_batch(batch)
                                elapsed_ms = (time.time() - start) * 1000
                                if span is not None:
                                    span.set_attribute(
                                        "storage.duration_ms", elapsed_ms
                                    )

                        successful_files += 1
                        completed += 1
                        if self.progress_callback:
                            self.progress_callback(file_path, True)
                        done_futures.append(future)

                    except Exception as e:
                        error_msg = f"{type(e).__name__}: {e}"
                        logger.error(
                            "Unexpected error processing file %s: %s",
                            file_path,
                            error_msg,
                        )
                        failed_files += 1
                        failure_reasons.append((str(file_path), error_msg))
                        completed += 1
                        if self.progress_callback:
                            self.progress_callback(file_path, False)
                        done_futures.append(future)

                for future in done_futures:
                    del pending_futures[future]

                if pending_futures:
                    time.sleep(0.01)

        return successful_files, failed_files, failure_reasons

    def ingest(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 30,
        cores: int | None = None,
        pool: str | None = None,
        skip_existing: bool | None = None,
    ) -> dict[str, int | list[tuple[str, str]]]:
        """Ingest documents from a file or directory.

        Args:
            path: Path to file or directory to ingest.
            recursive: Recursively process subdirectories.
            batch_size: Number of files to process in parallel (ThreadPool).
            cores: Number of CPU cores for threading. If None, uses
                config.max_workers or auto-detects CPU count.
            pool: Pool type: 'process', 'thread', or None to use config().ingest_pool.
            skip_existing: If True, skip re-embedding/re-storing chunks whose
                text_hash already exists. If None, uses
                config().skip_existing_on_reingest.

        Returns
        -------
            dict with 'success', 'failed' counts, and 'failures' list of (path, reason) tuples.
        """
        from secondbrain.config import config
        from secondbrain.embedding import EmbeddingProviderFactory
        from secondbrain.storage import VectorStorage

        cfg = config()
        embedding_gen = EmbeddingProviderFactory.create_from_config(cfg)
        storage = VectorStorage()

        with trace_operation("ingest_collect_files"):
            files = self._collect_and_validate_files(path, recursive)

        if not files:
            return {"success": 0, "failed": 0, "failures": []}

        cores = self._resolve_core_count(cores)

        successful, failed, failure_reasons = self._process_parallel_with_progress(
            files, embedding_gen, storage, cores, pool, skip_existing
        )

        return {"success": successful, "failed": failed, "failures": failure_reasons}

    def _extract_text(self, file_path: Path) -> list[dict[str, Any]]:
        """Extract text content from a file."""
        try:
            from secondbrain.document.fast_text import try_fast_pdf_extraction

            segments = try_fast_pdf_extraction(file_path)
            if segments is None:
                with trace_operation("extract_text"):
                    from secondbrain.document.docling_factory import (
                        get_converter_for_path,
                    )

                    converter = get_converter_for_path(file_path)
                    result = converter.convert(file_path)
                    content = result.document

                    segments = []

                    if hasattr(content, "texts") and content.texts:
                        for text_item in content.texts:
                            txt = _element_text(text_item)
                            if not txt:
                                continue

                            page_num = 1
                            prov = getattr(text_item, "prov", None) or []
                            if prov:
                                p = prov[0]
                                if hasattr(p, "page_no"):
                                    page_num = p.page_no

                            segments.append({"text": txt, "page": page_num})

                    if not segments:
                        with file_path.open(encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                            segments = [{"text": text, "page": 1}]

                return segments

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

    def _chunk_text(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Split segments into overlapping chunks.

        Args:
            segments: List of text segments to chunk.

        Returns
        -------
            List of chunked segments with overlapping text.
        """
        chunks: list[dict[str, Any]] = []

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
