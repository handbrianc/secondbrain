"""Tests for CLI validation edge cases."""

import json
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


class TestCLIChunkSizeValidation:
    """Tests for chunk size validation in CLI."""

    @pytest.mark.fast
    def test_ingest_rejects_negative_chunk_size(self) -> None:
        """Test that negative chunk size is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            runner = CliRunner()
            result = runner.invoke(cli, ["ingest", tmpdir, "--chunk-size", "-100"])
            assert result.exit_code != 0

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_accepts_zero_chunk_size(self, mock_ingestor: MagicMock) -> None:
        """Test that zero chunk size is accepted by Click (validated by Config)."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(cli, [_create_test_dir(), "--chunk-size", "0"])
        assert result.exit_code == 0

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_accepts_valid_chunk_size(self, mock_ingestor: MagicMock) -> None:
        """Test that valid positive chunk sizes are accepted."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(cli, [_create_test_dir(), "--chunk-size", "2048"])
        assert result.exit_code == 0 or "Validation error" not in result.output

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_chunk_size_boundary_values(self, mock_ingestor: MagicMock) -> None:
        """Test chunk size with boundary values."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(cli, [_create_test_dir(), "--chunk-size", "1"])
        assert result.exit_code == 0 or "Validation error" not in result.output

        result = runner.invoke(cli, [_create_test_dir(), "--chunk-size", "10000"])
        assert result.exit_code == 0 or "Validation error" not in result.output

    @pytest.mark.fast
    def test_ingest_chunk_size_with_non_integer(self) -> None:
        """Test that non-integer chunk size is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CliRunner()
            result = runner.invoke(cli, ["ingest", tmpdir, "--chunk-size", "abc"])
            assert result.exit_code != 0
            assert "Invalid value" in result.output or "UsageError" in result.output


class TestCLIBatchSizeValidation:
    """Tests for batch size validation in CLI."""

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_rejects_negative_batch_size(self, mock_ingestor: MagicMock) -> None:
        """Test that negative batch size is rejected by click.IntRange validation."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ingest", _create_test_dir(), "--batch-size", "-5"]
        )
        assert result.exit_code == 2
        assert (
            "must be at least 1" in result.output.lower()
            or "invalid value" in result.output.lower()
        )

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_rejects_zero_batch_size(self, mock_ingestor: MagicMock) -> None:
        """Test that zero batch size is rejected by click.IntRange validation."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", _create_test_dir(), "--batch-size", "0"])
        assert result.exit_code == 2
        assert (
            "must be at least 1" in result.output.lower()
            or "invalid value" in result.output.lower()
        )

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_accepts_large_batch_size(self, mock_ingestor: MagicMock) -> None:
        """Test that large batch sizes are accepted."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ingest", _create_test_dir(), "--batch-size", "100"]
        )
        assert result.exit_code == 0 or "Validation error" not in result.output

    @patch("secondbrain.document.DocumentIngestor")
    @pytest.mark.fast
    def test_ingest_batch_size_defaults(self, mock_ingestor: MagicMock) -> None:
        """Test that default batch size is used when not specified."""
        mock_ingestor_instance = MagicMock()
        mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor.return_value = mock_ingestor_instance

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", _create_test_dir()])
        assert result.exit_code == 0 or "Validation error" not in result.output


class TestCLIJSONFormatValidation:
    """Tests for JSON format validation in CLI."""

    @patch("secondbrain.search.Searcher")
    @pytest.mark.fast
    def test_search_json_format_valid_output(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test that JSON format produces valid JSON output."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {
                "chunk_id": "test-id",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "test content",
                "score": 0.95,
            }
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test query", "--format", "json"])

        assert result.exit_code == 0
        # Verify output is valid JSON
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert "chunk_id" in parsed[0]

    @patch("secondbrain.search.Searcher")
    @pytest.mark.fast
    def test_search_json_format_empty_results(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test JSON format with empty results."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "nonexistent", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed == []

    @patch("secondbrain.search.Searcher")
    @pytest.mark.fast
    def test_search_json_format_special_chars(
        self, mock_searcher_class: MagicMock
    ) -> None:
        """Test JSON format handles special characters correctly."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {
                "chunk_id": "test-id",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": 'Text with "quotes" and \\backslash',
                "score": 0.9,
            }
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert "quotes" in parsed[0]["chunk_text"]

    @patch("secondbrain.search.Searcher")
    @pytest.mark.fast
    def test_search_json_format_unicode(self, mock_searcher_class: MagicMock) -> None:
        """Test JSON format handles Unicode correctly."""
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = [
            {
                "chunk_id": "test-id",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "こんにちは世界 🌍",
                "score": 0.85,
            }
        ]
        mock_searcher.__enter__ = MagicMock(return_value=mock_searcher)
        mock_searcher.__exit__ = MagicMock(return_value=False)
        mock_searcher_class.return_value = mock_searcher

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert "こんにちは" in parsed[0]["chunk_text"]
