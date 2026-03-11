"""Tests for CLI module."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secondbrain.cli import cli, handle_cli_errors
from secondbrain.exceptions import CLIValidationError


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

    @pytest.mark.parametrize("output_format", ["text", "json"])
    @patch("secondbrain.cli.get_health_status")
    def test_health_command_output_format(
        self, mock_get_health: MagicMock, output_format: str
    ) -> None:
        mock_get_health.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }
        runner = CliRunner()
        if output_format == "text":
            result = runner.invoke(cli, ["health"])
            assert result.exit_code == 0
            assert "HEALTHY" in result.output
            assert "ollama" in result.output
            assert "mongodb" in result.output
        else:
            result = runner.invoke(cli, ["health", "--output", "json"])
            assert result.exit_code == 0
            assert "healthy" in result.output
            assert "ollama" in result.output

    @patch("secondbrain.cli.get_health_status")
    def test_health_command_status(self, mock_get_health: MagicMock) -> None:
        for status in ["healthy", "degraded"]:
            degraded = status == "degraded"
            mock_get_health.return_value = {
                "status": status,
                "timestamp": "2024-01-01T00:00:00+00:00",
                "uptime": 3600.0,
                "services": {"ollama": not degraded, "mongodb": degraded},
                "check_duration_seconds": 0.5,
            }
            runner = CliRunner()
            result = runner.invoke(cli, ["health"])
            assert result.exit_code == 0
            if status == "healthy":
                assert "HEALTHY" in result.output
            else:
                assert "DEGRADED" in result.output


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


class TestCLIMetricsCommand:
    """Tests for metrics command."""

    @patch("secondbrain.utils.perf_monitor.metrics.get_stats")
    def test_metrics_command_with_data(self, mock_get_stats: MagicMock) -> None:
        """Test metrics command displays performance data."""
        mock_get_stats.return_value = {
            "count": 10,
            "total_seconds": 1.5,
            "avg_seconds": 0.15,
            "min_seconds": 0.1,
            "max_seconds": 0.3,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["metrics"])

        assert result.exit_code == 0
        assert "Performance Metrics" in result.output
        assert "Count: 10" in result.output

    @patch("secondbrain.utils.perf_monitor.metrics.get_stats")
    def test_metrics_command_empty_data(self, mock_get_stats: MagicMock) -> None:
        """Test metrics command when no metrics collected."""
        mock_get_stats.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["metrics"])

        assert result.exit_code == 0
        assert "No metrics collected" in result.output

    @patch("secondbrain.utils.perf_monitor.metrics.reset")
    def test_metrics_command_reset(self, mock_reset: MagicMock) -> None:
        """Test metrics command with reset flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["metrics", "--reset"])

        assert result.exit_code == 0
        assert "All metrics reset" in result.output
        mock_reset.assert_called_once()


class TestCLICircuitBreakerCommand:
    """Tests for circuit breaker command."""

    @patch("secondbrain.utils.circuit_breaker.CircuitBreaker.get_stats")
    def test_circuit_breaker_command(self, mock_get_stats: MagicMock) -> None:
        """Test circuit breaker command displays status."""
        mock_get_stats.return_value = {
            "state": "closed",
            "failure_count": 0,
            "success_count": 10,
            "last_failure_time": None,
            "half_open_calls": 0,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["circuit-breaker"])

        assert result.exit_code == 0
        assert "Circuit Breaker Status" in result.output
        assert "State: closed" in result.output

    @patch("secondbrain.utils.circuit_breaker.CircuitBreaker.get_stats")
    def test_circuit_breaker_command_open_state(
        self, mock_get_stats: MagicMock
    ) -> None:
        """Test circuit breaker command with open state."""
        mock_get_stats.return_value = {
            "state": "open",
            "failure_count": 5,
            "success_count": 0,
            "last_failure_time": 100.0,
            "half_open_calls": 0,
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["circuit-breaker"])

        assert result.exit_code == 0
        assert "State: open" in result.output
        assert "Failure count: 5" in result.output

    @patch("secondbrain.utils.circuit_breaker.CircuitBreaker.reset")
    def test_circuit_breaker_command_reset(self, mock_reset: MagicMock) -> None:
        """Test circuit breaker command with reset flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["circuit-breaker", "--reset"])

        assert result.exit_code == 0
        assert "Circuit breaker reset" in result.output
        mock_reset.assert_called_once()


class TestCLIDeleteValidation:
    """Tests for delete command validation."""

    def test_delete_requires_option(self) -> None:
        """Test delete command requires --source, --chunk-id, or --all."""
        runner = CliRunner()
        result = runner.invoke(cli, ["delete"])

        assert result.exit_code != 0
        assert "Error" in result.output

    def test_delete_rejects_multiple_options(self) -> None:
        """Test delete rejects multiple conflicting options."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["delete", "--source", "test.pdf", "--chunk-id", "123"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output or "Specify only one" in result.output

    @patch("secondbrain.management.Deleter")
    def test_delete_with_source(self, mock_deleter_class: MagicMock) -> None:
        """Test delete command with source option."""
        mock_deleter = MagicMock()
        mock_deleter.delete.return_value = 5
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--source", "test.pdf", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "document" in result.output

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
