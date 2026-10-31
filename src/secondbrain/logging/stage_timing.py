"""Pipeline stage-timing instrumentation for attributable ingests.

Long-running pipeline stages (audio decode/ASR transcription, LLM topic
segmentation, chunking, embedding) otherwise leave no per-stage trail: a
multi-minute stage is indistinguishable from a hung worker after the fact.
This module provides :func:`timed_stage`, a context manager that measures one
logical pipeline stage and emits exactly one record when the stage completes —
INFO on success, WARNING when the stage exceeds the slow-stage threshold — so
a long or stalled ingest is attributable from the log alone.

Stage failures are logged before the error surfaces: when the wrapped body
raises, one WARNING naming the stage, the elapsed time and the error is
emitted, then the exception is re-raised unchanged.

The slow-stage threshold defaults to 60 seconds and is overridable through the
``SECONDBRAIN_SLOW_STAGE_SECONDS`` environment variable, which is read at call
time; malformed values fall back to the default. The INFO success trail is a
normal log record (visible at INFO level); the WARNING slow/failure records
require no debug-level flag or environment variable.

Elapsed time is measured on ``time.monotonic()`` so callers can anchor the
measurement to the moment the stage actually began (see *started_at*).
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = [
    "DEFAULT_SLOW_STAGE_SECONDS",
    "SLOW_STAGE_SECONDS_ENV",
    "timed_stage",
]

#: Slow-stage threshold when ``SECONDBRAIN_SLOW_STAGE_SECONDS`` is unset.
DEFAULT_SLOW_STAGE_SECONDS = 60.0

#: Environment variable overriding the slow-stage threshold (seconds).
SLOW_STAGE_SECONDS_ENV = "SECONDBRAIN_SLOW_STAGE_SECONDS"

logger = logging.getLogger(__name__)


def _slow_stage_threshold() -> float:
    """Resolve the slow-stage threshold from the environment.

    Reads :data:`SLOW_STAGE_SECONDS_ENV` at call time. Malformed values —
    non-numeric text, empty, non-finite, or non-positive — fall back to
    :data:`DEFAULT_SLOW_STAGE_SECONDS` so a typo can never disable or
    spam-enable the instrumentation.

    Returns
    -------
        The threshold in seconds.
    """
    raw = os.environ.get(SLOW_STAGE_SECONDS_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_SLOW_STAGE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SLOW_STAGE_SECONDS
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_SLOW_STAGE_SECONDS
    return value


@contextmanager
def timed_stage(
    stage: str, *, context: str, started_at: float | None = None
) -> Iterator[None]:
    """Measure one pipeline stage and log its outcome exactly once.

    Wrap the logical stage boundary — one decode/transcription call, one topic
    segmentation pass, one chunking or embedding pass — not every internal
    helper. On successful completion exactly one record is emitted: INFO with
    the stage, the context and the elapsed seconds, or WARNING instead when
    the elapsed time exceeds the slow-stage threshold (see the module
    docstring), so a slow stage warns without any debug-level flag.

    When the wrapped body raises, one WARNING naming the stage, the elapsed
    time and the error is emitted before the exception is re-raised unchanged
    — a stage failure is attributable in the log before the ingest error
    surfaces. (The stage record stays at WARNING; ERROR-level reporting is
    owned by the caller's failure accounting.)

    Args:
        stage: Logical stage name (e.g. ``"audio.transcription"``,
            ``"audio.topic_segmentation"``, ``"chunk"``, ``"embed"``).
        context: What the stage worked on — identifies the work unit in the
            log record (the ingested file path for ingestor stages).
        started_at: Optional ``time.monotonic()`` anchor taken when the stage
            actually began (e.g. the worker submission time, so the elapsed
            time covers pool queuing plus the wait). None measures from entry
            into the context manager.

    Yields
    ------
        Nothing; the wrapped body runs unchanged.
    """
    start = time.monotonic() if started_at is None else started_at
    try:
        yield
    except BaseException as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "Pipeline stage failed: stage=%s context=%s elapsed=%.3fs error=%s: %s",
            stage,
            context,
            elapsed,
            type(exc).__name__,
            exc,
        )
        raise
    else:
        elapsed = time.monotonic() - start
        threshold = _slow_stage_threshold()
        if elapsed > threshold:
            logger.warning(
                "Slow pipeline stage: stage=%s context=%s elapsed=%.3fs "
                "(threshold=%.3fs)",
                stage,
                context,
                elapsed,
                threshold,
            )
        else:
            logger.info(
                "Pipeline stage completed: stage=%s context=%s elapsed=%.3fs",
                stage,
                context,
                elapsed,
            )
