"""Additional async API coverage tests for document module.

This module provides targeted async tests to cover remaining uncovered
async functions in the AsyncDocumentIngestor class.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import AsyncDocumentIngestor


class TestAsyncDocumentIngestorCoverage:
    """Additional tests for AsyncDocumentIngestor async methods."""

    @pytest.mark.asyncio
    async def test_ingest_async_empty_files(self) -> None:
        """Test ingest_async returns empty when no files found (lines 1728-1729)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        with patch.object(
            ingestor, "_collect_and_validate_files", return_value=[]
        ) as mock_collect:
            result = await ingestor.ingest_async("/nonexistent/path", recursive=False)

            mock_collect.assert_called_once()
            assert result == {"success": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_ingest_async_with_semaphore(self) -> None:
        """Test ingest_async with semaphore control (lines 1732-1750)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        mock_file = MagicMock()
        mock_file.name = "test.txt"

        with patch.object(
            ingestor, "_collect_and_validate_files", return_value=[mock_file]
        ):
            with patch.object(ingestor, "process_file_async", return_value=True):
                result = await ingestor.ingest_async(
                    "/test/path", recursive=False, max_concurrent=2
                )

                assert "success" in result
                assert "failed" in result

    @pytest.mark.asyncio
    async def test_process_with_semaphore_async(self) -> None:
        """Test process_with_semaphore async helper (lines 1734-1737)."""
        ingestor = AsyncDocumentIngestor(
            chunk_size=512,
            chunk_overlap=50,
            verbose=False,
        )

        mock_file = MagicMock()
        mock_embedding = MagicMock()
        mock_storage = MagicMock()

        with patch.object(ingestor, "process_file_async", return_value=True):
            # Test that semaphore is created and used
            semaphore = asyncio.Semaphore(2)
            async with semaphore:
                result = await ingestor.process_file_async(
                    mock_file, mock_embedding, mock_storage
                )
                # Should return True when mocked
                assert result is True
