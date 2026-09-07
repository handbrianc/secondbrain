"""OpenAI LLM provider implementation for RAG pipeline.

Provides OpenAILLMProvider class that implements the LocalLLMProvider protocol
for using OpenAI API as an LLM backend.
"""

# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=arg-type
# mypy: disable-error-code=union-attr
# (openai package stubs don't explicitly export APIError/AsyncOpenAI/OpenAI;
#  arg-type suppressed for list[dict[str,str]] vs ChatCompletionMessageParam unions;
#  union-attr from the create() overload return union when streaming with top_p)

import logging
import os
import re
from difflib import SequenceMatcher

import httpx
from openai import APIError, AsyncOpenAI, OpenAI

from secondbrain.exceptions import ServiceUnavailableError

from ..interfaces import LocalLLMProvider, StreamingCallback

logger = logging.getLogger(__name__)

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
        ttft_timeout = httpx.Timeout(
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

            return response.choices[0].message.content or ""

        except httpx.ConnectError as e:
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

            return response.choices[0].message.content or ""

        except httpx.ConnectError as e:
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

            accumulated: list[str] = []
            reasoning_chars = 0
            reasoning_log: list[str] = []
            seen_windows: list[str] = []
            last_loop_check = 0
            content_chars = 0
            content_log: list[str] = []
            content_seen_windows: list[str] = []
            last_content_check = 0
            good_content = ""
            capped = False
            capped_reason = ""
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning is None:
                        reasoning = getattr(delta, "reasoning", None)
                    content = delta.content or ""
                    if reasoning:
                        reasoning_chars += len(reasoning)
                        reasoning_log.append(reasoning)
                        # Halt a genuine reasoning loop (near-exact repeated window).
                        if (
                            reasoning_chars >= _REASON_LOOP_MIN_CHARS
                            and reasoning_chars - last_loop_check
                            >= _REASON_LOOP_INTERVAL
                        ):
                            last_loop_check = reasoning_chars
                            window = _normalize_reasoning(
                                "".join(reasoning_log)[-_REASON_LOOP_WINDOW:]
                            )
                            if _is_repeat_window(
                                window, seen_windows, _REASON_LOOP_RATIO
                            ):
                                capped = True
                                capped_reason = "degenerate loop"
                                break
                            seen_windows.append(window)
                    if content:
                        content_chars += len(content)
                        content_log.append(content)
                        # Bound answer length regardless of repetition pattern: a
                        # runaway generator emitting varied output is cut here too.
                        if (
                            self._max_answer_chars
                            and content_chars > self._max_answer_chars
                        ):
                            capped = True
                            capped_reason = "answer limit"
                            break
                        # Halt a content-phase spiral (the model re-drafting and
                        # self-correcting its prose in a loop), keeping the clean
                        # summary accumulated before the spiral began.
                        if (
                            content_chars >= _CONTENT_LOOP_MIN_CHARS
                            and content_chars - last_content_check
                            >= _CONTENT_LOOP_INTERVAL
                        ):
                            last_content_check = content_chars
                            window = _normalize_reasoning(
                                "".join(content_log)[-_CONTENT_LOOP_WINDOW:]
                            )
                            if _is_repeat_window(
                                window, content_seen_windows, _CONTENT_LOOP_RATIO
                            ):
                                capped = True
                                capped_reason = "content loop"
                                break
                            content_seen_windows.append(window)
                            good_content = "".join(content_log)
                    if content or reasoning:
                        on_chunk(content, reasoning)
                    if content:
                        accumulated.append(content)

            if capped and capped_reason == "content loop":
                answer = good_content
            elif capped and capped_reason == "answer limit":
                full = "".join(accumulated)
                prefix = full[: self._max_answer_chars]
                # Cut at the last sentence/line end so a capped answer never stops
                # mid-word; fall back to the last space, then to the raw prefix.
                term = list(re.finditer(r"[.!?]\s|\n", prefix))
                cut = term[-1].end() if term else -1
                if cut <= 0:
                    sp = prefix.rfind(" ")
                    cut = sp if sp > 0 else -1
                answer = (prefix[:cut] if cut > 0 else prefix).rstrip()
            else:
                answer = "".join(accumulated)
            if capped:
                logger.warning(
                    "Stream halted (%s) reasoning=%s content=%s",
                    capped_reason,
                    reasoning_chars,
                    content_chars,
                )
                if not answer.strip():
                    answer = (
                        "I got stuck in repetitive reasoning and could not "
                        "produce an answer. Please rephrase or narrow your "
                        "question."
                    )
                    on_chunk(answer, None)
            return answer

        except httpx.ConnectError as e:
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
