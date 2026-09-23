"""Gap tests for the CLI ingest command: pool wiring and failure reporting.

Targets the uncovered branches reported by coverage for
``secondbrain/cli/ingest.py``:

- ``--pool`` defaulting to ``config().ingest_pool`` when omitted and being
  forwarded verbatim when provided;
- ``--cores`` forwarded and the excessive-cores clamp warning;
- ``--batch-size`` forwarded to the ingestor;
- ``--no-skip-existing`` producing ``skip_existing=False`` vs the default
  ``None``;
- non-int ``failed`` counts printing nothing extra;
- per-file failure lines rendered from ``results["failures"]``;
- ``failures`` not being a list (ignored silently).

Mocking style matches ``tests/test_cli/test_ingest_commands.py``: patch
``secondbrain.document.DocumentIngestor`` with a MagicMock and drive the CLI
through ``CliRunner``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli
from secondbrain.config import Config


def _mock_ingestor(result: dict[str, Any]) -> tuple[MagicMock, MagicMock]:
    ingestor = MagicMock()
    ingestor.ingest.return_value = result
    ingestor_class = MagicMock(return_value=ingestor)
    return ingestor, ingestor_class


def _invoke(ingestor_class: MagicMock, tmp_path: Path, *extra: str) -> Any:
    runner = CliRunner()
    with patch("secondbrain.document.DocumentIngestor", ingestor_class):
        with patch("secondbrain.document.is_supported", return_value=True):
            return runner.invoke(cli, ["ingest", str(tmp_path), *extra])


class TestPoolWiring:
    """--pool default from config and explicit forwarding."""

    def test_pool_defaults_to_config_ingest_pool(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        mock_cfg = MagicMock(spec=Config)
        mock_cfg.chunk_size = 512
        mock_cfg.chunk_overlap = 50
        mock_cfg.ingest_pool = "thread"
        monkeypatch.setattr("secondbrain.cli.ingest.config", lambda: mock_cfg)

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        forwarded = ingestor.ingest.call_args[1]
        assert forwarded["pool"] == "thread"

    def test_pool_explicit_value_forwarded(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        mock_cfg = MagicMock(spec=Config)
        mock_cfg.chunk_size = 512
        mock_cfg.chunk_overlap = 50
        mock_cfg.ingest_pool = "process"
        monkeypatch.setattr("secondbrain.cli.ingest.config", lambda: mock_cfg)

        result = _invoke(ingestor_class, tmp_path, "--pool", "thread")

        assert result.exit_code == 0
        forwarded = ingestor.ingest.call_args[1]
        assert forwarded["pool"] == "thread"

    def test_invalid_pool_choice_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path, "--pool", "fork")

        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestCoresAndBatchSize:
    """--cores clamping/forwarding and --batch-size forwarding."""

    def test_cores_forwarded_when_within_budget(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path, "--cores", "2")

        assert result.exit_code == 0
        forwarded = ingestor.ingest.call_args[1]
        assert forwarded["cores"] == 2
        assert "Warning" not in result.output

    def test_excessive_cores_clamped_with_warning(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})
        available = __import__("os").cpu_count() or 1

        result = _invoke(ingestor_class, tmp_path, "--cores", str(available + 5))

        assert result.exit_code == 0
        assert "Warning" in result.output
        forwarded = ingestor.ingest.call_args[1]
        assert forwarded["cores"] == available

    def test_batch_size_forwarded(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path, "--batch-size", "7")

        assert result.exit_code == 0
        forwarded = ingestor.ingest.call_args[1]
        assert forwarded["batch_size"] == 7

    def test_batch_size_zero_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path, "--batch-size", "0")

        assert result.exit_code != 0


class TestSkipExistingFlag:
    """--no-skip-existing maps to skip_existing=False; default is None."""

    def test_default_passes_skip_existing_none(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        assert ingestor.ingest.call_args[1]["skip_existing"] is None

    def test_no_skip_existing_passes_false(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        ingestor, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path, "--no-skip-existing")

        assert result.exit_code == 0
        assert ingestor.ingest.call_args[1]["skip_existing"] is False


class TestResultReporting:
    """Final summary rendering incl. non-int failed and failure lists."""

    def test_non_int_failed_prints_no_failure_block(self, tmp_path: Path) -> None:
        """failed='n/a' (bad backend payload) must not crash the summary."""
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor({"success": 1, "failed": "n/a"})

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        assert "Successfully ingested 1 files" in result.output
        assert "Failed:" not in result.output

    def test_failures_list_rendered_per_file(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor(
            {
                "success": 1,
                "failed": 1,
                "failures": [("/tmp/short/bad.txt", "parse error")],
            }
        )

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        flat = " ".join(result.output.split())
        assert "Failed: 1 files" in flat
        assert "parse error" in flat
        assert "bad.txt" in flat

    def test_non_list_failures_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor(
            {"success": 0, "failed": 2, "failures": "not-a-list"}
        )

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        assert "Failed: 2 files" in result.output
        # No per-file lines rendered from a non-list payload.
        assert "not-a-list" not in result.output

    def test_zero_failed_prints_only_success(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("hello")
        _, ingestor_class = _mock_ingestor({"success": 1, "failed": 0})

        result = _invoke(ingestor_class, tmp_path)

        assert result.exit_code == 0
        assert "Successfully ingested 1 files" in result.output
        assert "Failed:" not in result.output
