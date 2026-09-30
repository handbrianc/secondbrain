"""Tests for CLI ingest commands.

This module provides comprehensive tests for the ingest command functionality,
including progress callbacks, cores validation, streaming config, file validation,
empty directories, and mixed success/failure scenarios.
"""

import io
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from rich.console import Console

from secondbrain.cli import cli
from secondbrain.cli.ingest_progress import IngestProgressUI
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


class TestIngestProgressCallbacksForFiles:
    """Single and multi-file ingestion wires up the progress callbacks."""

    def test_single_file_sets_progress_and_chunk_callbacks(self, tmp_path) -> None:
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello world content")
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        runner = CliRunner()
        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            with patch("secondbrain.document.is_supported", return_value=True):
                result = runner.invoke(cli, ["ingest", str(test_file)])

        assert result.exit_code == 0
        call_kwargs = mock_ingestor_class.call_args[1]
        assert call_kwargs.get("progress_callback") is not None
        assert callable(call_kwargs.get("on_phase_progress"))
        assert "on_chunk_progress" not in call_kwargs
        mock_ingestor.ingest.assert_called_once()


class TestIngestProgressUI:
    """Unit tests for the fixed-row :class:`IngestProgressUI` state machine.

    Assertions target the underlying Rich task state (description, completed,
    total) plus one rendered-output check, keeping the tests deterministic.
    """

    @staticmethod
    def _console() -> Console:
        """Build a deterministic terminal console writing to an in-memory buffer."""
        return Console(
            file=io.StringIO(),
            force_terminal=True,
            width=100,
            legacy_windows=False,
        )

    @staticmethod
    def _tasks(ui: IngestProgressUI) -> dict:
        """Map task id to the live Rich task row for state assertions."""
        return {task.id: task for task in ui.progress.tasks}

    def test_single_file_phase_tracks_percent(self) -> None:
        ui = IngestProgressUI(self._console(), total_files=1, is_single=True)
        with ui:
            ui.on_phase(Path("report.pdf"), "extract", 10, 20)

            assert ui.overall_task_id is None
            assert ui.activity_task_id is not None
            task = self._tasks(ui)[ui.activity_task_id]
            assert task.description == "report.pdf · extracting"
            assert task.completed == 10
            assert task.total == 20
            assert task.percentage == 50.0

            ui.finish()
            assert task.completed == 20

    def test_rendered_output_contains_phase_and_percent(self) -> None:
        console = self._console()
        ui = IngestProgressUI(console, total_files=1, is_single=True)
        with ui:
            ui.on_phase(Path("report.pdf"), "extract", 10, 20)
        output = console.file.getvalue()
        assert "report.pdf · extracting" in output
        assert "50%" in output

    def test_multi_file_overall_increments_and_activity_marks(self) -> None:
        ui = IngestProgressUI(self._console(), total_files=3, is_single=False)
        with ui:
            assert ui.overall_task_id is not None
            assert ui.activity_task_id is not None

            ui.on_file_done(Path("a.txt"), True)
            ui.on_file_done(Path("b.txt"), False)

            tasks = self._tasks(ui)
            overall = tasks[ui.overall_task_id]
            activity = tasks[ui.activity_task_id]
            assert "Ingesting 3 files" in overall.description
            assert overall.total == 3
            assert overall.completed == 2
            assert overall.fields.get("show_mofn") is True
            assert activity.description == "[red]✗ b.txt[/red]"
            assert (activity.completed, activity.total) == (1, 1)

            ui.finish()
            assert overall.completed == 3
            assert activity.description == "[red]✗ b.txt[/red]"

    def test_indeterminate_phase_keeps_total_none(self) -> None:
        ui = IngestProgressUI(self._console(), total_files=1, is_single=True)
        with ui:
            ui.on_phase(Path("scan.pdf"), "extract", 0, 0)
            task = self._tasks(ui)[ui.activity_task_id]
            assert task.total is None
            assert task.description == "scan.pdf · extracting"

            # A later known-total phase becomes determinate again.
            ui.on_phase(Path("scan.pdf"), "chunk", 1, 1)
            assert task.total == 1
            assert task.completed == 1
            assert task.description == "scan.pdf · chunking"

            # And a subsequent unknown-total phase returns to indeterminate.
            ui.on_phase(Path("scan.pdf"), "embed", 0, 0)
            assert task.total is None
            assert task.completed == 0

    def test_unknown_phase_falls_back_to_phase_name(self) -> None:
        ui = IngestProgressUI(self._console(), total_files=1, is_single=True)
        with ui:
            ui.on_phase(Path("report.pdf"), "future", 2, 4)
            task = self._tasks(ui)[ui.activity_task_id]
            assert task.description == "report.pdf · future"

    def test_deferred_logging_replays_after_close(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        try:
            ui = IngestProgressUI(self._console(), total_files=1, is_single=True)
            with ui:
                logging.getLogger("test.ingest_progress").info("quiet passthrough")
                logging.getLogger("test.ingest_progress").warning("boom")
                assert "boom" not in stream.getvalue()
                assert "quiet passthrough" in stream.getvalue()
            assert "boom" in stream.getvalue()
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)


class TestIngestCoresValidation:
    """Tests for ingest command cores parameter validation."""

    def test_ingest_cores_validation(self, tmp_path) -> None:
        runner = CliRunner()
        available_cores = os.cpu_count() or 1

        # Use a temp dir with one file instead of /tmp (which has 133 files, causing 164s traversal)
        test_file = tmp_path / "dummy.txt"
        test_file.write_text("hello world")
        test_dir = str(tmp_path)

        # Mock DocumentIngestor to bypass costly docling/embedding initialization.
        # All three invoke cases below exercise CLI arg-validation and warning-logic
        # only — none depend on actual document ingestion, so a bare mock suffices.
        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = {"success": 1, "failed": 0}
        mock_ingestor_class = MagicMock(return_value=mock_ingestor)

        with patch("secondbrain.document.DocumentIngestor", mock_ingestor_class):
            result = runner.invoke(
                cli,
                ["ingest", test_dir, "--cores", "0"],
            )
            assert result.exit_code != 0
            assert result.exception is not None
            assert "positive" in str(result.exception).lower()

            result = runner.invoke(
                cli,
                ["ingest", test_dir, "--cores", "-1"],
            )
            assert result.exit_code != 0
            assert result.exception is not None
            assert "positive" in str(result.exception).lower()

            excessive_cores = available_cores + 10
            result = runner.invoke(
                cli,
                ["ingest", test_dir, "--cores", str(excessive_cores)],
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

        mock_config_func = MagicMock(spec=Config)
        mock_config_func.chunk_size = 4096
        mock_config_func.chunk_overlap = 50
        mock_config_func.streaming_enabled = True

        with (
            patch("secondbrain.document.DocumentIngestor", mock_ingestor_class),
            patch("secondbrain.cli.ingest.config", return_value=mock_config_func),
        ):
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
