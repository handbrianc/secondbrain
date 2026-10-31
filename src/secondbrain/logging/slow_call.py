"""Slow external-call instrumentation for attributable stalls.

External service calls (LLM, embedding, vector store) occasionally stall for
minutes while the user sees no progress. This module provides
:func:`timed_external_call`, a context manager that measures the wall time of
one logical external call and emits a single WARNING when the call exceeds the
slow-call threshold, naming the operation, the target (model, endpoint or
collection) and the elapsed seconds — so a silent multi-minute gap is
attributable in the default file log without reproducing it under debug
logging.

The threshold defaults to 10 seconds and is overridable through the
``SECONDBRAIN_SLOW_CALL_SECONDS`` environment variable, which is read at call
time; malformed values fall back to the default. A call within the threshold
emits nothing.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = [
    "DEFAULT_SLOW_CALL_SECONDS",
    "SLOW_CALL_SECONDS_ENV",
    "timed_external_call",
]

#: Slow-call threshold when ``SECONDBRAIN_SLOW_CALL_SECONDS`` is unset.
DEFAULT_SLOW_CALL_SECONDS = 10.0

#: Environment variable overriding the slow-call threshold (seconds).
SLOW_CALL_SECONDS_ENV = "SECONDBRAIN_SLOW_CALL_SECONDS"

logger = logging.getLogger(__name__)
# The slow-call record must survive root-level reconfiguration (a quiet CLI
# run keeps root at WARNING, a very quiet one at ERROR): pinning this logger's
# own level means the logger gate never suppresses the record (handler-level
# filtering, which is per-transport, still applies).
logger.setLevel(logging.WARNING)


def _slow_call_threshold() -> float:
    """Resolve the slow-call threshold from the environment.

    Reads :data:`SLOW_CALL_SECONDS_ENV` at call time. Malformed values —
    non-numeric text, empty, non-finite, or non-positive — fall back to
    :data:`DEFAULT_SLOW_CALL_SECONDS` so a typo can never disable or
    spam-enable the instrumentation.

    Returns
    -------
        The threshold in seconds.
    """
    raw = os.environ.get(SLOW_CALL_SECONDS_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_SLOW_CALL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SLOW_CALL_SECONDS
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_SLOW_CALL_SECONDS
    return value


@contextmanager
def timed_external_call(operation: str, target: str) -> Iterator[None]:
    """Measure one external call and WARN when it exceeds the threshold.

    Wrap the outermost request of a logical external operation — one LLM
    call, one embedding batch, one Qdrant search/upsert — not every internal
    helper. On exit, if the measured wall time exceeds the slow-call
    threshold, exactly one WARNING record is emitted naming *operation*,
    *target* and the elapsed seconds; a call within the threshold emits
    nothing. The record is emitted regardless of the ambient log-level
    configuration so silent stalls stay attributable in the default file log.

    The warning is also emitted when the wrapped call raises, provided the
    failed call was slow enough — a stalled call that errors is still
    attributable.

    Args:
        operation: Logical operation name (e.g. ``"llm.generate"``,
            ``"qdrant.search"``).
        target: What the call addressed — the model name, endpoint or
            collection (e.g. ``"gpt-4o-mini"``, ``"secondbrain"``).

    Yields
    ------
        Nothing; the wrapped body runs unchanged.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        threshold = _slow_call_threshold()
        if elapsed > threshold:
            logger.warning(
                "Slow external call: operation=%s target=%s elapsed=%.3fs "
                "(threshold=%.3fs)",
                operation,
                target,
                elapsed,
                threshold,
            )
