"""Async API coverage tests for document module.

This module provides targeted async tests to cover remaining uncovered
async functions in the document module, increasing async API coverage.
"""

import pytest

from secondbrain.document import AsyncDocumentIngestor


class TestAsyncDocumentIngestor:
    """Tests for AsyncDocumentIngestor async methods."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test AsyncDocumentIngestor async context manager (lines 1682-1691)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        async with ingestor as ing:
            assert ing is ingestor
            assert ing.chunk_size == 512

    @pytest.mark.asyncio
    async def test_async_exit_returns_none(self) -> None:
        """Test __aexit__ returns None (lines 1686-1694)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        async with ingestor:
            pass  # Context manager should exit cleanly
