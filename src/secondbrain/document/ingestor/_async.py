"""Asynchronous document ingestion pipeline (Motor/asyncio based)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from secondbrain.config import config
from secondbrain.document.chunker import classify_chunk_role
from secondbrain.document.ingestor._constants import get_file_type
from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.exceptions import DocumentExtractionError
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)


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
        """Exit async context manager."""
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
        from secondbrain.embedding import EmbeddingProviderFactory
        from secondbrain.storage import AsyncVectorStorage

        cfg = config()
        embedding_gen = EmbeddingProviderFactory.create_from_config(cfg)
        storage = AsyncVectorStorage()

        try:
            files = await asyncio.to_thread(
                self._collect_and_validate_files, path, recursive
            )

            if not files:
                return {"success": 0, "failed": 0}

            # Semaphore for concurrency control (backpressure)
            semaphore = asyncio.Semaphore(max_concurrent)

            async def process_with_semaphore(file_path: Path) -> bool:
                """Process a single file with semaphore control."""
                async with semaphore:
                    return await self.process_file_async(
                        file_path, embedding_gen, storage
                    )

            tasks = [process_with_semaphore(f) for f in files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful = sum(1 for r in results if r is True)
            failed = len(results) - successful

            return {"success": successful, "failed": failed}
        finally:
            # Clean up resources to prevent connection leaks
            with contextlib.suppress(Exception):
                embedding_gen.close()
            with contextlib.suppress(Exception):
                storage.close()

    async def _stream_process_chunks_async(
        self,
        file_path: Path,
        segments: list[dict[str, Any]],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Stream process chunks asynchronously for memory efficiency.

        Uses native async embedding generation to avoid blocking the event loop.
        """
        batch_size = config().streaming_chunk_batch_size

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
                docs_stored += await self._store_embedding_batch_async(
                    file_path, batch_chunks, embedding_gen, storage
                )
                batch_chunks = []

        if batch_chunks:
            docs_stored += await self._store_embedding_batch_async(
                file_path, batch_chunks, embedding_gen, storage
            )

        return docs_stored

    async def _store_embedding_batch_async(
        self,
        file_path: Path,
        chunks: list[dict[str, Any]],
        embedding_gen: Any,
        storage: Any,
    ) -> int:
        """Generate embeddings and store a batch of chunks asynchronously.

        Uses native async batch embedding generation for improved throughput
        without blocking the event loop.
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
                # Use native async batch embedding if available
                if hasattr(embedding_gen, "generate_batch_async"):
                    embeddings = await embedding_gen.generate_batch_async(
                        texts_to_embed
                    )
                else:
                    raise TypeError(
                        "EmbeddingGenerator does not implement generate_batch_async; "
                        "async-ingestor spec AI-003 requires native async embedding "
                        "generation. Configure a generator with native async support."
                    )

                for text, embedding in zip(texts_to_embed, embeddings, strict=True):
                    self.embedding_cache.set(text, embedding)
                    chunk = text_to_chunk[text]
                    chunk_to_embedding[chunk["text_hash"]] = embedding
            except Exception as e:
                logger.error(
                    "Failed to generate async batch embeddings: %s: %s",
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
                        if hasattr(embedding_gen, "generate_async"):
                            embedding = await embedding_gen.generate_async(text)
                        else:
                            raise TypeError(
                                "EmbeddingGenerator does not implement generate_async; "
                                "async-ingestor spec AI-003 requires native async single-"
                                "embedding generation. Configure a generator with native "
                                "async support."
                            )
                        self.embedding_cache.set(text, embedding)
                        chunk_to_embedding[chunk["text_hash"]] = embedding
                    except Exception as e2:
                        logger.error(
                            "Failed to generate async embedding: %s: %s",
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
                await storage.store_batch_async(docs_to_store)
                elapsed_ms = (time.time() - start) * 1000
                if span is not None:
                    span.set_attribute("storage.duration_ms", elapsed_ms)

        return len(docs_to_store)

    async def _build_documents_with_embeddings_async(
        self,
        file_path: Path,
        segments: list[dict[str, Any]],
        embedding_gen: Any,
    ) -> list[dict[str, Any]]:
        """Build documents with embeddings from text segments asynchronously."""
        all_chunks = self._deduplicate_and_chunk_segments(file_path, segments)
        chunk_to_embedding = await self._generate_embeddings_with_cache_async(
            all_chunks, embedding_gen
        )
        return self._build_documents_from_chunks(all_chunks, chunk_to_embedding)

    async def _generate_embeddings_with_cache_async(
        self,
        chunks: list[dict[str, Any]],
        embedding_gen: Any,
    ) -> dict[int, list[float]]:
        """Generate embeddings for chunks with async caching and batch processing."""
        batch_size = config().embedding_batch_size
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
                    if hasattr(embedding_gen, "generate_batch_async"):
                        embeddings = await embedding_gen.generate_batch_async(
                            texts_to_embed
                        )
                    else:
                        raise TypeError(
                            "EmbeddingGenerator does not implement generate_batch_async; "
                            "async-ingestor spec AI-003 requires native async embedding "
                            "generation. Configure a generator with native async support."
                        )

                    for idx, embedding in zip(cached_indices, embeddings, strict=True):
                        text = texts[idx]
                        self.embedding_cache.set(text, embedding)
                        chunk_to_embedding[batch[idx]["text_hash"]] = embedding

            except Exception as e:
                logger.error(
                    "Failed to generate async batch embeddings: %s: %s",
                    type(e).__name__,
                    e,
                )
                for chunk in batch:
                    try:
                        cached = self.embedding_cache.get(chunk["text"])
                        if cached is not None:
                            chunk_to_embedding[chunk["text_hash"]] = cached
                            continue

                        if hasattr(embedding_gen, "generate_async"):
                            embedding = await embedding_gen.generate_async(
                                chunk["text"]
                            )
                        else:
                            raise TypeError(
                                "EmbeddingGenerator does not implement generate_async; "
                                "async-ingestor spec AI-003 requires native async single-embedding "
                                "generation. Configure a generator with native async support."
                            )
                        self.embedding_cache.set(chunk["text"], embedding)
                        chunk_to_embedding[chunk["text_hash"]] = embedding
                    except Exception as e2:
                        logger.error(
                            "Failed to generate async embedding for chunk: %s: %s",
                            type(e2).__name__,
                            e2,
                        )
                        continue

        return chunk_to_embedding

    async def process_file_async(
        self,
        file_path: Path,
        embedding_gen: Any,
        storage: Any,
    ) -> bool:
        """Process a single file asynchronously.

        Uses native async embedding generation to avoid blocking the event loop.

        Args:
            file_path: Path to file to process.
            embedding_gen: Embedding generator instance.
            storage: VectorStorage instance.

        Returns
        -------
            True if processing succeeded, False otherwise.
        """
        try:
            segments = await asyncio.to_thread(self._extract_text, file_path)

            if not segments:
                logger.warning(
                    "File %s produced no segments (may be empty, image-only, or extraction failed)",
                    file_path,
                )
                return False

            from secondbrain.config import config

            if config().streaming_enabled:
                docs_count = await self._stream_process_chunks_async(
                    file_path, segments, embedding_gen, storage
                )
                return docs_count > 0
            else:
                docs_to_store = await self._build_documents_with_embeddings_async(
                    file_path, segments, embedding_gen
                )
                if docs_to_store:
                    with trace_operation("storage.store") as span:
                        if span is not None:
                            span.set_attribute(
                                "storage.documents_stored",
                                len(docs_to_store),
                            )
                        start = time.time()
                        await storage.store_batch_async(docs_to_store)
                        elapsed_ms = (time.time() - start) * 1000
                        if span is not None:
                            span.set_attribute("storage.duration_ms", elapsed_ms)
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
