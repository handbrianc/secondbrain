"""Docling page-batch progress scraping via a DEBUG log handler.

Docling 2.x exposes no progress callback API for its conversion pipeline:
the per-page hook proposals are still open upstream (docling PRs #3042 and
#3566), and the only supported in-band signal that pages have been processed
is a DEBUG log line emitted by ``docling.pipeline.base_pipeline`` once per
page batch::

    Finished converting pages {done}/{total} time={seconds:.3f}

The line fires on the same thread that runs ``converter.convert()`` and the
``done`` counter advances in-order/monotonic (batches of
``settings.perf.page_batch_size`` pages), so a transient
:class:`logging.Handler` attached for the duration of a single conversion can
reliably surface (done, total) ticks to the ingestion progress bar.

Because docling's ancestor ``docling`` logger is forced to WARNING elsewhere
in this repo (``docling_factory.py``), the DEBUG records would normally be
dropped before reaching the handler. This context manager therefore raises the
``docling.pipeline.base_pipeline`` logger's level to DEBUG on entry and
restores the previous level on exit. Propagation is disabled during the
conversion so DEBUG records do not reach root handlers, then restored on exit.
Throughput-affecting docling settings (e.g. ``page_batch_size``) are never
modified — only the logger state is borrowed for the conversion.

Everything here is defensive: if docling is not installed or anything else
fails, the context manager degrades to a no-op so ingestion is never blocked
by a progress-reporting nicety.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# The exact line docling's base pipeline emits per page batch (verified against
# the installed docling package: base_pipeline.py
# ``_log.debug(f"Finished converting pages {total_pages_processed}/"
#              f"{len(conv_res.pages)} time={end_batch_time:.3f}")``).
# ``time=...`` is fixed text in the real message but is not needed here, so it
# is simply not matched.
_PAGE_BATCH_RE = re.compile(r"Finished converting pages (\d+)/(\d+)")

# docling's own pipeline logger; the batch line is logged at DEBUG via
# ``_log = logging.getLogger(__name__)`` inside base_pipeline.py.
_TARGET_LOGGER = "docling.pipeline.base_pipeline"


class _PageBatchHandler(logging.Handler):
    """Log handler translating docling page-batch DEBUG lines to on_tick calls.

    Matches only the "Finished converting pages N/M" record message and drops
    everything else. ``on_tick`` failures are swallowed: a hostile progress
    callback must never break a conversion in flight.
    """

    def __init__(self, on_tick: Callable[[int, int], None]) -> None:
        super().__init__(level=logging.DEBUG)
        self._on_tick = on_tick

    def emit(self, record: logging.LogRecord) -> None:
        match = _PAGE_BATCH_RE.match(record.getMessage())
        if match is None:
            return
        with contextlib.suppress(Exception):
            self._on_tick(int(match.group(1)), int(match.group(2)))


@contextmanager
def scraped_page_progress(
    on_tick: Callable[[int, int], None],
) -> Iterator[None]:
    """Surface docling page-batch progress from its DEBUG pipeline log.

    Attaches a transient :class:`logging.Handler` to docling's
    ``docling.pipeline.base_pipeline`` logger for the duration of the wrapped
    block (i.e. one ``converter.convert()`` call), translating each
    ``Finished converting pages N/M`` DEBUG record into ``on_tick(N, M)``
    calls. Docling 2.x has no progress callback API (upstream per-page hooks
    are open PRs #3042/#3566), so this log line is the only supported signal;
    it fires on the same thread as ``convert()`` and advances in-order, which
    keeps the ticks monotonic.

    The ``docling`` ancestor logger is pinned to WARNING elsewhere in this
    repo, so on entry the target logger's level is raised to DEBUG and the
    previous level is restored on exit. Propagation is disabled while the
    handler is attached to prevent DEBUG records from reaching root handlers,
    and restored on exit. Docling settings that affect throughput
    (``page_batch_size`` etc.) are never modified. ``on_tick`` failures are
    swallowed.

    Degrades to a plain no-op context manager if docling's pipeline module
    cannot be imported or anything else fails, so callers never need to guard
    around it.

    Parameters
    ----------
    on_tick:
        ``(done, total)`` callback invoked per docling page batch, where
        ``done`` counts pages finished so far and ``total`` is the document's
        total page count.

    Yields
    ------
    None
        Nothing; used purely for the enter/exit side effects.
    """
    try:
        import docling.pipeline.base_pipeline as base_pipeline_module  # noqa: F401
    except Exception:
        # docling unavailable / stubbed: report no progress, break nothing.
        yield
        return

    try:
        log = logging.getLogger(_TARGET_LOGGER)
        previous_level = log.level
        previous_propagate = log.propagate
        handler = _PageBatchHandler(on_tick)
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)
        log.propagate = False
    except Exception:
        # Defensive-coding failure before tracking can start (e.g. exotic
        # logger state): run the block untracked instead of failing.
        yield
        return

    try:
        yield
    finally:
        try:
            log.removeHandler(handler)
            log.setLevel(previous_level)
            log.propagate = previous_propagate
        except Exception:
            logger.debug(
                "Failed to restore docling logger state after conversion",
                exc_info=True,
            )
