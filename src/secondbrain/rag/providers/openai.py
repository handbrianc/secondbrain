"""OpenAI LLM provider implementation for RAG pipeline.

Provides OpenAILLMProvider class that implements the LocalLLMProvider protocol
for using OpenAI API as an LLM backend.
"""

# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=arg-type
# mypy: disable-error-code=union-attr
# (openai 3.x stub gaps: dict-based messages don't satisfy the
#  ChatCompletionMessageParam union without casting; the create() overload
#  union on stream=True + top_p trips union-attr. arg-type also covers the
#  kwargs-dict passed to embeddings.create in the embedding provider's twin
#  module, which has the same stub-gap shape.)

import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import httpx2
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.logging import get_logger

from ..interfaces import LocalLLMProvider, StreamingCallback

logger = get_logger(__name__)

# Degenerate-loop guard: a trailing window that nearly exactly repeats an earlier
# one means the model is re-uttering itself, not progressing. Applied to both the
# reasoning channel and the answer-content channel (a model can spiral while
# drafting prose too). MIN_CHARS defers judging until the stream is substantial.
_REASON_LOOP_WINDOW = 500
_REASON_LOOP_INTERVAL = 1200
_REASON_LOOP_RATIO = 0.9
_REASON_LOOP_MIN_CHARS = 4000
_CONTENT_LOOP_WINDOW = 500
_CONTENT_LOOP_INTERVAL = 1500
_CONTENT_LOOP_RATIO = 0.9
_CONTENT_LOOP_MIN_CHARS = 4000


def _normalize_reasoning(text: str) -> str:
    """Lowercase and keep only alphanumerics for repetition comparison."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_repeat_window(window: str, seen: list[str], ratio: float) -> bool:
    """Return whether a trailing window nearly exactly duplicates an earlier one."""
    return bool(window) and any(
        SequenceMatcher(None, w, window).ratio() > ratio for w in seen
    )


def _log_token_usage(operation: str, usage: object, model: str) -> None:
    """Emit one structured token-usage log line when a response carries usage.

    OpenAI-compatible responses report ``usage.prompt_tokens``,
    ``usage.completion_tokens`` and ``usage.total_tokens``; the fields are
    logged verbatim (``None`` when the server omitted them) so the record can
    be asserted or parsed downstream. Streaming endpoints that do not include
    usage chunks simply produce no log line.
    """
    if usage is None:
        return
    logger.info(
        "%s token usage: model=%s prompt_tokens=%s completion_tokens=%s "
        "total_tokens=%s",
        operation,
        model,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        getattr(usage, "total_tokens", None),
    )


@dataclass
class _RepeatGuard:
    """Repetition detector for one streamed text channel.

    Accumulates chunk text and, every ``interval`` characters past
    ``min_chars``, normalizes the trailing ``window`` characters and
    compares it against previously seen windows. A near-exact repeat of an
    earlier window means the model is re-uttering itself, not progressing.

    Accumulation (``accumulate``) is separate from judgement (``check``) so
    callers can interleave other length-based halts between the two steps
    with the same observable ordering as before the split.
    """

    min_chars: int
    interval: int
    window: int
    ratio: float

    chars: int = 0
    last_clean_text: str = ""
    _chunks: list[str] = field(default_factory=list)
    _seen: list[str] = field(default_factory=list)
    _last_check: int = 0

    def accumulate(self, text: str) -> None:
        """Record one non-empty chunk of this channel."""
        self.chars += len(text)
        self._chunks.append(text)

    def check(self) -> bool:
        """Judge the accumulated text; return True on a degenerate repeat.

        Judgement is deferred until the stream is substantial (``min_chars``)
        and then repeated every ``interval`` characters. Each clean check
        records the accumulated text so a later halt can keep the last
        known-good content.
        """
        if self.chars < self.min_chars or self.chars - self._last_check < self.interval:
            return False
        self._last_check = self.chars
        window = _normalize_reasoning("".join(self._chunks)[-self.window :])
        if _is_repeat_window(window, self._seen, self.ratio):
            return True
        self._seen.append(window)
        self.last_clean_text = "".join(self._chunks)
        return False

    @property
    def text(self) -> str:
        """The full accumulated text of this channel."""
        return "".join(self._chunks)


@dataclass
class _StreamAccumulator:
    """Mutable state for one streamed chat response.

    Owns the reasoning-channel and content-channel repetition guards, the
    accumulated answer chunks, and the halt reason. ``consume`` processes a
    single streamed chunk in the original order (reasoning channel, then
    content channel with its answer-length bound before its loop check) and
    reports whether the stream must stop; ``resolve`` produces the final
    answer text once the stream has ended.
    """

    max_answer_chars: int
    reasoning: _RepeatGuard = field(
        default_factory=lambda: _RepeatGuard(
            min_chars=_REASON_LOOP_MIN_CHARS,
            interval=_REASON_LOOP_INTERVAL,
            window=_REASON_LOOP_WINDOW,
            ratio=_REASON_LOOP_RATIO,
        )
    )
    content: _RepeatGuard = field(
        default_factory=lambda: _RepeatGuard(
            min_chars=_CONTENT_LOOP_MIN_CHARS,
            interval=_CONTENT_LOOP_INTERVAL,
            window=_CONTENT_LOOP_WINDOW,
            ratio=_CONTENT_LOOP_RATIO,
        )
    )
    accumulated: list[str] = field(default_factory=list)
    capped: bool = False
    capped_reason: str = ""

    def consume(self, chunk: object, on_chunk: StreamingCallback) -> bool:
        """Absorb one streamed chunk; return True when the stream must stop.

        Forwards every non-empty channel to ``on_chunk`` exactly once, in the
        same order the chunks arrived, before any halt is reported.
        """
        if not (chunk.choices and len(chunk.choices) > 0):
            return False
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning is None:
            reasoning = getattr(delta, "reasoning", None)
        content = delta.content or ""
        if reasoning:
            self.reasoning.accumulate(reasoning)
            # Halt a genuine reasoning loop (near-exact repeated window).
            if self.reasoning.check():
                self.capped = True
                self.capped_reason = "degenerate loop"
                return True
        if content:
            self.content.accumulate(content)
            # Bound answer length regardless of repetition pattern: a
            # runaway generator emitting varied output is cut here too.
            if self.max_answer_chars and self.content.chars > self.max_answer_chars:
                self.capped = True
                self.capped_reason = "answer limit"
                return True
            # Halt a content-phase spiral (the model re-drafting and
            # self-correcting its prose in a loop), keeping the clean
            # summary accumulated before the spiral began.
            if self.content.check():
                self.capped = True
                self.capped_reason = "content loop"
                return True
        if content or reasoning:
            on_chunk(content, reasoning)
        if content:
            self.accumulated.append(content)
        return False

    def resolve(self) -> str:
        """Build the final answer text from the accumulated stream state."""
        if self.capped and self.capped_reason == "content loop":
            # Keep the clean summary accumulated before the spiral began.
            return self.content.last_clean_text
        if self.capped and self.capped_reason == "answer limit":
            prefix = "".join(self.accumulated)[: self.max_answer_chars]
            return _cut_at_sentence_boundary(prefix)
        return "".join(self.accumulated)


def _cut_at_sentence_boundary(prefix: str) -> str:
    """Cut a capped answer at its last sentence or line end.

    A capped answer must never stop mid-word; the cut falls back to the
    last space and then to the raw prefix when no boundary exists.
    """
    term = list(re.finditer(r"[.!?]\s|\n", prefix))
    cut = term[-1].end() if term else -1
    if cut <= 0:
        sp = prefix.rfind(" ")
        cut = sp if sp > 0 else -1
    return (prefix[:cut] if cut > 0 else prefix).rstrip()


class OpenAILLMProvider(LocalLLMProvider):
    """OpenAI implementation of LocalLLMProvider protocol.

    Uses the official OpenAI Python library for chat API interactions.
    Provides both sync and async generation methods with proper error handling.

    Attributes:
        model: Model name to use for generation.
        temperature: Default temperature for generation.
        max_tokens: Default max tokens for generation.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 1.0,
        max_tokens: int = 384000,
        timeout: int = 120,
        base_url: str | None = None,
        api_key: str | None = None,
        repetition_penalty: float = 1.0,
        reasoning_effort: str | None = None,
        top_p: float = 0.95,
        stream_idle_timeout_seconds: int = 0,
        max_answer_chars: int = 0,
    ) -> None:
        """Initialize OpenAI provider with configuration.

        Args:
            model: Model name to use (default: "gpt-4o-mini").
            temperature: Default temperature for generation (default: 1.0).
            max_tokens: Default max tokens for generation (default: 384000).
            timeout: Request timeout in seconds (default: 120).
            base_url: OpenAI-compatible API base URL (optional, defaults to OpenAI).
            api_key: OpenAI API key (defaults to SECONDBRAIN_OPENAI_API_KEY env var).
            repetition_penalty: Repetition penalty (>= 1.0). Values above 1.0 are
                forwarded as ``repetition_penalty`` to OpenAI-compatible servers
                that support it                 (DeepSeek, vLLM, TGI) to discourage the model from
                repeating itself (default: 1.0, disabled).
            reasoning_effort: Optional reasoning-effort hint for reasoning models,
                sent as ``reasoning_effort`` in the request body (LiteLLM maps it
                to the model's thinking controls; unsupported endpoints ignore or
                reject it). None omits the parameter (default).
            top_p: Nucleus-sampling top_p (0.0-1.0, default: 0.95).
            stream_idle_timeout_seconds: Maximum seconds with no token arriving
                before the stream is aborted, bounding a server that goes idle
                mid-output instead of hanging forever. 0 disables the bound.
            max_answer_chars: Bounded maximum length of the answer (content) text;
                a runaway generator is cut here and a clean prefix returned
                (0 disables the bound).

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._temperature = temperature
        self._top_p = top_p
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._base_url = base_url
        self._repetition_penalty = repetition_penalty
        self._reasoning_effort = reasoning_effort
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds
        self._max_answer_chars = max_answer_chars

        # Get API key from parameter or environment
        self._api_key = api_key or os.getenv("SECONDBRAIN_OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set SECONDBRAIN_OPENAI_API_KEY "
                "environment variable or provide api_key parameter"
            )

        # Initialize clients with TTFT-based timeout.
        # connect=timeout: connection must establish within `timeout` seconds.
        # read=idle:       seconds with no token before aborting an idle stream
        #                  (None = unlimited, i.e. the server cannot hang us forever).
        # write=timeout:   request body must be sent within `timeout` seconds.
        # pool=timeout:    connection pool acquisition timeout.
        read_timeout = (
            stream_idle_timeout_seconds if stream_idle_timeout_seconds > 0 else None
        )
        ttft_timeout = httpx2.Timeout(
            connect=timeout, read=read_timeout, write=timeout, pool=timeout
        )
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=base_url,  # Optional - None means use OpenAI default
            timeout=ttft_timeout,
        )
        self._async_client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=base_url,  # Optional - None means use OpenAI default
            timeout=ttft_timeout,
        )

    def _extra_body(self) -> dict[str, object] | None:
        """Extra request-body params for OpenAI-compatible endpoints.

        Includes ``repetition_penalty`` (DeepSeek/vLLM/TGI style) only when
        enabled (``!= 1.0``) and ``reasoning_effort`` only when configured,
        so the default request payload is unchanged. Sent via the SDK's
        ``extra_body`` because these are not native SDK arguments; proxies
        such as LiteLLM map them to per-model equivalents and servers that
        support neither ignore unknown fields.
        """
        extra: dict[str, object] = {}
        if self._repetition_penalty != 1.0:
            extra["repetition_penalty"] = self._repetition_penalty
        if self._reasoning_effort is not None:
            extra["reasoning_effort"] = self._reasoning_effort
        return extra or None

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response using OpenAI chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If OpenAI API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            messages = [{"role": "user", "content": prompt}]

            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
                extra_body=self._extra_body(),
            )

            _log_token_usage(
                "completion", getattr(response, "usage", None), self._model
            )
            return response.choices[0].message.content or ""

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                f"OpenAI API request timed out after {self._timeout}s: {e}"
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Generation failed: {e}") from e

    async def generate_async(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response asynchronously using OpenAI chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If OpenAI API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            messages = [{"role": "user", "content": prompt}]

            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = await self._async_client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
                extra_body=self._extra_body(),
            )

            _log_token_usage(
                "completion", getattr(response, "usage", None), self._model
            )
            return response.choices[0].message.content or ""

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                f"OpenAI API request timed out after {self._timeout}s: {e}"
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async generation failed: {e}") from e

    def health_check(self) -> bool:
        """Check if OpenAI API is accessible.

        Returns:
            True if API is accessible, False otherwise.
        """
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._model

    @property
    def temperature(self) -> float:
        """Get the default temperature."""
        return self._temperature

    @property
    def max_tokens(self) -> int:
        """Get the default max tokens."""
        return self._max_tokens

    @property
    def timeout(self) -> int:
        """Get the request timeout."""
        return self._timeout

    async def agenerate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response asynchronously using OpenAI chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If OpenAI API is unreachable.
            RuntimeError: If generation fails.
        """
        return await self.generate_async(prompt, temperature, max_tokens)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Stream response tokens in real time via the on_chunk callback.

        Uses ``stream=True`` so the HTTP response is consumed as a
        token-by-token iterator.  Each content delta is forwarded to
        ``on_chunk`` immediately, allowing the caller to update a
        spinner/progress indicator on the first token and display
        incremental output.
        """
        try:
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
                stream=True,
                extra_body=self._extra_body(),
            )

            state = _StreamAccumulator(max_answer_chars=self._max_answer_chars)
            stream_usage: object = None
            for chunk in response:
                # Some OpenAI-compatible servers append a usage-bearing final
                # chunk even without ``stream_options``; capture it when present
                # so streaming responses log token usage too.
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    stream_usage = chunk_usage
                if state.consume(chunk, on_chunk):
                    break

            answer = state.resolve()
            _log_token_usage("streaming completion", stream_usage, self._model)
            if state.capped:
                logger.warning(
                    "Stream halted (%s) reasoning=%s content=%s",
                    state.capped_reason,
                    state.reasoning.chars,
                    state.content.chars,
                )
                if not answer.strip():
                    answer = (
                        "I got stuck in repetitive reasoning and could not "
                        "produce an answer. Please rephrase or narrow your "
                        "question."
                    )
                    on_chunk(answer, None)
            return answer

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                f"OpenAI API request timed out after {self._timeout}s: {e}"
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Streaming failed: {e}") from e

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async streaming via on_chunk callback."""
        result = await self.generate_async(
            messages[-1]["content"] if messages else "",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        on_chunk(result, None)
        return result
