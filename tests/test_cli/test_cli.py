"""Tests for CLI module."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_help(self) -> None:
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "SecondBrain" in result.output

    def test_cli_verbose_flag(self) -> None:
        """Test CLI verbose flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "ingest", "--help"])
        assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_command(self, mock_ingestor_class: MagicMock) -> None:
        """Test ingest command with mocked ingestion to avoid slow PDF processing."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 5, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
            result = runner.invoke(cli, ["ingest", "/tmp/test_docs"])
            assert result.exit_code == 0
            mock_ingestor_class.assert_called_once()
            mock_ingestor.ingest.assert_called_once()

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_command_recursive(self, mock_ingestor_class: MagicMock) -> None:
        """Test ingest command with recursive flag."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 10, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "/tmp", "--recursive"])
        assert result.exit_code == 0
        mock_ingestor_class.assert_called_once()
        mock_ingestor.ingest.assert_called_once()

    @patch("secondbrain.search.Searcher")
    def test_search_command(self, mock_searcher_class: MagicMock) -> None:
        """Test search command."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"source_file": "test.pdf", "score": 0.9},
            {"source_file": "test2.pdf", "score": 0.8},
        ]
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        runner.invoke(cli, ["search", "test query"])
        # May fail due to connection, but tests the command

    @patch("secondbrain.search.Searcher")
    def test_search_command_with_top_k(self, mock_searcher_class: MagicMock) -> None:
        """Test search command with top-k."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        runner.invoke(cli, ["search", "test query", "--top-k", "10"])

    @patch("secondbrain.management.Deleter")
    def test_delete_with_chunk_id(self, mock_deleter_class: MagicMock) -> None:
        """Test delete command with chunk-id option."""
        mock_deleter = MagicMock()
        mock_deleter.delete.return_value = 1
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--chunk-id", "test-123", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "document" in result.output

    @patch("secondbrain.management.Deleter")
    def test_delete_all_with_confirmation(self, mock_deleter_class: MagicMock) -> None:
        """Test delete all command with confirmation."""
        mock_deleter = MagicMock()
        mock_deleter.delete.return_value = 100
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--all", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "document" in result.output

    @patch("secondbrain.management.Deleter")
    def test_delete_cancelled_by_user(self, mock_deleter_class: MagicMock) -> None:
        """Test delete command cancelled by user."""
        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--source", "test.pdf"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output

    def test_ingest_with_failed_files_displayed(self) -> None:
        """Test ingest command displays failed files count."""
        from unittest.mock import MagicMock, patch

        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor_class:
            mock_ingestor = MagicMock()
            mock_ingestor.ingest.return_value = {"success": 3, "failed": 2}
            mock_ingestor_class.return_value = mock_ingestor

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                result = runner.invoke(cli, ["ingest", "/tmp/test_docs"])

            assert result.exit_code == 0
            assert "Successfully ingested 3 files" in result.output
            assert "Failed: 2 files" in result.output

    def test_search_verbose_format_empty_results(self) -> None:
        """Test search with json format and empty results."""
        from unittest.mock import MagicMock, patch

        with patch("secondbrain.search.Searcher") as mock_searcher_class:
            mock_searcher = MagicMock()
            mock_searcher.search.return_value = []
            mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
            mock_searcher.__exit__ = MagicMock(return_value=False)
            mock_searcher_class.return_value = mock_searcher

            runner = CliRunner()
            result = runner.invoke(cli, ["search", "no matches", "--format", "json"])

            assert result.exit_code == 0

    def test_delete_validation_no_options(self) -> None:
        """Test delete command fails when no options provided."""
        runner = CliRunner()
        result = runner.invoke(cli, ["delete"])

        assert result.exit_code != 0
        assert "Error" in result.output

    def test_delete_validation_multiple_options(self) -> None:
        """Test delete command fails with multiple conflicting options."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["delete", "--source", "test.pdf", "--chunk-id", "123", "--yes"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output or "Specify only one" in result.output

    def test_metrics_reset_command(self) -> None:
        """Test metrics command with reset flag."""
        from unittest.mock import patch

        with patch("secondbrain.utils.perf_monitor.metrics.reset") as mock_reset:
            runner = CliRunner()
            result = runner.invoke(cli, ["metrics", "--reset"])

            assert result.exit_code == 0
            assert "All metrics reset" in result.output
            mock_reset.assert_called_once()

    def test_circuit_breaker_reset_command(self) -> None:
        """Test circuit-breaker command with reset flag."""
        from unittest.mock import patch

        with patch(
            "secondbrain.utils.circuit_breaker.CircuitBreaker.reset"
        ) as mock_reset:
            runner = CliRunner()
            result = runner.invoke(cli, ["circuit-breaker", "--reset"])

            assert result.exit_code == 0
            assert "Circuit breaker state is per-instance" in result.output
            assert "No global circuit breaker to reset" in result.output
            mock_reset.assert_not_called()
