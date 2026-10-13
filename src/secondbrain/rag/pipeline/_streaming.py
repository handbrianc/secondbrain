"""Streaming-control primitives for the RAG pipeline.

Internal abort signals and the per-window streaming sink that forwards
tokens live while guarding against derailment.
"""

from __future__ import annotations

from collections.abc import Callable

from secondbrain.rag.pipeline._leak_scrub import (
    _REASONING_BUDGET_FALLBACK_PREFIX,
    _is_content_self_correction,
)


class _StreamAbortError(Exception):
    """Internal control-flow signal to stop a streaming window early."""


class _StreamLeakError(Exception):
    """Internal signal: a window leaked reasoning/self-correction into content."""


class _WindowStreamSink:
    """Streaming sink for one map-reduce window.

    Collects the streamed content, tracks the longest prefix that stayed
    acceptable, and raises :class:`_StreamAbortError` the moment the window
    derails: a chain-of-thought spiral, a flood, a figure-verification leak
    arriving as content, or the provider's dead-end fallback sentence.

    Reasoning is consumed for spiral detection only -- it is never forwarded
    to the terminal, so a thinking spiral or the raw reasoning block is not
    shown to the user. The heading is emitted once, before the first content
    chunk, and only when a terminal callback is registered.
    """

    def __init__(
        self,
        heading: str,
        *,
        is_reasoning_spiral: Callable[[str], bool],
        is_flooding: Callable[[str], bool],
        on_chunk: Callable[[str, str | None], None] | None,
    ) -> None:
        self._heading = heading
        self._is_reasoning_spiral = is_reasoning_spiral
        self._is_flooding = is_flooding
        self._on_chunk = on_chunk
        self.buffered: list[str] = []  # everything streamed (incl. any derailed tail)
        self.clean: list[
            str
        ] = []  # longest prefix that stayed acceptable as it streamed
        self.reason_log: list[
            str
        ] = []  # accumulated chain-of-thought for spiral detection
        self.heading_shown = False
        self.aborted = False

    def __call__(self, content: str, reasoning: str | None) -> None:
        if reasoning:
            self._absorb_reasoning(reasoning)
        if content:
            self._absorb_content(content)

    def _absorb_reasoning(self, reasoning: str) -> None:
        self.reason_log.append(reasoning)
        if self._is_reasoning_spiral("".join(self.reason_log)):
            raise _StreamAbortError()

    def _absorb_content(self, content: str) -> None:
        self.buffered.append(content)
        joined = "".join(self.buffered)
        # Flush before streaming a chunk that would trip the flood guard, so a
        # derailed tail is never surfaced, and never reaches `clean`.
        if self._is_flooding(joined):
            raise _StreamAbortError()
        # A figure-verification leak arriving as content (e.g. "?? (wait, the
        # text says ...)") precedes a stall -- abort and clean-retry.
        if _is_content_self_correction(joined.lower()):
            raise _StreamAbortError()
        # Never surface the provider's "I got stuck in repetitive reasoning"
        # dead-end; treat it as a derail and relax-retry.
        if joined.lstrip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX):
            raise _StreamAbortError()
        self._emit(content)
        self.clean.append(content)

    def _emit(self, content: str) -> None:
        if self._on_chunk is None:
            return
        if not self.heading_shown:
            self._on_chunk(f"{self._heading}\n\n", None)
            self.heading_shown = True
        self._on_chunk(content, None)

    @property
    def text(self) -> str:
        """The longest clean prefix streamed for this window."""
        return "".join(self.clean)
