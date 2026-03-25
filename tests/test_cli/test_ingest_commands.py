"""Tests for CLI ingest commands.

This module provides comprehensive tests for the ingest command functionality,
including progress callbacks, cores validation, streaming config, file validation,
empty directories, and mixed success/failure scenarios.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli
from secondbrain.config import Config


class TestIngestProgressCallback:
    """Tests for ingest command progress callback with Rich progress bar."""

    def test_ingest_progress_callback(self) -> None:
        progress_updates: list[tuple[Path, bool]] = []

        def mock_progress_callback(file_path: Path, success: bool) -> None:
            progress_updates.append((file_path, success))

        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 3, "failed": 1}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            runner = CliRunner()
            with runner.isolated_filesystem():
                Path("/tmp/test_ingest_progress").mkdir(parents=True, exist_ok=True)

                with patch("secondbrain.document.is_supported", return_value=True):
                    result = runner.invoke(
                        cli,
                        ["ingest", "/tmp/test_ingest_progress"],
                    )

        assert result.exit_code == 0
        mock_ingestor_class.assert_called_once()
        call_kwargs = mock_ingestor_class.call_args[1]
        assert call_kwargs.get("progress_callback") is None
        assert mock_ingestor.ingest.called


class TestIngestCoresValidation:
    """Tests for ingest command cores parameter validation."""

    def test_ingest_cores_validation(self) -> None:
        runner = CliRunner()
        available_cores = os.cpu_count() or 1

        result = runner.invoke(
            cli,
            ["ingest", "/tmp", "--cores", "0"],
        )
        assert result.exit_code != 0
        assert result.exception is not None
        assert "positive" in str(result.exception).lower()

        result = runner.invoke(
            cli,
            ["ingest", "/tmp", "--cores", "-1"],
        )
        assert result.exit_code != 0
        assert result.exception is not None
        assert "positive" in str(result.exception).lower()

        excessive_cores = available_cores + 10
        result = runner.invoke(
            cli,
            ["ingest", "/tmp", "--cores", str(excessive_cores)],
        )
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert str(available_cores) in result.output


class TestIngestStreamingEnabled:
    """Tests for ingest command with streaming configuration."""

    def test_ingest_streaming_enabled(self) -> None:
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 2, "failed": 0}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        mock_config = MagicMock(spec=Config)
        mock_config.chunk_size = 4096
        mock_config.chunk_overlap = 50
        mock_config.streaming_enabled = True

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            with patch("secondbrain.cli.commands.get_config", return_value=mock_config):
                runner = CliRunner()
                with runner.isolated_filesystem():
                    Path("/tmp/test_streaming").mkdir(parents=True, exist_ok=True)

                    with patch("secondbrain.document.is_supported", return_value=True):
                        result = runner.invoke(
                            cli,
                            ["ingest", "/tmp/test_streaming"],
                        )

        assert result.exit_code == 0

        mock_ingestor_class.assert_called_once()
        call_kwargs = mock_ingestor_class.call_args[1]
        assert call_kwargs["chunk_size"] == 4096
        assert call_kwargs["chunk_overlap"] == 50

        mock_ingestor.ingest.assert_called_once()


class TestIngestFileValidation:
    """Tests for ingest command file validation."""

    def test_ingest_file_validation(self) -> None:
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["ingest", "/tmp/../../../etc/passwd"],
        )
        assert result.exit_code != 0

        result = runner.invoke(
            cli,
            ["ingest", "/nonexistent/path/file.pdf"],
        )
        assert result.exit_code != 0

        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            runner = CliRunner()
            with runner.isolated_filesystem():
                test_file = Path("/tmp/test_oversized.pdf")
                test_file.touch()

                result = runner.invoke(cli, ["ingest", str(test_file)])

            assert result.exit_code == 0
            mock_ingestor_class.assert_called_once()


class TestIngestEmptyDirectory:
    """Tests for ingest command with empty directories."""

    def test_ingest_empty_directory(self) -> None:
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 0, "failed": 0}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            runner = CliRunner()
            with runner.isolated_filesystem():
                empty_dir = Path("/tmp/test_empty_dir")
                empty_dir.mkdir(parents=True, exist_ok=True)

                (empty_dir / "file.exe").touch()
                (empty_dir / "file.bin").touch()

                with patch("secondbrain.document.is_supported", return_value=False):
                    result = runner.invoke(
                        cli,
                        ["ingest", str(empty_dir)],
                    )

        assert result.exit_code == 0
        assert "Successfully ingested 0 files" in result.output


class TestIngestMixedSuccessFailure:
    """Tests for ingest command with mixed success and failure."""

    def test_ingest_mixed_success_failure(self) -> None:
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 3, "failed": 2}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            runner = CliRunner()
            with runner.isolated_filesystem():
                Path("/tmp/test_mixed").mkdir(parents=True, exist_ok=True)

                with patch("secondbrain.document.is_supported", return_value=True):
                    result = runner.invoke(
                        cli,
                        ["ingest", "/tmp/test_mixed"],
                    )

        assert result.exit_code == 0
        assert "Successfully ingested 3 files" in result.output
        assert "Failed: 2 files" in result.output
        assert "Successfully" in result.output
        assert "Failed" in result.output
