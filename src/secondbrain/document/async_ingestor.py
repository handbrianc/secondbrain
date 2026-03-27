"""Async document ingestion class for non-blocking document processing."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from secondbrain.config import get_config
from secondbrain.document.ingestor import DocumentIngestor
from secondbrain.embedding.local import LocalEmbeddingGenerator
from secondbrain.exceptions import DocumentExtractionError
from secondbrain.storage import VectorStorage

logger = logging.getLogger(__name__)


class AsyncDocumentIngestor(DocumentIngestor):
    """Async version of DocumentIngestor for non-blocking document ingestion.

    Provides asynchronous versions of key document ingestion methods,
    using asyncio.to_thread() to run blocking I/O operations without
    blocking the event loop.
    """

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
        progress_callback: Any = None,
    ) -> dict[str, int]:
        """Ingest asynchronously from a file or directory."""
        embedding_gen = LocalEmbeddingGenerator()
        storage = VectorStorage()

        files = await asyncio.to_thread(
            self._collect_and_validate_files,
            path,
            recursive,
        )

        if not files:
            return {"success": 0, "failed": 0}

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(file_path: Path) -> bool:
            """Process a single file with semaphore control."""
            async with semaphore:
                try:
                    result = await self.process_file_async(
                        file_path, embedding_gen, storage
                    )
                    if progress_callback:
                        progress_callback(file_path, result)
                    return result
                except Exception:
                    if progress_callback:
                        progress_callback(file_path, False)
                    return False

        tasks = [process_with_semaphore(f) for f in files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for r in results if r is True)
        failed = len(results) - successful

        return {"success": successful, "failed": failed}

    async def process_file_async(
        self,
        file_path: Path,
        embedding_gen: Any,
        storage: Any,
    ) -> bool:
        """Process a single file asynchronously."""
        try:
            segments = await asyncio.to_thread(
                self._extract_text,
                file_path,
            )

            if not segments:
                logger.warning(
                    "File %s produced no segments (may be empty, image-only, or extraction failed)",
                    file_path,
                )
                return False

            config = get_config()

            if config.streaming_enabled:
                docs_count = await asyncio.to_thread(
                    self._stream_process_chunks,
                    file_path,
                    segments,
                    embedding_gen,
                    storage,
                )
                return docs_count > 0
            else:
                docs_to_store = await asyncio.to_thread(
                    self._build_documents_with_embeddings,
                    file_path,
                    segments,
                    embedding_gen,
                )
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
