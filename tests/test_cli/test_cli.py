"""Tests for CLI module."""

import logging
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
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
        # The CLI drives Deleter as a context manager; without this the
        # ``with`` block binds ``__enter__()``'s child mock and the delete
        # return value configured below is never seen.
        mock_deleter.__enter__ = MagicMock(return_value=mock_deleter)
        mock_deleter.delete.return_value = 1
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--chunk-id", "test-123", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "chunk(s)" in result.output

    @patch("secondbrain.management.Deleter")
    def test_delete_all_with_confirmation(self, mock_deleter_class: MagicMock) -> None:
        """Test delete all command with confirmation."""
        mock_deleter = MagicMock()
        # Context-manager wiring as in test_delete_with_chunk_id above.
        mock_deleter.__enter__ = MagicMock(return_value=mock_deleter)
        mock_deleter.delete.return_value = 100
        mock_deleter_class.return_value = mock_deleter

        runner = CliRunner()
        result = runner.invoke(cli, ["delete", "--all", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert "chunk(s)" in result.output

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


class TestCLILoggingWiring:
    """Test the CLI --verbose flag wiring into logging levels.

    Spec (structured-logging, Integration with CLI): --verbose SHALL set the
    log level to DEBUG; a default run keeps the WARNING default. The group
    callback runs setup_logging before any subcommand, so --help on a
    subcommand exercises the wiring.

    SECONDBRAIN_LOG_LEVEL is pinned to WARNING because the CLI honors that
    env var and config() loads .env.test (SECONDBRAIN_LOG_LEVEL=DEBUG) in the
    test environment; production default (no env override) is WARNING, which
    the direct setup_logging tests cover.
    """

    @pytest.fixture(autouse=True)
    def _restore_root_logging(self) -> Iterator[None]:
        """Restore root handlers (with their levels) and the root level."""
        root_logger = logging.getLogger()
        handlers = list(root_logger.handlers)
        handler_levels = [(handler, handler.level) for handler in handlers]
        root_level = root_logger.level
        yield
        root_logger.handlers = handlers
        for handler, level in handler_levels:
            handler.setLevel(level)
        root_logger.setLevel(root_level)

    def test_verbose_flag_sets_debug_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--verbose wires the effective level to DEBUG."""
        monkeypatch.setenv("SECONDBRAIN_LOG_LEVEL", "WARNING")
        runner = CliRunner()

        result = runner.invoke(cli, ["--verbose", "ingest", "--help"])

        assert result.exit_code == 0
        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    def test_default_run_keeps_warning_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run without --verbose keeps the WARNING default."""
        monkeypatch.setenv("SECONDBRAIN_LOG_LEVEL", "WARNING")
        runner = CliRunner()

        result = runner.invoke(cli, ["ingest", "--help"])

        assert result.exit_code == 0
        assert logging.getLogger().getEffectiveLevel() == logging.WARNING

    def test_level_toggles_back_after_verbose_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A later default run downgrades the level again (reconfiguration)."""
        monkeypatch.setenv("SECONDBRAIN_LOG_LEVEL", "WARNING")
        runner = CliRunner()

        verbose_result = runner.invoke(cli, ["--verbose", "ingest", "--help"])
        assert verbose_result.exit_code == 0
        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

        default_result = runner.invoke(cli, ["ingest", "--help"])
        assert default_result.exit_code == 0
        assert logging.getLogger().getEffectiveLevel() == logging.WARNING
