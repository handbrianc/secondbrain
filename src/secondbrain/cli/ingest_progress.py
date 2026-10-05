"""Flicker-free progress UI for the ingest command.

``IngestProgressUI`` renders a fixed-row Rich ``Progress`` display for document
ingestion and defers WARNING+ log records until the display closes, so log
output never interleaves with the live region.

Anti-flicker rules baked into this module:

- No spinner column and no manual ``refresh()`` calls: the display repaints
  exclusively through Rich's own auto-refresh thread.
- Rows are created once when the UI opens, so the rendered line count never
  changes mid-run.
- Phase rows track per-phase percent directly; indeterminate phases
  (``total == 0``) render a pulsing bar without a percent cell.
- WARNING+ log records are deferred and replayed after the bars close.

Events may arrive from worker threads/processes; the ingestor drains its queue
on the main thread, so these callbacks only mutate Rich task state (cheap,
non-blocking) and let Rich handle the painting.
"""

import contextlib
import logging
from pathlib import Path
from types import TracebackType

from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.text import Text

logger = logging.getLogger(__name__)

PHASE_LABELS: dict[str, str] = {
    "extract": "extracting",
    "chunk": "chunking",
    "embed": "embedding",
    "store": "storing",
}
"""Human-readable labels for the pipeline phase reported by the ingestor."""


class _DeferringFilter(logging.Filter):
    """Logging filter that stashes WARNING+ records for later replay.

    While the progress display is live, WARNING+ records are captured and
    suppressed at the handler level so they cannot interleave with the Rich
    live region. The stashed records are replayed once the display closes.
    """

    def __init__(self, stash: list[logging.LogRecord]) -> None:
        """Create a filter sharing ``stash`` with the owning UI.

        Args:
            stash: List that matching records are appended to.
        """
        super().__init__()
        self._stash = stash

    def filter(self, record: logging.LogRecord) -> bool:
        """Defer WARNING+ records; let everything else through.

        Args:
            record: The record about to be emitted by the handler.

        Returns:
            True to let the handler emit the record, False to suppress it.
        """
        if record.levelno >= logging.WARNING:
            self._stash.append(record)
            return False
        return True


class _OverallCountColumn(MofNCompleteColumn):
    """``MofNCompleteColumn`` that renders only for the overall row.

    The multi-file layout shares one column set between the overall row and
    the activity row; the activity row opts out via its ``show_mofn`` task
    field so only the overall row shows "N/M".
    """

    def render(self, task: Task) -> Text:
        """Render the completed/total cell, or empty for non-overall rows.

        Args:
            task: The task row being rendered.

        Returns:
            The rendered cell text.
        """
        if not task.fields.get("show_mofn", False):
            return Text("")
        return super().render(task)


class IngestProgressUI:
    """Fixed-row progress display for the ingest command.

    The UI exposes two callbacks that are handed to
    :class:`~secondbrain.document.DocumentIngestor`:

    - :meth:`on_phase` receives ``(file_path, phase, done, total)`` phase
      events and drives the per-file phase row (percent, or pulsing bar when
      ``total == 0``).
    - :meth:`on_file_done` receives ``(file_path, success)`` after each file
      completes and advances the overall files bar.

    Use as a context manager::

        ui = IngestProgressUI(console, total_files, is_single=total_files == 1)
        with ui:
            ingestor = DocumentIngestor(
                progress_callback=ui.on_file_done,
                on_phase_progress=ui.on_phase,
                ...
            )
            results = ingestor.ingest(...)
            ui.finish()
    """

    def __init__(self, console: Console, total_files: int, is_single: bool) -> None:
        """Create the display without opening it.

        Args:
            console: Console the display renders to.
            total_files: Number of files the ingest is expected to process.
            is_single: True for a single-file ingest (one phase row, no
                overall row), False for the two-row multi-file layout.
        """
        self._console = console
        self._total_files = total_files
        self._is_single = is_single
        self._files_completed = 0
        self._deferred_records: list[logging.LogRecord] = []
        self._attached_filters: list[tuple[logging.Handler, _DeferringFilter]] = []

        columns: list[
            TextColumn | BarColumn | TaskProgressColumn | _OverallCountColumn
        ] = [
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
        ]
        if not is_single:
            columns.insert(1, _OverallCountColumn())

        self.progress = Progress(
            *columns,
            console=console,
            auto_refresh=True,
            refresh_per_second=8,
        )
        self.overall_task_id: TaskID | None = None
        self.activity_task_id: TaskID | None = None

    def __enter__(self) -> "IngestProgressUI":
        """Create the fixed rows, start the live display, and defer logs.

        Returns:
            The UI itself, ready to receive phase and file-done events.
        """
        if self._is_single:
            self.overall_task_id = None
            self.activity_task_id = self.progress.add_task(
                "Starting ingest", total=None
            )
        else:
            self.overall_task_id = self.progress.add_task(
                f"Ingesting {self._total_files} files",
                total=self._total_files,
                show_mofn=True,
            )
            self.activity_task_id = self.progress.add_task(
                "Starting ingest", total=None
            )
        self.progress.start()
        self._attach_deferring_filters()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop the live display, restore logging, and replay deferred logs.

        Args:
            exc_type: Exception class if the managed block raised, else None.
            exc_val: Exception instance if the managed block raised, else None.
            exc_tb: Traceback if the managed block raised, else None.
        """
        try:
            self.progress.stop()
        finally:
            try:
                self._detach_deferring_filters()
            finally:
                # Replay must never mask the ingest result.
                with contextlib.suppress(Exception):
                    self._replay_deferred_records()

    def on_phase(self, file_path: Path, phase: str, done: int, total: int) -> None:
        """Update the activity row with a pipeline phase event.

        Args:
            file_path: File the event belongs to; its name becomes the row
                description (last write wins when workers interleave).
            phase: Pipeline phase name; see :data:`PHASE_LABELS`.
            done: Units completed in this phase (pages, chunks, batches...).
            total: Total units for this phase; 0 means unknown, rendering the
                row as an indeterminate pulsing bar.
        """
        if self.activity_task_id is None:
            return
        label = PHASE_LABELS.get(phase, phase)
        description = f"{escape(file_path.name)} · {label}"
        if total == 0:
            self.progress.update(self.activity_task_id, description=description)
            task = self._task(self.activity_task_id)
            if task.total is not None:
                task.total = None
            self.progress.update(self.activity_task_id, completed=done)
        else:
            self.progress.update(
                self.activity_task_id,
                description=description,
                completed=done,
                total=total,
            )

    def on_file_done(self, file_path: Path, success: bool) -> None:
        """Advance the overall bar and stamp the activity row with the result.

        Args:
            file_path: File that finished processing.
            success: True if the file was ingested, False if it failed.
        """
        self._files_completed += 1
        if self.overall_task_id is not None:
            self.progress.update(self.overall_task_id, completed=self._files_completed)
        if self.activity_task_id is None:
            return
        status = "✓" if success else "✗"
        style = "green" if success else "red"
        self.progress.update(
            self.activity_task_id,
            description=f"[{style}]{status} {escape(file_path.name)}[/{style}]",
            completed=1,
            total=1,
        )

    def finish(self) -> None:
        """Push the overall bar to 100% and settle the rows before closing.

        Called right before leaving the context manager. The overall row is
        pushed to ``total_files`` (files skipped by ``skip_existing`` still
        count as processed); in single-file mode the phase row is pushed to
        100% when its total is known. The multi-file activity row is left
        as-is.
        """
        if self.overall_task_id is not None:
            self.progress.update(self.overall_task_id, completed=self._total_files)
            return
        if self.activity_task_id is None:
            return
        task = self._task(self.activity_task_id)
        if task.total is not None:
            self.progress.update(self.activity_task_id, completed=task.total)

    def _task(self, task_id: TaskID) -> Task:
        """Return the Rich task row for ``task_id``.

        Args:
            task_id: ID returned by :meth:`rich.progress.Progress.add_task`.

        Returns:
            The matching task row.

        Raises:
            KeyError: If ``task_id`` is not tracked by the display.
        """
        for task in self.progress.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Unknown task id: {task_id}")

    def _attach_deferring_filters(self) -> None:
        """Attach the deferring filter to every root logging handler.

        A no-op when the root logger has no handlers. Each handler gets its
        own filter instance sharing the single record stash; duplicates are
        dropped at replay time.
        """
        for handler in list(logging.root.handlers):
            log_filter = _DeferringFilter(self._deferred_records)
            handler.addFilter(log_filter)
            self._attached_filters.append((handler, log_filter))

    def _detach_deferring_filters(self) -> None:
        """Remove the deferring filters from the root logging handlers."""
        for handler, log_filter in self._attached_filters:
            try:
                handler.removeFilter(log_filter)
            except ValueError:
                # Filter already gone (handler replaced mid-run); nothing to do.
                logger.debug("Deferring filter already removed from handler; skipping")
                continue
        self._attached_filters = []

    def _replay_deferred_records(self) -> None:
        """Replay stashed WARNING+ records through their originating loggers.

        The same record can be stashed once per root handler; it is replayed
        exactly once (deduplicated by identity). A failing handler is skipped
        so one bad record cannot drop the rest.
        """
        seen: set[int] = set()
        for record in self._deferred_records:
            if id(record) in seen:
                continue
            seen.add(id(record))
            try:
                logging.getLogger(record.name).handle(record)
            except Exception:
                # Skip a bad record; still replay the rest.
                logger.debug(
                    "Failed to replay deferred log record from %s",
                    record.name,
                    exc_info=True,
                )
                continue
        self._deferred_records.clear()
