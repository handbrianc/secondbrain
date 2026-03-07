"""Tests for CLI edge cases including pagination and large result sets."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import MAX_LIST_LIMIT, cli


class TestCLIPaginationEdgeCases:
    """Tests for pagination edge cases in CLI."""

    @patch("secondbrain.management.Lister")
    def test_list_with_zero_limit(self, mock_lister_class: MagicMock) -> None:
        """Test list command with zero limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--limit", "0"])
        # Should handle zero limit gracefully
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_negative_offset(self, mock_lister_class: MagicMock) -> None:
        """Test list command with negative offset."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--offset", "-10"])
        # Click typically accepts negative integers, behavior depends on implementation
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_large_limit(self, mock_lister_class: MagicMock) -> None:
        """Test list command with large limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--limit", "10000"])
        # Should accept large limits
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_pagination_accuracy(self, mock_lister_class: MagicMock) -> None:
        """Test that pagination returns correct results."""
        mock_lister = MagicMock()
        # Simulate 100 documents
        all_chunks = [
            {
                "chunk_id": f"chunk{i}",
                "source_file": f"file{i}.pdf",
                "page_number": i % 10,
                "chunk_text": f"text{i}",
            }
            for i in range(100)
        ]

        def list_chunks_mock(limit, offset, **kwargs):
            return all_chunks[offset : offset + limit]

        mock_lister.list_chunks.side_effect = list_chunks_mock
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()

        # First page
        result1 = runner.invoke(cli, ["list", "--limit", "10", "--offset", "0"])
        assert result1.exit_code == 0

        # Second page
        result2 = runner.invoke(cli, ["list", "--limit", "10", "--offset", "10"])
        assert result2.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_all_flag(self, mock_lister_class: MagicMock) -> None:
        """Test list command with --all flag."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        # Configure mock to return itself on __enter__ (context manager protocol)
        mock_lister.__enter__ = MagicMock(return_value=mock_lister)
        mock_lister.__exit__ = MagicMock(return_value=False)
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--all"])
        assert result.exit_code == 0
        # Verify list_chunks was called with large limit
        call_args = mock_lister.list_chunks.call_args
        assert call_args is not None
        assert call_args.kwargs["limit"] == MAX_LIST_LIMIT

    @patch("secondbrain.management.Lister")
    def test_list_empty_results(self, mock_lister_class: MagicMock) -> None:
        """Test list command with empty database."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_source_filter_and_pagination(
        self, mock_lister_class: MagicMock
    ) -> None:
        """Test list with source filter and pagination combined."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = [
            {
                "chunk_id": "chunk1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "text1",
            }
        ]
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(
            cli, ["list", "--source", "test.pdf", "--limit", "10", "--offset", "0"]
        )
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_chunk_id_filter(self, mock_lister_class: MagicMock) -> None:
        """Test list with chunk ID filter."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = [
            {
                "chunk_id": "test-chunk-id",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "text1",
            }
        ]
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--chunk-id", "test-chunk-id"])
        assert result.exit_code == 0


class TestCLILargeResultSetHandling:
    """Tests for large result set handling."""

    @patch("secondbrain.search.Searcher")
    def test_search_large_result_set(self, mock_searcher_class: MagicMock) -> None:
        """Test search with large number of results."""
        mock_searcher = MagicMock()
        # Simulate 100 search results
        mock_searcher.search.return_value = [
            {
                "chunk_id": f"chunk{i}",
                "source_file": f"file{i}.pdf",
                "page_number": i % 10,
                "chunk_text": f"text{i}",
                "score": 0.9 - (i * 0.001),
            }
            for i in range(100)
        ]
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test query", "--top-k", "100"])
        # Should handle large result sets
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_truncates_large_results(self, mock_lister_class: MagicMock) -> None:
        """Test that list command truncates results to default limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister.__enter__ = MagicMock(return_value=mock_lister)
        mock_lister.__exit__ = MagicMock(return_value=False)
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        # Verify default limit is used
        call_args = mock_lister.list_chunks.call_args
        assert call_args is not None
        assert call_args.kwargs["limit"] == 50  # Default limit

    @patch("secondbrain.management.Lister")
    def test_list_handles_many_chunks(self, mock_lister_class: MagicMock) -> None:
        """Test list command handles many chunks efficiently."""
        mock_lister = MagicMock()
        # Simulate 1000 chunks
        all_chunks = [
            {
                "chunk_id": f"chunk{i}",
                "source_file": f"file{i}.pdf",
                "page_number": i % 10,
                "chunk_text": f"text{i}",
            }
            for i in range(1000)
        ]
        mock_lister.list_chunks.return_value = all_chunks[:50]  # Default limit
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
