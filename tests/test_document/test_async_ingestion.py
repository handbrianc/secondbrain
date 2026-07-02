"""Tests for async ingestion path - AI-003 spec verification.

Verifies that AsyncDocumentIngestor._store_embedding_batch_async() calls
generate_batch_async() natively (directly awaited) without asyncio.to_thread()
wrapper, satisfying the AI-003 async-ingestor spec requirement.

The AI-003 invariant enforced here:
  In ingestor.py:1417-1420, the call MUST be:
    embeddings = await embedding_gen.generate_batch_async(texts_to_embed)
  NOT:
    embeddings = await asyncio.to_thread(embedding_gen.generate_batch_async, texts_to_embed)

Wrapping a native async method in asyncio.to_thread() is incorrect because
asyncio.to_thread() runs the callable in a thread pool but never awaits the
result -- producing a silent bug where the coroutine is never resolved.
"""

import asyncio
import inspect
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_stub = MagicMock()
for mod_name in (
    "docling",
    "docling.datamodel",
    "docling.datamodel.accelerator_options",
    "docling.datamodel.base_models",
    "docling.datamodel.pipeline_options",
    "docling.document_converter",
    "docling.document_converter_PdfFormatOption",
):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _stub

from secondbrain.document.ingestor import AsyncDocumentIngestor


class TestAsyncIngestionNativeAwait:
    """Verify generate_batch_async is awaited directly, not via asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_generate_batch_async_is_awaited_directly_without_to_thread(
        self,
    ) -> None:
        """_store_embedding_batch_async invokes generate_batch_async natively (no to_thread)."""
        sentinel_errors: list[str] = []
        original_to_thread = asyncio.to_thread

        def _sentinel_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            if callable(func):
                code = getattr(func, "__code__", None)
                if code is not None:
                    co_flags = getattr(code, "co_flags", 0)
                    if co_flags & inspect.CO_COROUTINE:
                        sentinel_errors.append(
                            f"asyncio.to_thread() called with coroutine ({func}). "
                            "AI-003 requires: await gen.generate_batch_async(texts)"
                        )
            return original_to_thread(func, *args, **kwargs)

        THREE_EMBEDDINGS = [[0.1] * 384 for _ in range(3)]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate_batch_async = AsyncMock(
            return_value=THREE_EMBEDDINGS
        )
        mock_embedding_gen.generate_batch = MagicMock()
        mock_embedding_gen.generate_async = AsyncMock()

        chunks = [
            {
                "text": "Chunk alpha",
                "text_hash": 1,
                "file_path": Path("/tmp/sample.pdf"),
                "page": 1,
                "metadata": {},
            },
            {
                "text": "Chunk beta",
                "text_hash": 2,
                "file_path": Path("/tmp/sample.pdf"),
                "page": 1,
                "metadata": {},
            },
            {
                "text": "Chunk gamma",
                "text_hash": 3,
                "file_path": Path("/tmp/sample.pdf"),
                "page": 2,
                "metadata": {},
            },
        ]

        mock_storage = MagicMock()
        mock_storage.store_chunks = AsyncMock(return_value={})

        ingestor = AsyncDocumentIngestor()

        with patch.object(asyncio, "to_thread", side_effect=_sentinel_to_thread):
            result = await ingestor._store_embedding_batch_async(
                file_path=Path("/tmp/sample.pdf"),
                chunks=chunks,
                embedding_gen=mock_embedding_gen,
                storage=mock_storage,
            )

        assert result == 3, f"Expected 3 chunks stored, got {result}"

        mock_embedding_gen.generate_batch_async.assert_called_once()
        received_texts = mock_embedding_gen.generate_batch_async.call_args[0][0]
        assert len(received_texts) == 3
        assert received_texts[0] == "Chunk alpha"
        assert received_texts[1] == "Chunk beta"
        assert received_texts[2] == "Chunk gamma"

        mock_embedding_gen.generate_batch.assert_not_called()

        assert not sentinel_errors, "\n".join(sentinel_errors)


class TestToThreadAntipatternWouldFail:
    """Confirm sentinel detects the CO_COROUTINE anti-pattern if introduced."""

    @pytest.mark.asyncio
    async def test_sentinel_fires_when_async_def_passed_to_to_thread(self) -> None:
        """Detector fires when async def is routed through to_thread instead of awaited."""
        sentinel_triggered = False

        async def _real_async_impl(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 384 for _ in texts]

        def _shim(func: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal sentinel_triggered
            if callable(func):
                code = getattr(func, "__code__", None)
                if code is not None and (code.co_flags & inspect.CO_COROUTINE):
                    sentinel_triggered = True
            import asyncio

            return asyncio.to_thread(func, *args, **kwargs)

        with patch.object(asyncio, "to_thread", side_effect=_shim):
            await asyncio.to_thread(_real_async_impl, ["x", "y", "z"])

        assert sentinel_triggered, (
            "Sentinel must fire when async def reaches to_thread. Detection regressed."
        )
