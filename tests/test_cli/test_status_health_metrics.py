"""Tests for status, health, and metrics CLI commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli


class TestStatusHealthMetrics:
    """Tests for status, health, and metrics commands."""

    def test_status_display(self) -> None:
        """Test status command output formatting.

        Verifies that document count and chunk count are displayed correctly
        using Rich table formatting.
        """
        runner = CliRunner()

        with patch("secondbrain.management.StatusChecker") as mock_checker_class:
            mock_checker = MagicMock()
            mock_checker.get_status.return_value = {
                "total_chunks": 150,
                "unique_sources": 12,
                "database": "secondbrain",
                "collection": "chunks",
            }
            mock_checker_class.return_value.__enter__ = MagicMock(
                return_value=mock_checker
            )
            mock_checker_class.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(cli, ["status"])

            assert result.exit_code == 0
            assert "Database Status" in result.output
            assert "Total chunks: 150" in result.output
            assert "Unique sources: 12" in result.output
            assert "Database: secondbrain" in result.output
            assert "Collection: chunks" in result.output

    def test_health_json_output(self) -> None:
        """Test --format json for health check.

        Verifies JSON structure with service statuses and MongoDB
        and embedding service health indicators.
        """
        runner = CliRunner()

        with patch("secondbrain.cli.commands.get_health_status") as mock_health:
            mock_health.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00+00:00",
                "uptime": None,
                "services": {
                    "mongodb": True,
                    "embedding": True,
                },
                "check_duration_seconds": 0.123,
            }

            result = runner.invoke(cli, ["health", "--output", "json"])

            assert result.exit_code == 0
            output = json.loads(result.output)

            assert output["status"] == "healthy"
            assert output["timestamp"] == "2024-01-15T10:30:00+00:00"
            assert output["services"]["mongodb"] is True
            assert output["services"]["embedding"] is True
            assert "check_duration_seconds" in output

    def test_metrics_reset(self) -> None:
        """Test metrics reset functionality.

        Verifies that counters are cleared when --reset flag is used.
        """
        runner = CliRunner()

        with patch("secondbrain.utils.perf_monitor.metrics.reset") as mock_reset:
            result = runner.invoke(cli, ["metrics", "--reset"])

            assert result.exit_code == 0
            assert "All metrics reset" in result.output
            mock_reset.assert_called_once()

    def test_metrics_no_data(self) -> None:
        """Test metrics display with no collected data.

        Verifies graceful handling when no metrics have been collected.
        """
        runner = CliRunner()

        with (
            patch("secondbrain.cli._ensure_mongodb"),
            patch("secondbrain.utils.perf_monitor.metrics.get_stats") as mock_get_stats,
        ):
            # Return None for all metric queries (no data collected)
            mock_get_stats.return_value = None

            result = runner.invoke(cli, ["metrics"])

            assert result.exit_code == 0
            assert "No metrics collected yet" in result.output
            assert "Run some operations first" in result.output
