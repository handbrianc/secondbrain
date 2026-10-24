"""Asynchronous document ingestion pipeline (Motor/asyncio based)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from secondbrain.config import config
from secondbrain.document.chunker import (
    classify_chunk_role,
    label_to_element_type,
)
from secondbrain.document.fast_text import extract_printed_page, resolve_printed_pages
from secondbrain.document.ingestor._constants import get_file_type
from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.document.structure_capture import capture_structure
from secondbrain.exceptions import DocumentExtractionError
from secondbrain.utils.tracing import trace_operation

if TYPE_CHECKING:
    from secondbrain.storage.structure_sqlite import DocumentStructure

logger = logging.getLogger(__name__)


def _query_existing_hashes(storage: Any, text_hashes: list[str]) -> set[str]:
    """Return which of *text_hashes* already exist in storage, degrading safely.

    Mirrors the sync worker's ``processor._existing_text_hashes`` contract: on
    any storage failure the warning is logged and an empty set is returned so
    the caller re-embeds everything instead of aborting the ingest. Unlike the
    sync worker (which builds a throwaway storage per worker task), the async
    pipeline queries through the storage instance it already owns, so no extra
    connection is created per file.

    Args:
        storage: VectorStorage instance exposing ``has_existing_hashes``.
        text_hashes: Chunk text hashes to look up.

    Returns
    -------
        The subset of *text_hashes* already present in storage; empty when
        the lookup is unnecessary or fails.
    """
    if not text_hashes:
        return set()
    try:
        return set(storage.has_existing_hashes(text_hashes))
    except Exception as e:
        logger.warning(
            "Could not query existing text hashes for re-ingest skip (%s: %s); "
            "proceeding to embed all chunks.",
            type(e).__name__,
            e,
        )
        return set()


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
        # Resource pair created by ``__aenter__`` for ``async with`` usage.
        # ``None`` whenever the ingestor is used without the context manager,
        # in which case ``ingest_async`` creates (and closes) its own pair.
        self._context_embedding_gen: Any | None = None
        self._context_storage: Any | None = None

    async def __aenter__(self) -> AsyncDocumentIngestor:
        """Enter the async context, initializing the shared ingestion resources.

        Builds the same embedding generator and vector storage pair that
        :meth:`ingest_async` uses, so an ``async with`` block ingests through
        one connection pair that :meth:`__aexit__` closes. Any leftover pair
        from a previous enter is closed first, so re-entering cannot leak; if
        the storage factory fails after the generator was created, the
        half-built pair is closed before the error propagates.
        """
        self._close_context_resources()

        from secondbrain.embedding import EmbeddingProviderFactory
        from secondbrain.storage import StorageFactory

        cfg = config()
        embedding_gen = EmbeddingProviderFactory.create_from_config(cfg)
        try:
            storage = StorageFactory.create_from_config(cfg)
        except BaseException:
            with contextlib.suppress(Exception):
                embedding_gen.close()
            raise
        self._context_embedding_gen = embedding_gen
        self._context_storage = storage
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the async context, closing the resources ``__aenter__`` created.

        Closing is idempotent — each close is suppressed and its reference
        reset first — so an exit after ``ingest_async`` already cleaned up
        (or any repeated close) is a safe no-op instead of a double close.
        """
        self._close_context_resources()

    def _close_context_resources(self) -> None:
        """Close the context-owned provider pair; idempotent and leak-safe.

        Each resource's reference is reset to ``None`` before its ``close()``
        runs inside ``contextlib.suppress(Exception)``, so repeated calls
        (a second ``__aenter__``, ``__aexit__`` after an explicit cleanup) are
        no-ops and a raising ``close()`` cannot leave a stale reference.
        """
        for attr_name in ("_context_embedding_gen", "_context_storage"):
            resource = getattr(self, attr_name, None)
            setattr(self, attr_name, None)
            if resource is not None:
                with contextlib.suppress(Exception):
                    resource.close()

    async def ingest_async(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 30,
        max_concurrent: int = 5,
        skip_existing: bool | None = None,
    ) -> dict[str, int | list[tuple[str, str]]]:
        """Ingest documents asynchronously from a file or directory.

        Args:
            path: Path to file or directory to ingest.
            recursive: Recursively process subdirectories.
            batch_size: Number of files to process in parallel.
            max_concurrent: Maximum concurrent file processing tasks (semaphore).
            skip_existing: If True, skip re-embedding/re-storing chunks whose
                text_hash already exists in storage. If None, uses
                config().skip_existing_on_reingest — the same default surface
                as the sync ``ingest()``.

        Returns
        -------
            dict with 'success' and 'failed' counts, 'failures' list of
            (path, reason) tuples for every failed file, and 'skipped'
            (already-stored re-ingest skips) counts — the same shape and skip
            semantics as the sync ``ingest()``: with skip_existing enabled,
            chunks whose text_hash already exists in storage are neither
            re-embedded nor re-stored, and a file whose every chunk is already
            stored is counted once in both 'success' and 'skipped' (never in
            'failed'/'failures'). Failure reasons carry the real cause when
            one was captured — ``"ExceptionType: message"``, the same format
            the sync worker records — while files that fail without a raised
            error (no text extracted, or every embedding attempt failed) fall
            back to the generic no-documents reason.
        """
        from secondbrain.embedding import EmbeddingProviderFactory
        from secondbrain.storage import StorageFactory

        cfg = config()
        # Inside ``async with``, reuse the pair __aenter__ initialized (the
        # context owns and closes it). Plain usage creates a fresh pair that
        # this call owns and closes in its finally — and any leftover partial
        # pair is dropped first so nothing leaks.
        embedding_gen: Any = self._context_embedding_gen
        storage: Any = self._context_storage
        owns_resources = embedding_gen is None or storage is None
        if owns_resources:
            self._close_context_resources()
            embedding_gen = EmbeddingProviderFactory.create_from_config(cfg)
            storage = StorageFactory.create_from_config(cfg)

        skipped_files: set[str] = set()

        try:
            with trace_operation("ingest_collect_files") as span:
                if span is not None:
                    span.set_attribute("ingest.file_path", str(path))
                files = await asyncio.to_thread(
                    self._collect_and_validate_files, path, recursive
                )

            if not files:
                return {"success": 0, "failed": 0, "failures": [], "skipped": 0}

            # Semaphore for concurrency control (backpressure)
            semaphore = asyncio.Semaphore(max_concurrent)

            # ``process_file_async`` records the real per-file error here as
            # "ExceptionType: message" (the sync worker's reason format) so
            # the failures list below can name the true cause, and records
            # fully-skipped re-ingests in ``skipped_files`` the way the sync
            # pool loop counts them.
            captured_reasons: dict[str, str] = {}

            async def process_with_semaphore(file_path: Path) -> bool:
                """Process a single file with semaphore control."""
                async with semaphore:
                    return await self.process_file_async(
                        file_path,
                        embedding_gen,
                        storage,
                        failure_reasons=captured_reasons,
                        skip_existing=skip_existing,
                        skipped_files=skipped_files,
                    )

            tasks = [process_with_semaphore(f) for f in files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful = sum(1 for r in results if r is True)
            failed = len(results) - successful

            # Mirror the sync ingest() return: every failed file carries a
            # (path, reason) entry. A False result carries the real error
            # captured by ``process_file_async`` ("ExceptionType: message",
            # the sync worker's format) when there was one, and otherwise the
            # same generic no-documents reason the sync worker uses.
            # Exceptions that escaped the worker (e.g. cancellation) carry
            # their type and message and are never masked with the generic
            # reason. A skipped file returns True (the sync loop counts a
            # skip as success too) and is reported via 'skipped' only.
            failures: list[tuple[str, str]] = []
            for file_path, result in zip(files, results, strict=True):
                if result is True:
                    continue
                if isinstance(result, BaseException):
                    reason = f"{type(result).__name__}: {result}"
                else:
                    reason = captured_reasons.get(str(file_path)) or (
                        "No documents produced (file may be empty, image-only, "
                        "or extraction failed)"
                    )
                failures.append((str(file_path), reason))

            return {
                "success": successful,
                "failed": failed,
                "failures": failures,
                "skipped": len(skipped_files),
            }
        finally:
            # Only the creator closes its resources: plain usage closes the
            # pair it just built (idempotent-suppressed closes), while the
            # context-owned pair stays open for the with-block and is closed
            # by ``__aexit__``.
            if owns_resources:
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
        skip_hashes: set[str] | None = None,
    ) -> int:
        """Stream process chunks asynchronously for memory efficiency.

        Uses native async embedding generation to avoid blocking the event loop.

        Chunking (dedup + role classification) runs up front inside one
        ``ingest_worker_chunk`` span per file; embeddings and stores still
        flush per batch so memory stays bounded.

        Args:
            file_path: Source file path.
            segments: Extracted text segments to chunk and store.
            embedding_gen: Embedding generator instance.
            storage: VectorStorage instance.
            skip_hashes: Text hashes already present in storage (re-ingest
                skip, mirroring the sync worker's ``skip_existing`` filter);
                matching chunks are neither re-embedded nor re-stored. None
                or empty disables filtering.
        """
        batch_size = config().streaming_chunk_batch_size

        with trace_operation("ingest_worker_chunk") as span:
            if span is not None:
                span.set_attribute("ingest.segments_count", len(segments))

            seen_hashes = set()
            all_chunks: list[dict[str, Any]] = []

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

                # Already stored (re-ingest skip): drop before classification
                # so neither the embedder nor the store sees it again.
                if skip_hashes and text_hash in skip_hashes:
                    continue

                is_likely_title_raw = (
                    len(cleaned) < 100
                    and not any(p in cleaned for p in [".", ":", "-", "—"])
                    and not cleaned.strip().endswith(".")
                )

                labeled_role = label_to_element_type(segment.get("label"))
                chunk_role = (
                    labeled_role
                    if labeled_role is not None
                    else classify_chunk_role(
                        cleaned,
                        stream_seg_counter,
                        stream_total_segs,
                        is_likely_title_raw,
                    )
                )

                all_chunks.append(
                    {
                        "file_path": file_path,
                        "original_index": i,
                        "text": cleaned,
                        "page": segment["page"],
                        "text_hash": text_hash,
                        "chunk_role": chunk_role,
                        "element_type": chunk_role,
                        **{
                            key: segment[key]
                            for key in ("t_start", "t_end")
                            if key in segment
                        },
                    }
                )

                stream_seg_counter += 1

        docs_stored = 0
        for start in range(0, len(all_chunks), batch_size):
            docs_stored += await self._store_embedding_batch_async(
                file_path,
                all_chunks[start : start + batch_size],
                embedding_gen,
                storage,
            )

        return docs_stored

    async def _embed_chunks_async(
        self,
        chunks: list[dict[str, Any]],
        embedding_gen: Any,
    ) -> dict[int, list[float]]:
        """Generate embeddings for a batch of chunks asynchronously.

        Cache-aware: cached texts reuse stored embeddings; uncached texts are
        batch-embedded natively (AI-003), falling back to per-chunk
        ``generate_async`` when batch generation fails. Chunks whose fallback
        also fails are omitted from the returned mapping.
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

        return chunk_to_embedding

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
        with trace_operation("ingest_worker_embed") as span:
            if span is not None:
                span.set_attribute("ingest.chunks_count", len(chunks))
            chunk_to_embedding = await self._embed_chunks_async(chunks, embedding_gen)

        docs_to_store: list[dict[str, Any]] = []
        seen_doc_keys = set()
        page_pos = 0
        last_page: int | None = None

        for chunk_item in chunks:
            text_hash = chunk_item["text_hash"]
            if text_hash not in chunk_to_embedding:
                continue

            doc_key = (str(chunk_item["file_path"]), chunk_item["page"], text_hash)
            if doc_key in seen_doc_keys:
                continue
            seen_doc_keys.add(doc_key)
            if chunk_item["page"] != last_page:
                page_pos = 0
                last_page = chunk_item["page"]

            embedding = chunk_to_embedding[text_hash]
            file_type = get_file_type(chunk_item["file_path"])
            ingested_at = datetime.now(UTC).isoformat()

            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(chunk_item["file_path"]),
                "page_number": chunk_item["page"],
                "printed_page": extract_printed_page(chunk_item["text"]),
                "page_pos": page_pos,
                "chunk_role": chunk_item.get("chunk_role", "body"),
                "element_type": chunk_item.get("element_type", "body"),
                "chunk_text": chunk_item["text"],
                "embedding": embedding,
                "file_type": file_type,
                "ingested_at": ingested_at,
                **{
                    key: chunk_item[key]
                    for key in ("t_start", "t_end")
                    if key in chunk_item
                },
            }
            docs_to_store.append(doc)
            page_pos += 1

        stamped_pages = resolve_printed_pages(docs_to_store)
        if stamped_pages:
            logger.debug(
                "Footer page stamps: %d physical pages stamped for %s",
                stamped_pages,
                file_path,
            )

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
        skip_hashes: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Build documents with embeddings from text segments asynchronously.

        Args:
            file_path: Source file path.
            segments: Extracted text segments to chunk and embed.
            embedding_gen: Embedding generator instance.
            skip_hashes: Text hashes already present in storage (re-ingest
                skip, mirroring the sync worker's ``skip_existing`` filter);
                matching chunks are neither re-embedded nor re-stored. None
                or empty disables filtering.
        """
        with trace_operation("ingest_worker_chunk") as span:
            if span is not None:
                span.set_attribute("ingest.segments_count", len(segments))
            all_chunks = self._deduplicate_and_chunk_segments(file_path, segments)
            if skip_hashes:
                all_chunks = [
                    c for c in all_chunks if c["text_hash"] not in skip_hashes
                ]
        with trace_operation("ingest_worker_embed") as span:
            if span is not None:
                span.set_attribute("ingest.chunks_count", len(all_chunks))
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
        *,
        failure_reasons: dict[str, str] | None = None,
        skip_existing: bool | None = None,
        skipped_files: set[str] | None = None,
    ) -> bool:
        """Process a single file asynchronously.

        Uses native async embedding generation to avoid blocking the event loop.

        Args:
            file_path: Path to file to process.
            embedding_gen: Embedding generator instance.
            storage: VectorStorage instance.
            failure_reasons: Optional mapping keyed by ``str(file_path)`` that
                receives the reason for any error caught here, formatted as
                ``"ExceptionType: message"`` — exactly the format the sync
                worker records — so ``ingest_async``'s ``failures`` list can
                report the true cause instead of the generic no-documents
                reason. ``BaseException`` subclasses such as
                ``asyncio.CancelledError`` are deliberately not caught and not
                recorded here: cancellation propagates to the caller instead
                of being swallowed as a document failure.
            skip_existing: If True, drop chunks whose text_hash already exists
                in storage before embedding (the sync worker's re-ingest
                skip); when every extracted chunk is already stored, the file
                is reported as a skip instead of being reprocessed. If None,
                falls back to config().skip_existing_on_reingest.
            skipped_files: Optional set keyed by ``str(file_path)`` that
                receives every fully-skipped file, so ``ingest_async`` can
                report the same 'skipped' count the sync loop returns (a
                skipped file still counts as a success, exactly as in sync).

        Returns
        -------
            True if processing succeeded — including a fully-skipped re-ingest,
            matching the sync worker's skip-as-success accounting — and False
            otherwise.
        """
        try:
            with trace_operation("ingest_worker_extract") as span:
                if span is not None:
                    span.set_attribute(
                        "ingest.filesize_bytes", file_path.stat().st_size
                    )
                structure_sink: list[Any] = []
                segments = await asyncio.to_thread(
                    self._extract_text, file_path, structure_sink
                )
                # Capture + persist the document's structure tree once per
                # file (design §6). The async path self-extracts via
                # _extract_text — it never consumes processor worker
                # payloads — so the sink filled above is this file's only
                # capture chance (the docling heading part for parseable
                # documents, the extracted ASR capture shape for audio —
                # design §5); it must be consumed before the outcome
                # branches below (skip included). The returned tree feeds
                # the payload refresh (design §6.4) and the audio
                # topic-segmentation hook (design §5) below.
                structure = await self._capture_and_persist_structure_async(
                    file_path, structure_sink
                )

            if not segments:
                logger.warning(
                    "File %s produced no segments (may be empty, image-only, or extraction failed)",
                    file_path,
                )
                return False

            # Audio topic segmentation (design §5): fills audio segment
            # titles in the parent process after the tree is persisted.
            # Runs ahead of the outcome branches so a fully-skipped
            # re-ingest also gains titles; never raises.
            await self._segment_audio_topics_async(file_path, structure, segments)

            # Re-ingest skip detection, mirroring the sync pool worker
            # (``processor._extract_chunk_and_embed_file``): with skip_existing
            # enabled, chunks whose text_hash is already stored are filtered
            # out before embedding, and a file whose every chunk is already
            # stored is reported as a skip (counted as success) instead of
            # being reprocessed. The lookup degrades to "nothing exists" on
            # any storage failure, like the sync worker's.
            cfg = config()
            if skip_existing is None:
                skip_existing = bool(getattr(cfg, "skip_existing_on_reingest", True))

            skip_hashes: set[str] = set()
            if skip_existing:
                chunk_hashes = [
                    c["text_hash"]
                    for c in self._deduplicate_and_chunk_segments(file_path, segments)
                ]
                existing_hashes = _query_existing_hashes(storage, chunk_hashes)
                skip_hashes = {h for h in chunk_hashes if h in existing_hashes}
                if chunk_hashes and len(skip_hashes) == len(chunk_hashes):
                    logger.info(
                        "All %d chunks for %s were already stored; skipping embed/store",
                        len(chunk_hashes),
                        file_path,
                    )
                    if skipped_files is not None:
                        skipped_files.add(str(file_path))
                    # Full skip: nothing was stored fresh, but legacy points
                    # still gain their structural payload (design §6.4).
                    await self._refresh_structure_payload_async(structure, storage)
                    return True

            if cfg.streaming_enabled:
                docs_count = await self._stream_process_chunks_async(
                    file_path,
                    segments,
                    embedding_gen,
                    storage,
                    skip_hashes=skip_hashes,
                )
                await self._refresh_structure_payload_async(structure, storage)
                return docs_count > 0
            else:
                docs_to_store = await self._build_documents_with_embeddings_async(
                    file_path,
                    segments,
                    embedding_gen,
                    skip_hashes=skip_hashes,
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
                    # Freshly stored async points carry no structural keys
                    # (chunk builders treat segments as chunks), so the
                    # refresh annotates them alongside legacy points
                    # (design §6.4).
                    await self._refresh_structure_payload_async(structure, storage)
                    return True
                return False

        except (OSError, DocumentExtractionError) as e:
            logger.error("Failed to process %s: %s", file_path, e)
            if failure_reasons is not None:
                failure_reasons[str(file_path)] = f"{type(e).__name__}: {e}"
            return False
        except Exception as e:
            logger.error(
                "Unexpected error processing file %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
            if failure_reasons is not None:
                failure_reasons[str(file_path)] = f"{type(e).__name__}: {e}"
            return False

    async def _capture_and_persist_structure_async(
        self,
        file_path: Path,
        structure_sink: list[Any],
    ) -> DocumentStructure | None:
        """Capture and persist one file's structure tree (never raises).

        The async twin of the sync pool path's per-file persist (design §6):
        captures the full tree from the capture inputs ``_extract_text``
        collected into the *structure_sink* — the docling heading part for
        parseable documents (PDFs also read the outline and /PageLabels) —
        and saves it through the ingestor's structure store. For audio files
        (design §5) the sink carries the extracted ASR capture shape instead,
        which is handed to the dispatcher's audio branch directly: the ASR
        document itself is already released and heading parts are
        meaningless for a transcript. Any failure is swallowed with a
        warning so ingest continues treeless rather than failing.

        Args:
            file_path: Path to the source file (``str(file_path)`` becomes
                the tree key and MUST equal the qdrant payload
                ``source_file``).
            structure_sink: Capture inputs collected during extraction — the
                docling heading part, or the extracted ASR capture shape for
                audio files (see :meth:`DocumentIngestor._extract_text`);
                possibly empty when the fast path skipped docling.

        Returns
        -------
            The persisted :class:`DocumentStructure`, or None when nothing
            was captured or the structure store is unavailable. The caller
            passes it to the payload refresh (design §6.4) and the audio
            topic-segmentation hook (design §5).
        """
        try:
            file_type = get_file_type(file_path)
            docling_doc: Any = (
                structure_sink[0]
                if file_type == "audio" and structure_sink
                else (structure_sink or None)
            )
            structure = await asyncio.to_thread(
                capture_structure,
                file_path,
                docling_doc,
                file_type,
            )
            if structure is None:
                return None
            store = self._get_structure_store()
            if store is None:
                return None
            await asyncio.to_thread(self._preserve_audio_topics, structure, store)
            await store.save_structure_async(structure)
            return structure
        except Exception as e:
            logger.warning(
                "Failed to persist structure tree for %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
            return None

    async def _refresh_structure_payload_async(
        self, structure: DocumentStructure | None, storage: Any
    ) -> None:
        """Refresh structural payload fields on stored points (never raises).

        Async twin of the sync pool path's refresh (design §6.4): runs after
        this file's points are stored (or on the full-skip return), so
        freshly stored async points — built without inline annotation — and
        legacy dedup-skipped points alike gain their structural payload keys
        from the just-captured tree. A storage without the refresh
        capability is a no-op.

        Args:
            structure: The persisted tree (None → no-op).
            storage: The vector storage instance used for this ingest.
        """
        if structure is None:
            return
        refresh = getattr(storage, "refresh_structural_payload", None)
        if not callable(refresh):
            return
        try:
            refreshed = await asyncio.to_thread(
                refresh, structure.source_file, structure
            )
        except Exception as e:
            logger.warning(
                "Structural payload refresh failed for %s: %s: %s",
                structure.source_file,
                type(e).__name__,
                e,
            )
            return
        if refreshed:
            logger.info(
                "Refreshed structural payload on %d stored points for %s",
                refreshed,
                structure.source_file,
            )

    async def _segment_audio_topics_async(
        self,
        file_path: Path,
        structure: DocumentStructure | None,
        segments: Sequence[Mapping[str, Any]],
    ) -> None:
        """Fill audio segment titles via LLM topic segmentation (never raises).

        Async twin of the sync ingestor's hook (design §5): gated by the
        ``audio_topic_segmentation_enabled`` config flag, bounded to ≤20
        windows, run only for trees carrying audio segment nodes, using the
        extracted segment texts. Produced ``AudioSegment`` rows replace
        ``structure.audio_segments`` and the tree is re-saved; any failure
        preserves compatible prior titles.
        """
        if structure is None or not structure.nodes:
            return
        if not any(node.kind == "segment" for node in structure.nodes):
            return
        cfg = config()
        if not getattr(cfg, "audio_topic_segmentation_enabled", True):
            return
        texts = [str(segment.get("text", "")) for segment in segments]
        if not any(texts):
            return
        store = self._get_structure_store()
        if store is None:
            return
        try:
            from secondbrain.rag.providers.factory import LLMProviderFactory

            llm = await asyncio.to_thread(LLMProviderFactory.create_from_config, cfg)
        except Exception as e:
            logger.warning(
                "LLM provider unavailable for audio topic segmentation (%s: %s)",
                type(e).__name__,
                e,
            )
            return
        try:
            from secondbrain.document.structure_capture import audio_topic_segments

            audio_segments = await asyncio.to_thread(
                audio_topic_segments, structure, texts, llm=llm
            )
        except Exception as e:
            logger.warning(
                "Audio topic segmentation failed for %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
            return
        if not audio_segments:
            return
        self._replace_audio_topics(structure, audio_segments)
        try:
            await store.save_structure_async(structure)
        except Exception as e:
            logger.warning(
                "Failed to persist audio segment titles for %s: %s: %s",
                file_path,
                type(e).__name__,
                e,
            )
