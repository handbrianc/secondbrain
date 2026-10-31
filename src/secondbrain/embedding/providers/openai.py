"""OpenAI embedding provider implementation for API-based embeddings.

Provides OpenAIEmbeddingProvider class that implements the EmbeddingProvider
protocol for using OpenAI API or OpenAI-compatible endpoints for embedding generation.
"""

from __future__ import annotations

# mypy: disable-error-code=attr-defined
# mypy: disable-error-code=arg-type
# mypy: disable-error-code=misc
#
# Rationale for disabled codes:
# - attr-defined : openai v1.x stub gaps — OpenAI, AsyncOpenAI, APIError not
#   exposed at top-level in static type index even though they work at runtime.
# - arg-type     : Dynamic dict kwargs passed as **kwargs to .create() exceed
#   what openai's overloaded TypedDict signatures can express (int vs str keys
#   in the union type cannot be matched precisely by mypy).
# - misc         : Class cannot subclass EmbeddingProvider (has type Any) — mypy
#   limitation when inheriting from a Protocol resolved through a relative import
#   inside a namespace package. The inheritance is sound at runtime.
import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from typing import Any, TypeVar

import httpx2
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)

from secondbrain.embedding.interfaces import EmbeddingProvider
from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.logging import timed_external_call
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)
from secondbrain.utils.rate_limiter import SharedRateLimiter
from secondbrain.utils.tracing import create_trace_propagation_hooks, trace_operation

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@contextmanager
def _traced_embedding_operation(operation: str, **attributes: Any) -> Generator[Any]:
    """Span for an embedding provider API operation.

    Emits an ``embedding_<operation>`` span carrying the attributes under the
    ``embedding.`` namespace (``embedding.text_length`` / ``embedding.dimensions``
    for single-text operations, ``embedding.batch_size`` for batch operations),
    so embedding latency and payload sizes are identifiable in traces. Extra
    *attributes* are stamped on the span when tracing is enabled; ``None``
    values are skipped.

    When tracing is disabled ``trace_operation`` yields ``None`` and the span
    degenerates to plain execution (zero overhead), mirroring the
    ``if span:`` pattern used in :mod:`secondbrain.storage.qdrant` and
    :mod:`secondbrain.search`.
    """
    with trace_operation(f"embedding.{operation}") as span:
        if span is not None:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(f"embedding.{key}", value)
        yield span


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API implementation of EmbeddingProvider protocol.

    Supports OpenAI embeddings API and any OpenAI-compatible endpoint
    (e.g., Azure OpenAI, local vLLM, custom embeddings API, etc.).

    Models supported:
    - text-embedding-ada-002 (1536 dimensions)
    - text-embedding-3-small (1536 dimensions, recommended)
    - text-embedding-3-large (3072 dimensions)

    Attributes:
        model: Model name to use for embeddings.
        api_key: OpenAI API key for authentication.
        api_base: Base URL for OpenAI-compatible API endpoints.
        timeout: Request timeout in seconds.
        dimensions: Output dimensions (only for text-embedding-3-* models).
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: int = 120,
        dimensions: int | None = None,
        rate_limiter: SharedRateLimiter | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize OpenAI embedding provider.

        Args:
            model: Model name (default: text-embedding-3-small).
            api_key: API key (defaults to SECONDBRAIN_EMBEDDING_API_KEY env var).
            api_base: Base URL for OpenAI-compatible API (optional).
            timeout: Request timeout in seconds (default: 120).
            dimensions: Output dimensions (only for text-embedding-3-* models).
            rate_limiter: Shared rate limiter whose slot is acquired before
                each embeddings API call (waits, queueing requests, until a
                slot frees). None disables rate limiting (default).
            circuit_breaker_config: Circuit breaker protecting the
                embeddings API paths (generation and connection
                validation). While the circuit is OPEN, generation fails
                fast with ServiceUnavailableError without an API call.
                None disables it (default); ``EmbeddingProviderFactory``
                passes one built from config.

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._timeout = timeout
        self._dimensions = dimensions
        self._rate_limiter = rate_limiter
        # Circuit breaker for the embeddings API paths (mirrors the
        # ValidatableService wiring): None → disabled, no behavior change.
        self._circuit_breaker_enabled = circuit_breaker_config is not None
        self._circuit_breaker: CircuitBreaker | None = None
        if self._circuit_breaker_enabled and circuit_breaker_config is not None:
            self._circuit_breaker = CircuitBreaker(
                config=circuit_breaker_config,
                service_name=self.__class__.__name__,
            )

        # Get API key from parameter or environment (truly optional for OpenAI-compatible APIs)
        self._api_key = api_key or os.getenv("SECONDBRAIN_EMBEDDING_API_KEY")

        client_kwargs: dict[str, Any] = {
            "timeout": httpx2.Timeout(timeout),
        }
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        else:
            # Provide a sentinel for the OpenAI client credential check.
            # This is not a real credential - it's a placeholder for
            # local-only configurations that don't need auth.
            # Sentinel for local-only / no-auth API configurations.
            # This is NOT a real credential — it satisfies the OpenAI SDK
            # client check for environments that don't require auth.
            client_kwargs["api_key"] = (
                os.environ.get("SECONDBRAIN_EMBEDDING_API_KEY", "")
                or "no-auth-placeholder"
            )
        if api_base:
            client_kwargs["base_url"] = api_base
            client_kwargs["default_query"] = {"drop_params": "true"}

        # Propagate trace context to the embedding API when tracing is on.
        # httpx invokes sync request hooks on the sync client and awaits async
        # hooks on the async client, so each flavour gets its own client.
        # None (tracing disabled) leaves the clients built exactly as before.
        hooks = create_trace_propagation_hooks()
        async_client_kwargs: dict[str, Any] = dict(client_kwargs)
        if hooks is not None:
            client_kwargs["http_client"] = httpx2.Client(
                event_hooks=hooks["sync"], timeout=httpx2.Timeout(timeout)
            )
            async_client_kwargs["http_client"] = httpx2.AsyncClient(
                event_hooks=hooks["async"], timeout=httpx2.Timeout(timeout)
            )

        self._client = OpenAI(**client_kwargs)
        self._async_client = AsyncOpenAI(**async_client_kwargs)

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text using OpenAI API.

        When a circuit breaker is configured, the API call runs through it
        (inside the emitted span): failures are recorded against the
        breaker, and while the circuit is OPEN the call is skipped — no API
        request — and ServiceUnavailableError is raised, matching the
        provider-unreachable failures callers already handle.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ServiceUnavailableError: If API is unreachable, the request
                times out, the API errors, or the wired circuit breaker is
                open (fail-fast, no request attempted).
            RuntimeError: If embedding generation fails.
        """
        try:
            if self._rate_limiter is not None:
                self._rate_limiter.wait_and_acquire()
            kwargs: dict[str, str | list[str] | int] = {
                "input": text,
                "model": self._model,
            }
            # Only pass dimensions for models that support it (text-embedding-3-* series)
            # Custom models via LiteLLM may not support this parameter
            if self._dimensions and self._model.startswith("text-embedding-3-"):
                kwargs["dimensions"] = self._dimensions

            with _traced_embedding_operation("generate", text_length=len(text)) as span:
                with timed_external_call("embedding.generate", self._model):
                    response = self._call_through_breaker(
                        lambda: self._client.embeddings.create(**kwargs)
                    )
                embedding: list[float] = response.data[0].embedding
                if span is not None:
                    span.set_attribute("embedding.dimensions", len(embedding))
                return embedding

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s",
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(
                "Embedding", "OpenAI embeddings API unreachable"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}",
            ) from e
        except CircuitBreakerError as e:
            # Fail-fast while the circuit is open: no API call was made, but
            # the surface must match the provider-unavailable failures the
            # search/chat callers already handle, not a breaker-specific type.
            raise ServiceUnavailableError(
                "Embedding", f"Embedding API call skipped, circuit breaker open: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts using OpenAI API.

        OpenAI API supports batch requests (up to 2048 inputs for text-embedding-3-small).

        When a circuit breaker is configured, the API call runs through it
        (inside the emitted span): failures are recorded against the
        breaker, and while the circuit is OPEN the call is skipped — no API
        request — and ServiceUnavailableError is raised.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.

        Raises:
            ServiceUnavailableError: If API is unreachable, the request
                times out, the API errors, or the wired circuit breaker is
                open (fail-fast, no request attempted).
            RuntimeError: If embedding generation fails.
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        try:
            if self._rate_limiter is not None:
                self._rate_limiter.wait_and_acquire()
            kwargs: dict[str, str | list[str] | int] = {
                "input": valid_texts,
                "model": self._model,
            }
            # Only pass dimensions for models that support it (text-embedding-3-* series)
            # Custom models via LiteLLM may not support this parameter
            if self._dimensions and self._model.startswith("text-embedding-3-"):
                kwargs["dimensions"] = self._dimensions

            with _traced_embedding_operation(
                "generate_batch", batch_size=len(valid_texts)
            ) as span:
                with timed_external_call("embedding.generate_batch", self._model):
                    response = self._call_through_breaker(
                        lambda: self._client.embeddings.create(**kwargs)
                    )

                # Sort by index to maintain input order (API may return in any order)
                embeddings_sorted = sorted(response.data, key=lambda x: x.index)
                embeddings = [emb.embedding for emb in embeddings_sorted]
                if span is not None and embeddings:
                    span.set_attribute("embedding.dimensions", len(embeddings[0]))
                return embeddings

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s",
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(
                "Embedding", "OpenAI embeddings API unreachable"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}",
            ) from e
        except CircuitBreakerError as e:
            raise ServiceUnavailableError(
                "Embedding", f"Embedding API call skipped, circuit breaker open: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Batch embedding generation failed: {e}") from e

    async def generate_async(self, text: str) -> list[float]:
        """Async version of generate.

        When a circuit breaker is configured, the awaited API call runs
        through it (inside the emitted span) with the same gate-and-record
        contract as the sync path: failures are recorded, and while the
        circuit is OPEN the coroutine is never created — no API request —
        and ServiceUnavailableError is raised.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ServiceUnavailableError: If API is unreachable, the request
                times out, the API errors, or the wired circuit breaker is
                open (fail-fast, no request attempted).
            RuntimeError: If embedding generation fails.
        """
        try:
            if self._rate_limiter is not None:
                # Wait off the event loop so a full window doesn't block it.
                await asyncio.to_thread(self._rate_limiter.wait_and_acquire)
            kwargs: dict[str, str | list[str] | int] = {
                "input": text,
                "model": self._model,
            }
            # Only pass dimensions for models that support it (text-embedding-3-* series)
            # Custom models via LiteLLM may not support this parameter
            if self._dimensions and self._model.startswith("text-embedding-3-"):
                kwargs["dimensions"] = self._dimensions

            with _traced_embedding_operation(
                "generate_async", text_length=len(text)
            ) as span:
                with timed_external_call("embedding.generate_async", self._model):
                    response = await self._call_through_breaker_async(
                        lambda: self._async_client.embeddings.create(**kwargs)
                    )
                embedding: list[float] = response.data[0].embedding
                if span is not None:
                    span.set_attribute("embedding.dimensions", len(embedding))
                return embedding

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s",
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(
                "Embedding", "OpenAI embeddings API unreachable"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}",
            ) from e
        except CircuitBreakerError as e:
            raise ServiceUnavailableError(
                "Embedding", f"Embedding API call skipped, circuit breaker open: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Async embedding generation failed: {e}") from e

    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Async version of generate_batch.

        When a circuit breaker is configured, the awaited API call runs
        through it (inside the emitted span) with the same gate-and-record
        contract as the sync path: failures are recorded, and while the
        circuit is OPEN the coroutine is never created — no API request —
        and ServiceUnavailableError is raised.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.

        Raises:
            ServiceUnavailableError: If API is unreachable, the request
                times out, the API errors, or the wired circuit breaker is
                open (fail-fast, no request attempted).
            RuntimeError: If embedding generation fails.
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        try:
            if self._rate_limiter is not None:
                # Wait off the event loop so a full window doesn't block it.
                await asyncio.to_thread(self._rate_limiter.wait_and_acquire)
            kwargs: dict[str, str | list[str] | int] = {
                "input": valid_texts,
                "model": self._model,
            }
            # Only pass dimensions for models that support it (text-embedding-3-* series)
            # Custom models via LiteLLM may not support this parameter
            if self._dimensions and self._model.startswith("text-embedding-3-"):
                kwargs["dimensions"] = self._dimensions

            with _traced_embedding_operation(
                "generate_batch_async", batch_size=len(valid_texts)
            ) as span:
                with timed_external_call("embedding.generate_batch_async", self._model):
                    response = await self._call_through_breaker_async(
                        lambda: self._async_client.embeddings.create(**kwargs)
                    )
                embeddings_sorted = sorted(response.data, key=lambda x: x.index)
                embeddings = [emb.embedding for emb in embeddings_sorted]
                if span is not None and embeddings:
                    span.set_attribute("embedding.dimensions", len(embeddings[0]))
                return embeddings

        except APITimeoutError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s",
            ) from e
        except APIConnectionError as e:
            raise ServiceUnavailableError(
                "Embedding", "OpenAI embeddings API unreachable"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}",
            ) from e
        except CircuitBreakerError as e:
            raise ServiceUnavailableError(
                "Embedding", f"Embedding API call skipped, circuit breaker open: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Async batch embedding generation failed: {e}") from e

    def _call_through_breaker(self, func: Callable[[], _T]) -> _T:
        """Run one embeddings API call through the wired circuit breaker.

        The disabled path (no breaker configured) is a plain passthrough —
        no breaker object is consulted, so behavior is exactly as before
        the breaker existed. Otherwise the call is gated by
        ``CircuitBreaker.call``: a raised or failed call is recorded
        against the breaker, so repeated failures open the circuit, and
        while the circuit is OPEN the call is skipped entirely — no API
        request — with ``CircuitBreakerError`` raised for the caller to
        map.

        Args:
            func: Zero-argument callable performing the API call.

        Returns:
            Whatever *func* returned, on success.

        Raises:
            CircuitBreakerError: If the circuit is open (fail-fast, no
                API call attempted).
        """
        breaker = self._circuit_breaker
        if breaker is None:
            return func()
        holder: list[_T] = []

        def _recorded() -> bool:
            holder.append(func())
            return True

        breaker.call(_recorded)
        return holder[0]

    async def _call_through_breaker_async(
        self, func: Callable[[], Awaitable[_T]]
    ) -> _T:
        """Await one embeddings API call through the wired circuit breaker.

        Async mirror of :meth:`_call_through_breaker`.
        ``CircuitBreaker.call`` only accepts synchronous callables, so the
        identical gate-and-record contract is applied here against the
        breaker's own primitives: ``CircuitBreakerError`` when the circuit
        is open (no API call, and the coroutine from *func* is never even
        created), ``record_failure`` if the awaited call raises,
        ``record_success`` otherwise — the same transitions ``call()``
        performs for the sync path.

        Args:
            func: Zero-argument callable returning the awaitable API call.

        Returns:
            The awaited result of *func*, on success.

        Raises:
            CircuitBreakerError: If the circuit is open (fail-fast, no
                API call attempted).
        """
        breaker = self._circuit_breaker
        if breaker is None:
            return await func()
        if not breaker.is_allowed():
            raise CircuitBreakerError(
                "Circuit breaker is open, request not allowed",
                service_name=breaker.service_name,
            )
        try:
            result = await func()
        except Exception:
            breaker.record_failure()
            raise
        breaker.record_success()
        return result

    def validate_connection(
        self, force: bool = False, bypass_circuit_breaker: bool = False
    ) -> bool:
        """Check if OpenAI API is accessible.

        When a circuit breaker is configured, the raw probe runs through it
        (``CircuitBreaker.call``): while the circuit is OPEN the API call is
        skipped entirely and the method degrades gracefully to ``False`` —
        the same unavailable signal the bool contract already produces —
        without touching the network.

        With ``bypass_circuit_breaker=True`` (startup-wait probes) the raw
        probe runs directly and the breaker is neither consulted nor updated
        — success or failure — so transient startup failures cannot open the
        circuit.

        Args:
            force: Accepted for protocol compatibility; the probe is
                uncached, so it always runs.
            bypass_circuit_breaker: Run the probe without consulting or
                updating the circuit breaker.

        Returns:
            True if API is accessible, False otherwise.
        """
        if self._circuit_breaker is None or bypass_circuit_breaker:
            return self._probe_api()
        try:
            return bool(self._circuit_breaker.call(self._probe_api))
        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker open for %s; skipping embedding API probe",
                self.__class__.__name__,
            )
            return False

    def _probe_api(self) -> bool:
        """One raw OpenAI API reachability probe (no circuit breaker).

        Returns
        -------
            True if the API answered ``models.list()`` (or no client is
            configured, preserving the original trust-on-missing behavior).
        """
        try:
            # Make a minimal request to check connectivity
            if self._client is not None:
                self._client.models.list()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close clients and release resources.

        Note: For proper async cleanup in async context, use aclose() instead.
        This method closes the sync httpx2 client but does not close the async
        client — the async client must be closed with aclose() to avoid
        RuntimeWarnings from unawaited coroutines.
        """
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None

    async def aclose(self) -> None:
        """Asynchronously close both sync and async HTTP clients.

        Releases all held resources including async connection pools to prevent
        resource leaks and RuntimeWarnings from unawaited coroutines.
        """
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
        self._api_key = None
