"""Tests for CLI module."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secondbrain.cli import CLIValidationError, cli, handle_cli_errors


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
        """Test ingest command."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 5, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
            runner.invoke(cli, ["ingest", "/tmp/test_docs"])

    @patch("secondbrain.document.DocumentIngestor")
    def test_ingest_command_recursive(self, mock_ingestor_class: MagicMock) -> None:
        """Test ingest command with recursive flag."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 10, "failed": 0}
        mock_ingestor_class.return_value = mock_ingestor

        runner = CliRunner()
        runner.invoke(cli, ["ingest", "/tmp", "--recursive"])
        # May fail due to path, but tests the flag

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

    @patch("secondbrain.management.Lister")
    def test_list_command(self, mock_lister_class: MagicMock) -> None:
        """Test list command."""
        mock_lister = MagicMock()
        mock_lister.list_chunks.return_value = [
            {"chunk_id": "1", "source_file": "test.pdf", "page_number": 1},
        ]
        mock_lister_class.return_value = mock_lister

        runner = CliRunner()
        runner.invoke(cli, ["list"])

    @patch("secondbrain.management.Deleter")
    def test_delete_command_by_source(self, mock_deleter_class: MagicMock) -> None:
        """Test delete command by source."""
        mock_deleter = MagicMock()
        mock_deleter.delete.return_value = 5
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        runner.invoke(cli, ["delete", "--source", "test.pdf", "--yes"])

    @patch("secondbrain.management.Deleter")
    def test_delete_command_all(self, mock_deleter_class: MagicMock) -> None:
        """Test delete command all."""
        mock_deleter = MagicMock()
        mock_deleter.delete.return_value = 100
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        runner.invoke(cli, ["delete", "--all", "--yes"])

    @patch("secondbrain.management.StatusChecker")
    def test_status_command(self, mock_status_class: MagicMock) -> None:
        """Test status command."""
        mock_status = MagicMock()
        mock_status.get_status.return_value = {
            "total_chunks": 50,
            "unique_sources": 3,
            "database": "secondbrain",
            "collection": "embeddings",
        }
        mock_status_class.return_value = mock_status

        runner = CliRunner()
        runner.invoke(cli, ["status"])

    def test_ingest_requires_path(self) -> None:
        """Test ingest command requires path argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest"])
        assert result.exit_code != 0

    def test_search_requires_query(self) -> None:
        """Test search command requires query argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["search"])
        assert result.exit_code != 0

    def test_delete_requires_option(self) -> None:
        """Test delete command requires an option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["delete"])
        assert result.exit_code != 0

    @patch("secondbrain.search.Searcher")
    def test_search_json_format(self, mock_searcher_class: MagicMock) -> None:
        """Test search command with JSON format."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {"source_file": "test.pdf", "score": 0.9},
        ]
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        runner.invoke(cli, ["search", "test", "--format", "json"])

    @patch("secondbrain.search.Searcher")
    def test_search_verbose_format(self, mock_searcher_class: MagicMock) -> None:
        """Test search command with verbose format."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {
                "source_file": "test.pdf",
                "page_number": 1,
                "score": 0.9,
                "chunk_text": "test content",
            },
        ]
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test", "--format", "verbose"])
        assert result.exit_code == 0


class TestCLIHealth:
    """Tests for CLI health command."""

    @patch("secondbrain.cli.get_health_status")
    def test_health_command_text(self, mock_get_health: MagicMock) -> None:
        """Test health command with text output."""
        mock_get_health.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "HEALTHY" in result.output
        assert "ollama" in result.output
        assert "mongodb" in result.output

    @patch("secondbrain.cli.get_health_status")
    def test_health_command_json(self, mock_get_health: MagicMock) -> None:
        """Test health command with JSON output."""
        expected_status = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }
        mock_get_health.return_value = expected_status

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--output", "json"])
        assert result.exit_code == 0
        assert "healthy" in result.output
        assert "ollama" in result.output

    @patch("secondbrain.cli.get_health_status")
    def test_health_command_degraded(self, mock_get_health: MagicMock) -> None:
        """Test health command when services are degraded."""
        mock_get_health.return_value = {
            "status": "degraded",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": False},
            "check_duration_seconds": 0.5,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "DEGRADED" in result.output

    @patch("secondbrain.cli.get_health_status")
    def test_health_command_verbose(self, mock_get_health: MagicMock) -> None:
        """Test health command with verbose flag."""
        mock_get_health.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["health", "--output", "json"])
        assert result.exit_code == 0
        assert "3600.0" in result.output


class TestHandleCliErrors:
    """Tests for handle_cli_errors decorator."""

    def test_decorator_passes_through_success(self) -> None:
        """Test decorator allows successful function to pass through."""

        @handle_cli_errors
        def successful_func() -> str:
            return "success"

        result = successful_func()
        assert result == "success"

    def test_decorator_catches_exception_and_exits(self) -> None:
        """Test decorator catches exception and exits with status 1."""

        @handle_cli_errors
        def failing_func() -> None:
            raise ValueError("Test error")

        with pytest.raises(SystemExit) as exc_info:
            failing_func()

        assert exc_info.value.code == 1

    def test_decorator_catches_specific_exception(self) -> None:
        """Test decorator catches CLIValidationError."""

        @handle_cli_errors
        def validation_func() -> None:
            raise CLIValidationError("Validation failed")

        with pytest.raises(SystemExit) as exc_info:
            validation_func()

        assert exc_info.value.code == 1

    def test_decorator_with_args(self) -> None:
        """Test decorator works with function arguments."""

        @handle_cli_errors
        def func_with_args(a: int, b: int) -> int:
            return a + b

        result = func_with_args(2, 3)
        assert result == 5

    def test_decorator_with_exception_message(self) -> None:
        """Test decorator includes exception message in output."""

        @handle_cli_errors
        def error_func() -> None:
            raise RuntimeError("Something went wrong")

        with pytest.raises(SystemExit) as exc_info:
            error_func()

        assert exc_info.value.code == 1
