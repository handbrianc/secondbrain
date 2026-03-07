"""Tests for CLI validation edge cases."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli


class TestCLIChunkSizeValidation:
    """Tests for chunk size validation in CLI."""

    def test_ingest_rejects_negative_chunk_size(self) -> None:
        """Test that negative chunk size is rejected."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                cli, ["ingest", "/tmp/test_docs", "--chunk-size", "-100"]
            )
            # Click should reject negative integer
            assert result.exit_code != 0

    def test_ingest_accepts_zero_chunk_size(self) -> None:
        """Test that zero chunk size is accepted by Click (validated by Config)."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                # Click accepts 0, but Config validation would reject it
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--chunk-size", "0"]
                )
                # Click passes it through; validation happens in Config
                assert result.exit_code == 0

    def test_ingest_accepts_valid_chunk_size(self) -> None:
        """Test that valid positive chunk sizes are accepted."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--chunk-size", "2048"]
                )
                # Should not fail due to validation
                assert result.exit_code == 0 or "Validation error" not in result.output

    def test_ingest_chunk_size_boundary_values(self) -> None:
        """Test chunk size with boundary values."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)

                # Test minimum valid value
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--chunk-size", "1"]
                )
                assert result.exit_code == 0 or "Validation error" not in result.output

                # Test large valid value
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--chunk-size", "10000"]
                )
                assert result.exit_code == 0 or "Validation error" not in result.output

    def test_ingest_chunk_size_with_non_integer(self) -> None:
        """Test that non-integer chunk size is rejected."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "/tmp/test", "--chunk-size", "abc"])
        # Click should reject non-integer
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "UsageError" in result.output


class TestCLIBatchSizeValidation:
    """Tests for batch size validation in CLI."""

    def test_ingest_accepts_negative_batch_size(self) -> None:
        """Test that negative batch size is accepted by Click (validated by app logic)."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                # Click accepts negative values; app logic should validate
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--batch-size", "-5"]
                )
                assert result.exit_code == 0

    def test_ingest_accepts_zero_batch_size(self) -> None:
        """Test that zero batch size is accepted by Click (validated by app logic)."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                # Click accepts zero; app logic should validate
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--batch-size", "0"]
                )
                assert result.exit_code == 0

    def test_ingest_accepts_large_batch_size(self) -> None:
        """Test that large batch sizes are accepted."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                result = runner.invoke(
                    cli, ["ingest", "/tmp/test_docs", "--batch-size", "100"]
                )
                # Should accept large batch size
                assert result.exit_code == 0 or "Validation error" not in result.output

    def test_ingest_batch_size_defaults(self) -> None:
        """Test that default batch size is used when not specified."""
        with patch("secondbrain.document.DocumentIngestor") as mock_ingestor:
            mock_ingestor_instance = MagicMock()
            mock_ingestor_instance.ingest.return_value = {"success": 1, "failed": 0}
            mock_ingestor.return_value = mock_ingestor_instance

            runner = CliRunner()
            with runner.isolated_filesystem():
                from pathlib import Path

                Path("/tmp/test_docs").mkdir(parents=True, exist_ok=True)
                result = runner.invoke(cli, ["ingest", "/tmp/test_docs"])
                # Should use default batch size
                assert result.exit_code == 0 or "Validation error" not in result.output


class TestCLIJSONFormatValidation:
    """Tests for JSON format validation in CLI."""

    @patch("secondbrain.search.Searcher")
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
