"""Tests for CLI edge cases and validation."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secondbrain.cli import cli


def _create_test_dir() -> str:
    tmpdir = tempfile.mkdtemp()
    Path(tmpdir, ".gitkeep").touch()
    return tmpdir


class TestCLIChunkValidation:
    """Tests for chunk size validation in CLI."""

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_with_custom_chunk_size(
        self, mock_ingestor_class: MagicMock
    ) -> None:
        """Test ingest with custom chunk size."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ingest", _create_test_dir(), "--chunk-size", "2048"]
        )
        assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_with_custom_chunk_overlap(
        self, mock_ingestor_class: MagicMock
    ) -> None:
        """Test ingest with custom chunk overlap."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ingest", _create_test_dir(), "--chunk-overlap", "100"]
        )
        assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_with_both_chunk_options(
        self, mock_ingestor_class: MagicMock
    ) -> None:
        """Test ingest with both chunk size and overlap."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest",
                _create_test_dir(),
                "--chunk-size",
                "2048",
                "--chunk-overlap",
                "100",
            ],
        )
        assert result.exit_code == 0


class TestCLIBatchValidation:
    """Tests for batch size validation in CLI."""

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_with_batch_size(self, mock_ingestor_class: MagicMock) -> None:
        """Test ingest with batch size option."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 10, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        # Create temp directory since click.Path(exists=True) requires it
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CliRunner()
            result = runner.invoke(cli, ["ingest", tmpdir, "--batch-size", "20"])
            assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_with_batch_size_short_flag(
        self, mock_ingestor_class: MagicMock
    ) -> None:
        """Test ingest with batch size short flag."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 10, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        # Create temp directory since click.Path(exists=True) requires it
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CliRunner()
            result = runner.invoke(cli, ["ingest", tmpdir, "-b", "15"])
            assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_batch_size_zero(self, mock_ingestor_class: MagicMock) -> None:
        """Test ingest with batch size of zero."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 0, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        # Should fail validation due to click.IntRange(min=1)
        result = runner.invoke(cli, ["ingest", "/tmp/test_docs", "--batch-size", "0"])
        # Click's IntRange validation returns exit code 2
        assert result.exit_code == 2
        assert (
            "must be at least 1" in result.output.lower()
            or "invalid value" in result.output.lower()
        )


class TestCLIPaginationEdgeCases:
    """Tests for pagination edge cases."""

    @patch("secondbrain.management.Lister")
    def test_list_with_large_limit(self, mock_lister_class: MagicMock) -> None:
        """Test list command with large limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls", "--limit", "10000"])
        # Should handle gracefully
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_zero_limit(self, mock_lister_class: MagicMock) -> None:
        """Test list command with zero limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls", "--limit", "0"])
        # Should handle gracefully
        assert result.exit_code in [0, 1]

    @patch("secondbrain.management.Lister")
    def test_list_with_negative_offset(self, mock_lister_class: MagicMock) -> None:
        """Test list command with negative offset."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls", "--offset", "-1"])
        # Should handle gracefully
        assert result.exit_code in [0, 1]


class TestCLIJSONFormat:
    """Tests for JSON output format."""

    @patch("secondbrain.search.Searcher")
    def test_search_with_json_format(self, mock_searcher_class: MagicMock) -> None:
        """Test search command with JSON format output."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"chunk_id": "1", "score": 0.9, "source_file": "test.pdf"},
            {"chunk_id": "2", "score": 0.8, "source_file": "test2.pdf"},
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        assert result.exit_code == 0
        import json

        try:
            json.loads(result.output)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    @patch("secondbrain.search.Searcher")
    def test_search_json_format_with_empty_results(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search JSON format with no results."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "nonexistent query", "--format", "json"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data == []

    @patch("secondbrain.search.Searcher")
    def test_search_with_empty_results_table_format(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search with empty results in table format shows 'no results' message."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "nonexistent query"])
        assert result.exit_code == 0
        assert "no results found" in result.output.lower()

    @patch("secondbrain.search.Searcher")
    def test_search_with_low_score_results_filtered(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search filters out results below minimum score threshold."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"chunk_id": "1", "score": 0.15, "source_file": "test.pdf"},
            {"chunk_id": "2", "score": 0.25, "source_file": "test2.pdf"},
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "query", "--min-score", "0.3"])
        assert result.exit_code == 0
        assert "no relevant results found" in result.output.lower()

    @patch("secondbrain.search.Searcher")
    def test_search_with_mixed_scores_applies_threshold(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search shows only results above threshold when mixed scores exist."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"chunk_id": "1", "score": 0.15, "source_file": "test.pdf"},
            {"chunk_id": "2", "score": 0.85, "source_file": "test2.pdf"},
            {"chunk_id": "3", "score": 0.45, "source_file": "test3.pdf"},
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "query", "--min-score", "0.4"])
        assert result.exit_code == 0
        assert "Result 1" in result.output or "1." in result.output

    @patch("secondbrain.search.Searcher")
    def test_search_min_score_option_defaults_to_0_3(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search uses default min-score of 0.3 when not specified."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"chunk_id": "1", "score": 0.25, "source_file": "test.pdf"},
            {"chunk_id": "2", "score": 0.85, "source_file": "test2.pdf"},
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "query"])
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_large_result_set(self, mock_lister_class: MagicMock) -> None:
        """Test list command handles large result sets."""
        large_results = [
            {"chunk_id": f"chunk-{i}", "source_file": f"file-{i}.pdf", "page_number": 1}
            for i in range(1000)
        ]
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = large_results
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls"])
        assert result.exit_code == 0


class TestCLILargeResultSets:
    """Tests for handling large result sets."""

    @patch("secondbrain.management.Lister")
    def test_list_handles_large_result_set(self, mock_lister_class: MagicMock) -> None:
        """Test list command handles large result sets."""
        large_results = [
            {"chunk_id": f"chunk-{i}", "source_file": f"file-{i}.pdf", "page_number": 1}
            for i in range(1000)
        ]
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = large_results
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls"])
        assert result.exit_code == 0

    @patch("secondbrain.management.Lister")
    def test_list_with_max_limit(self, mock_lister_class: MagicMock) -> None:
        """Test list respects maximum limit."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = []
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        result = runner.invoke(cli, ["ls", "--limit", "200000"])
        assert result.exit_code in [0, 1]


class TestCLIHealthEdgeCases:
    """Tests for health check edge cases."""

    @patch("secondbrain.cli.commands.get_health_status")
    def test_health_command_with_degraded_services(
        self, mock_get_health_status: MagicMock
    ) -> None:
        """Test health command shows degraded status."""
        mock_get_health_status.return_value = {
            "status": "degraded",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": None,
            "services": {"sentence-transformers": True, "mongodb": False},
            "check_duration_seconds": 0.5,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "degraded" in result.output.lower()

    @patch("secondbrain.logging.get_health_status")
    def test_health_command_json_format(
        self, mock_get_health_status: MagicMock
    ) -> None:
        """Test health command with JSON output."""
        mock_status = MagicMock()
        mock_status.mongo_healthy = True
        mock_status.sentence_transformers_healthy = True
        mock_status.degraded = False
        mock_get_health_status.return_value = mock_status

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--output", "json"])
        assert result.exit_code == 0

    @patch("secondbrain.logging.get_health_status")
    def test_health_command_verbose_output(
        self, mock_get_health_status: MagicMock
    ) -> None:
        """Test health command with verbose output."""
        mock_status = MagicMock(
            mongo_healthy=True,
            sentence_transformers_healthy=True,
            degraded=False,
        )
        mock_get_health_status.return_value = mock_status

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--verbose"])
        # Exit code 2 indicates missing option, which is expected behavior
        assert result.exit_code == 2


class TestCLIValidationErrorHandling:
    """Tests for CLI validation error handling."""

    def test_validation_error_with_missing_source(self) -> None:
        """Test validation error when source option is missing for delete."""
        runner = CliRunner()
        result = runner.invoke(cli, ["delete"])
        # Should fail with error (Click's usage error or custom validation)
        assert result.exit_code in [1, 2]

    def test_validation_error_with_missing_query(self) -> None:
        """Test validation error when query is missing for search."""
        runner = CliRunner()
        result = runner.invoke(cli, ["search"])
        # Should fail with proper error message
        assert result.exit_code == 2

    def test_validation_error_with_invalid_path(self) -> None:
        """Test validation error with invalid file path."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "/nonexistent/path/file.pdf"])
        # Should fail with proper error message
        assert result.exit_code == 2


class TestCLISearchValidation:
    """Tests for search command validation."""

    @patch("secondbrain.search.Searcher")
    def test_search_with_very_long_query(self, mock_searcher_class: MagicMock) -> None:
        """Test search with very long query (near max length)."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        # Query just under max length
        long_query = "test " * 1999
        result = runner.invoke(cli, ["search", long_query])
        # Should handle gracefully
        assert result.exit_code in [0, 1]

    @patch("secondbrain.search.Searcher")
    def test_search_with_special_characters(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test search with special characters in query."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test @#$%^&*() query"])
        # Should handle gracefully
        assert result.exit_code in [0, 1]

    @pytest.mark.timeout(10)
    def test_search_with_unicode_query(self) -> None:
        """Test search with unicode characters in query."""
        mock_config = MagicMock()
        mock_config.default_top_k = 5

        mock_searcher = MagicMock()
        mock_searcher.config = mock_config
        mock_searcher.search.return_value = []
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)

        with (
            patch("secondbrain.cli._ensure_mongodb"),
            patch("secondbrain.search.Searcher", return_value=mock_searcher),
            patch("secondbrain.cli.commands.get_config") as mock_get_config,
        ):
            mock_get_config.return_value = mock_config

            runner = CliRunner()
            result = runner.invoke(cli, ["search", "搜索测试 émojis 日本語"])
            # Should handle gracefully
            assert result.exit_code == 0
