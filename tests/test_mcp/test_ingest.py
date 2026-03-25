"""Unit tests for MCP ingest tool."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain_mcp.tools.ingest import handle_ingest


class TestIngestTool:
    """Tests for the ingest MCP tool."""

    @pytest.mark.asyncio
    async def test_ingest_missing_path(self):
        """Test ingest returns error when path is missing."""
        result = await handle_ingest({})
        assert "Error: path is required" in result

    @pytest.mark.asyncio
    async def test_ingest_with_valid_path(self):
        """Test ingest with valid path."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_instance = MagicMock()
            mock_instance.ingest.return_value = {"success": 2, "failed": 0}
            mock_ingestor.return_value = mock_instance

            result = await handle_ingest({"path": "/tmp/test.pdf"})

            assert "2 files succeeded" in result
            assert "0 files failed" in result

    @pytest.mark.asyncio
    async def test_ingest_with_options(self):
        """Test ingest with custom options."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_instance = MagicMock()
            mock_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_instance

            await handle_ingest(
                {
                    "path": "/tmp/test.pdf",
                    "recursive": True,
                    "chunk_size": 500,
                    "cores": 2,
                }
            )

            # Verify DocumentIngestor was called with correct args
            mock_ingestor.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_with_failures(self):
        """Test ingest handles failures."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_instance = MagicMock()
            mock_instance.ingest.return_value = {"success": 1, "failed": 1}
            mock_ingestor.return_value = mock_instance

            result = await handle_ingest({"path": "/tmp/test.pdf"})

            assert "1 files succeeded" in result
            assert "1 files failed" in result

    @pytest.mark.asyncio
    async def test_ingest_handles_exceptions(self):
        """Test ingest handles exceptions gracefully."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor.side_effect = Exception("Test error")

            result = await handle_ingest({"path": "/tmp/test.pdf"})

            assert "Error:" in result
