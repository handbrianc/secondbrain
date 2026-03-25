"""Unit tests for MCP search tool."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain_mcp.tools.search import handle_search


class TestSearchTool:
    """Tests for the search MCP tool."""

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        """Test search returns error when query is missing."""
        result = await handle_search({})
        assert "Error: query is required" in result

    @pytest.mark.asyncio
    async def test_search_with_valid_query(self):
        """Test search with valid query."""
        with patch("secondbrain.search.Searcher") as mock_searcher:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [
                {
                    "score": 0.9,
                    "source_file": "test.pdf",
                    "page_number": 1,
                    "chunk_text": "test content",
                },
            ]
            mock_searcher.return_value = mock_instance

            result = await handle_search({"query": "test query"})

            assert "Found 1 results" in result
            assert "test.pdf" in result

    @pytest.mark.asyncio
    async def test_search_with_top_k(self):
        """Test search with custom top_k."""
        with patch("secondbrain.search.Searcher") as mock_searcher:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            mock_searcher.return_value = mock_instance

            await handle_search({"query": "test", "top_k": 10})

            mock_instance.search.assert_called_once()
            call_args = mock_instance.search.call_args
            assert call_args[1]["top_k"] == 10

    @pytest.mark.asyncio
    async def test_search_with_min_score_filter(self):
        """Test search filters by min_score."""
        with patch("secondbrain.search.Searcher") as mock_searcher:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [
                {"score": 0.9},
                {"score": 0.5},
                {"score": 0.8},
            ]
            mock_searcher.return_value = mock_instance

            result = await handle_search({"query": "test", "min_score": 0.7})

            # Should only include results with score >= 0.7
            assert "Found 2 results" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """Test search with no results."""
        with patch("secondbrain.search.Searcher") as mock_searcher:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            mock_searcher.return_value = mock_instance

            result = await handle_search({"query": "test"})

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_search_handles_exceptions(self):
        """Test search handles exceptions gracefully."""
        with patch("secondbrain.search.Searcher") as mock_searcher:
            mock_searcher.side_effect = Exception("Test error")

            result = await handle_search({"query": "test"})

            assert "Error:" in result
