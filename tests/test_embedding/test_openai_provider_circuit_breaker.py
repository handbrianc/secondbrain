"""Circuit-breaker tests for ``OpenAIEmbeddingProvider`` generation paths.

The provider's wired breaker (from resilience config via
``EmbeddingProviderFactory``) must protect all four generation methods:
repeated failures are recorded, the threshold opens the circuit, and while
the circuit is OPEN generation fails fast with ServiceUnavailableError
without any API call. The ``embedding.*`` spans are still emitted regardless
of breaker state (the breaker wraps the API call inside the span). With no
breaker configured (disabled path) nothing changes: every call reaches the
API.

All OpenAI SDK clients are patched at the provider module, so no test ever
touches the network.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import secondbrain.embedding.providers.openai as openai_mod
import secondbrain.utils.tracing as tracing_module
from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.utils.circuit_breaker import CircuitBreakerConfig, CircuitState

_THRESHOLD = 2
_RECOVERY_TIMEOUT = 30.0


def _response(items: list[tuple[int, list[float]]]) -> MagicMock:
    """Fake embeddings response: list of (index, embedding) pairs."""
    response = MagicMock()
    data = []
    for index, embedding in items:
        item = MagicMock()
        item.index = index
        item.embedding = embedding
        data.append(item)
    response.data = data
    return response


def _unreachable() -> APIConnectionError:
    """Fresh connection error, as the SDK would raise on a dead endpoint."""
    return APIConnectionError(request=MagicMock())


def _make_provider(**overrides: Any) -> tuple[Any, MagicMock, MagicMock]:
    """Build OpenAIEmbeddingProvider with mocked OpenAI/AsyncOpenAI clients.

    Returns (provider, sync_client, async_client); both clients are MagicMocks.
    """
    kwargs: dict[str, Any] = {
        "model": "m",
        "api_key": "sk-test",
        "timeout": 30,
        "dimensions": None,
    }
    kwargs.update(overrides)
    with (
        patch("secondbrain.embedding.providers.openai.OpenAI") as mock_openai,
        patch("secondbrain.embedding.providers.openai.AsyncOpenAI") as mock_async,
    ):
        provider = openai_mod.OpenAIEmbeddingProvider(**kwargs)
        sync_client = mock_openai.return_value
        async_client = mock_async.return_value
    return provider, sync_client, async_client


def _make_breaker_provider(**overrides: Any) -> tuple[Any, MagicMock, MagicMock]:
    """Provider wired with a small breaker: threshold 2, 30s recovery."""
    return _make_provider(
        circuit_breaker_config=CircuitBreakerConfig(
            failure_threshold=_THRESHOLD,
            success_threshold=1,
            recovery_timeout=_RECOVERY_TIMEOUT,
        ),
        **overrides,
    )


class _FakeMonotonic:
    """Controllable ``time.monotonic`` replacement (CircuitBreaker's clock)."""

    def __init__(self) -> None:
        self._now = time.monotonic()

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward."""
        self._now += seconds

    def __call__(self) -> float:
        """Return the current fake time."""
        return self._now


@pytest.fixture
def breaker_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeMonotonic:
    """Pin the circuit breaker's time source to a controllable fake clock."""
    clock = _FakeMonotonic()
    monkeypatch.setattr(time, "monotonic", clock)
    return clock


def setup_span_capture(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Route trace_operation spans into an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(tracing_module, "OTTEL_AVAILABLE", True)
    monkeypatch.setattr(tracing_module, "get_tracer", lambda: tracer)
    monkeypatch.setattr(tracing_module, "is_tracing_enabled", lambda: True)
    return exporter


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, list[Any]]:
    spans: dict[str, list[Any]] = {}
    for span in exporter.get_finished_spans():
        spans.setdefault(span.name, []).append(span)
    return spans


def _open_circuit(provider: Any, api_mock: Any, attempts: int) -> None:
    """Record *attempts* sync failures so the threshold opens the circuit."""
    api_mock.side_effect = _unreachable()
    for _ in range(attempts):
        with pytest.raises(ServiceUnavailableError):
            provider.generate("hello")


async def _open_circuit_async(provider: Any, api_mock: Any, attempts: int) -> None:
    """Record *attempts* async failures so the threshold opens the circuit."""
    api_mock.side_effect = _unreachable()
    for _ in range(attempts):
        with pytest.raises(ServiceUnavailableError):
            await provider.generate_async("hello")


class TestBreakerOpensOnThreshold:
    def test_threshold_failures_open_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """Consecutive API failures are recorded; the threshold trips OPEN."""
        provider, sync_client, _ = _make_breaker_provider()
        sync_client.embeddings.create.side_effect = _unreachable()

        for _ in range(_THRESHOLD):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                provider.generate("hello")

        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN
        assert sync_client.embeddings.create.call_count == _THRESHOLD

    def test_batch_threshold_failures_open_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """generate_batch failures feed the same breaker."""
        provider, sync_client, _ = _make_breaker_provider()
        sync_client.embeddings.create.side_effect = _unreachable()

        for _ in range(_THRESHOLD):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                provider.generate_batch(["a", "b"])

        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN

    async def test_async_threshold_failures_open_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """generate_async failures feed the same breaker."""
        provider, _, async_client = _make_breaker_provider()
        async_client.embeddings.create = AsyncMock(side_effect=_unreachable())

        for _ in range(_THRESHOLD):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                await provider.generate_async("hello")

        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN
        assert async_client.embeddings.create.call_count == _THRESHOLD

    async def test_async_batch_threshold_failures_open_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """generate_batch_async failures feed the same breaker."""
        provider, _, async_client = _make_breaker_provider()
        async_client.embeddings.create = AsyncMock(side_effect=_unreachable())

        for _ in range(_THRESHOLD):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                await provider.generate_batch_async(["a", "b"])

        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN


class TestOpenCircuitFailsFast:
    def test_open_circuit_skips_api_call(self, breaker_clock: _FakeMonotonic) -> None:
        """While OPEN, generate fails without any API call."""
        provider, sync_client, _ = _make_breaker_provider()
        _open_circuit(provider, sync_client.embeddings.create, _THRESHOLD)
        calls_before = sync_client.embeddings.create.call_count

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            provider.generate("hello")

        assert sync_client.embeddings.create.call_count == calls_before

    def test_open_circuit_skips_batch_api_call(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """While OPEN, generate_batch fails without any API call."""
        provider, sync_client, _ = _make_breaker_provider()
        _open_circuit(provider, sync_client.embeddings.create, _THRESHOLD)
        calls_before = sync_client.embeddings.create.call_count

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            provider.generate_batch(["a", "b"])

        assert sync_client.embeddings.create.call_count == calls_before

    async def test_open_circuit_skips_async_api_call(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """While OPEN, generate_async fails without ever creating the call."""
        provider, _, async_client = _make_breaker_provider()
        await _open_circuit_async(provider, async_client.embeddings.create, _THRESHOLD)
        calls_before = async_client.embeddings.create.call_count

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            await provider.generate_async("hello")

        assert async_client.embeddings.create.call_count == calls_before

    async def test_open_circuit_skips_async_batch_api_call(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """While OPEN, generate_batch_async fails without any API call."""
        provider, _, async_client = _make_breaker_provider()
        await _open_circuit_async(provider, async_client.embeddings.create, _THRESHOLD)
        calls_before = async_client.embeddings.create.call_count

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            await provider.generate_batch_async(["a", "b"])

        assert async_client.embeddings.create.call_count == calls_before


class TestRecoveryClosesCircuit:
    def test_success_after_recovery_closes_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """After the recovery timeout a probe succeeds and CLOSEs the circuit."""
        provider, sync_client, _ = _make_breaker_provider()
        _open_circuit(provider, sync_client.embeddings.create, _THRESHOLD)
        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN

        breaker_clock.advance(_RECOVERY_TIMEOUT + 1.0)
        assert breaker.state is CircuitState.HALF_OPEN

        sync_client.embeddings.create.side_effect = None
        sync_client.embeddings.create.return_value = _response([(0, [0.1, 0.2])])

        assert provider.generate("hello") == [0.1, 0.2]
        assert breaker.state is CircuitState.CLOSED

    async def test_async_success_after_recovery_closes_circuit(
        self, breaker_clock: _FakeMonotonic
    ) -> None:
        """The async path recovers through the same state machine."""
        provider, _, async_client = _make_breaker_provider()
        await _open_circuit_async(provider, async_client.embeddings.create, _THRESHOLD)
        breaker = provider._circuit_breaker
        assert breaker is not None
        assert breaker.state is CircuitState.OPEN

        breaker_clock.advance(_RECOVERY_TIMEOUT + 1.0)
        assert breaker.state is CircuitState.HALF_OPEN

        async_client.embeddings.create = AsyncMock(return_value=_response([(0, [0.3])]))

        assert await provider.generate_async("hello") == [0.3]
        assert breaker.state is CircuitState.CLOSED


class TestDisabledBreakerPath:
    def test_no_config_keeps_unwrapped_behavior(self) -> None:
        """Without a breaker config every call reaches the API, no fail-fast."""
        provider, sync_client, _ = _make_provider()
        assert provider._circuit_breaker is None
        sync_client.embeddings.create.side_effect = _unreachable()

        for _ in range(10):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                provider.generate("hello")

        assert sync_client.embeddings.create.call_count == 10

    async def test_no_config_async_unwrapped(self) -> None:
        """The async disabled path also always reaches the API."""
        provider, _, async_client = _make_provider()
        assert provider._circuit_breaker is None
        async_client.embeddings.create = AsyncMock(side_effect=_unreachable())

        for _ in range(10):
            with pytest.raises(ServiceUnavailableError, match="unreachable"):
                await provider.generate_async("hello")

        assert async_client.embeddings.create.call_count == 10


class TestSpansWithBreaker:
    def test_success_span_emitted_with_breaker_enabled(
        self, monkeypatch: pytest.MonkeyPatch, breaker_clock: _FakeMonotonic
    ) -> None:
        """With a wired breaker, success still emits the usual span."""
        exporter = setup_span_capture(monkeypatch)
        provider, sync_client, _ = _make_breaker_provider()
        sync_client.embeddings.create.return_value = _response([(0, [0.1, 0.2])])

        assert provider.generate("hello") == [0.1, 0.2]

        span = _spans_by_name(exporter)["embedding.generate"][0]
        assert span.attributes["embedding.dimensions"] == 2

    def test_span_emitted_and_marked_error_when_open(
        self, monkeypatch: pytest.MonkeyPatch, breaker_clock: _FakeMonotonic
    ) -> None:
        """Fail-fast while OPEN still emits an error-marked span.

        The span records the raw in-span failure (``CircuitBreakerError``);
        the ServiceUnavailableError mapping happens at the method boundary,
        after the span has closed — mirroring how the API-error spans record
        the raw openai exceptions.
        """
        exporter = setup_span_capture(monkeypatch)
        provider, sync_client, _ = _make_breaker_provider()
        _open_circuit(provider, sync_client.embeddings.create, _THRESHOLD)

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            provider.generate("hello")

        span = _spans_by_name(exporter)["embedding.generate"][-1]
        assert span.status.status_code == StatusCode.ERROR
        exception_events = [
            event
            for event in span.events
            if "CircuitBreakerError" in str(event.attributes)
        ]
        assert exception_events

    async def test_async_span_emitted_and_marked_error_when_open(
        self, monkeypatch: pytest.MonkeyPatch, breaker_clock: _FakeMonotonic
    ) -> None:
        """The async fail-fast path also keeps emitting the span."""
        exporter = setup_span_capture(monkeypatch)
        provider, _, async_client = _make_breaker_provider()
        await _open_circuit_async(provider, async_client.embeddings.create, _THRESHOLD)

        with pytest.raises(ServiceUnavailableError, match="circuit breaker open"):
            await provider.generate_async("hello")

        span = _spans_by_name(exporter)["embedding.generate_async"][-1]
        assert span.status.status_code == StatusCode.ERROR
        exception_events = [
            event
            for event in span.events
            if "CircuitBreakerError" in str(event.attributes)
        ]
        assert exception_events
