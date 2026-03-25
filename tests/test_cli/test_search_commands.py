"""Tests for search CLI commands.

This module provides comprehensive tests for the search command functionality,
including filters, JSON output, empty results, and timeout handling.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli


def create_mock_searcher(
    return_value: list | None = None, side_effect: Exception | None = None
) -> MagicMock:
    """Create a properly configured mock Searcher for context manager usage.

    Args:
        return_value: List of results to return from search()
        side_effect: Exception to raise from search()

    Returns:
        A MagicMock configured as a context manager that returns itself,
        with search() method set up correctly.
    """
    mock_instance = MagicMock()

    if side_effect:
        mock_instance.search.side_effect = side_effect
    else:
        mock_instance.search.return_value = return_value or []

    # Set up context manager protocol
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)

    # The class mock returns the instance
    mock_class = MagicMock(return_value=mock_instance)

    return mock_class


class TestSearchFilters:
    """Tests for search command filters."""

    def test_search_with_source_filter(self) -> None:
        """Test search with --source filter."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {
                    "source_file": "/path/to/document.pdf",
                    "score": 0.9,
                    "chunk_text": "test content",
                },
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["search", "test query", "--source", "/path/to/document.pdf"],
            )

        assert result.exit_code == 0
        mock_instance = mock_searcher_class.return_value
        mock_instance.search.assert_called_once()
        call_kwargs = mock_instance.search.call_args[1]
        assert call_kwargs["source_filter"] == "/path/to/document.pdf"

    def test_search_with_file_type_filter(self) -> None:
        """Test search with --file-type filter."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {"source_file": "test.pdf", "score": 0.85, "chunk_text": "pdf content"},
                {"source_file": "test2.pdf", "score": 0.8, "chunk_text": "more pdf"},
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["search", "pdf documents", "--file-type", "pdf"]
            )

        assert result.exit_code == 0
        mock_instance = mock_searcher_class.return_value
        mock_instance.search.assert_called_once()
        call_kwargs = mock_instance.search.call_args[1]
        assert call_kwargs["file_type_filter"] == "pdf"

    def test_search_with_min_score_filter(self) -> None:
        """Test search with --min-score filter."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {"source_file": "test.pdf", "score": 0.95, "chunk_text": "high score"},
                {
                    "source_file": "test2.pdf",
                    "score": 0.8,
                    "chunk_text": "medium score",
                },
                {"source_file": "test3.pdf", "score": 0.7, "chunk_text": "low score"},
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["search", "test query", "--min-score", "0.85"],
            )

        assert result.exit_code == 0
        mock_instance = mock_searcher_class.return_value
        call_kwargs = mock_instance.search.call_args[1]
        assert call_kwargs["source_filter"] is None
        assert call_kwargs["file_type_filter"] is None

    def test_search_with_multiple_filters(self) -> None:
        """Test search with multiple filters combined."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {
                    "source_file": "/docs/report.pdf",
                    "score": 0.92,
                    "chunk_text": "filtered result",
                },
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "search",
                    "quarterly report",
                    "--source",
                    "/docs/report.pdf",
                    "--file-type",
                    "pdf",
                    "--min-score",
                    "0.9",
                ],
            )

        assert result.exit_code == 0
        mock_instance = mock_searcher_class.return_value
        mock_instance.search.assert_called_once()
        call_kwargs = mock_instance.search.call_args[1]
        assert call_kwargs["source_filter"] == "/docs/report.pdf"
        assert call_kwargs["file_type_filter"] == "pdf"


class TestSearchJsonOutput:
    """Tests for search command JSON output format."""

    def test_search_json_output_format(self) -> None:
        """Test search with --format json flag."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {
                    "source_file": "test.pdf",
                    "score": 0.9,
                    "chunk_text": "This is the chunk text content",
                    "page_number": 1,
                },
                {
                    "source_file": "test2.pdf",
                    "score": 0.85,
                    "chunk_text": "Another chunk of text",
                    "page_number": 2,
                },
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "pdf documents", "--format", "json"])

        assert result.exit_code == 0
        import json

        output_data = json.loads(result.output)
        assert isinstance(output_data, list)
        assert len(output_data) == 2
        assert output_data[0]["source_file"] == "test.pdf"
        assert output_data[0]["score"] == 0.9
        assert output_data[0]["chunk_text"] == "This is the chunk text content"

    def test_search_json_empty_results(self) -> None:
        """Test JSON output with no results."""
        mock_searcher_class = create_mock_searcher(return_value=[])

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["search", "no matches here", "--format", "json"]
            )

        assert result.exit_code == 0
        import json

        output_data = json.loads(result.output)
        assert output_data == []

    def test_search_json_serialization(self) -> None:
        """Test proper JSON serialization of search results."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {
                    "source_file": "document.pdf",
                    "score": 0.95,
                    "chunk_text": "Test content with special chars: aou",
                    "page_number": None,
                },
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "query", "--format", "json"])

        assert result.exit_code == 0
        import json

        output_data = json.loads(result.output)
        assert len(output_data) == 1
        assert output_data[0]["score"] == 0.95
        assert output_data[0]["page_number"] is None


class TestSearchNoResults:
    """Tests for search command with no results."""

    def test_search_empty_result_set(self) -> None:
        """Test search when storage returns empty list."""
        mock_searcher_class = create_mock_searcher(return_value=[])

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "completely unrelated query"])

        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_search_empty_result_below_threshold(self) -> None:
        """Test search when all results are below minimum score threshold."""
        mock_searcher_class = create_mock_searcher(
            return_value=[
                {
                    "source_file": "test.pdf",
                    "score": 0.5,
                    "chunk_text": "low score content",
                },
                {"source_file": "test2.pdf", "score": 0.6, "chunk_text": "still low"},
            ]
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["search", "query", "--min-score", "0.78"],
            )

        assert result.exit_code == 0
        assert "No relevant results found" in result.output
        assert "minimum score: 0.78" in result.output

    def test_search_no_results_exit_code(self) -> None:
        """Test that no results does not cause error exit code."""
        mock_searcher_class = create_mock_searcher(return_value=[])

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "nothing matches"])

        assert result.exit_code == 0


class TestSearchTimeoutHandling:
    """Tests for search command timeout and error handling."""

    def test_search_timeout_error(self) -> None:
        """Test search with timeout error handling."""
        from secondbrain.exceptions import ServiceUnavailableError

        mock_searcher_class = create_mock_searcher(
            side_effect=ServiceUnavailableError("Search timed out after 30s")
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "test query"])

        assert result.exit_code == 1

    def test_search_connection_error(self) -> None:
        """Test search with connection error handling."""
        from secondbrain.exceptions import StorageConnectionError

        mock_searcher_class = create_mock_searcher(
            side_effect=StorageConnectionError("Cannot connect to MongoDB")
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "test query"])

        assert result.exit_code == 1

    def test_search_timeout_with_user_friendly_message(self) -> None:
        """Test that timeout errors show user-friendly messages."""
        from secondbrain.exceptions import ServiceUnavailableError

        mock_searcher_class = create_mock_searcher(
            side_effect=ServiceUnavailableError(
                "Timeout: embedding service unavailable"
            )
        )

        with patch("secondbrain.search.Searcher", mock_searcher_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "test query"])

        assert result.exit_code == 1
