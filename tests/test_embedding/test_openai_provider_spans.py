"""Span tests for ``OpenAIEmbeddingProvider`` (opentelemetry-integration spec).

The spec requires an ``embedding.generate`` span carrying the text length and
the embedding dimensions. Routes ``trace_operation`` spans into an
``InMemorySpanExporter`` (same pattern as
``tests/test_storage/test_qdrant_spans.py``) and asserts on spans emitted by
the real provider methods, with the OpenAI SDK clients mocked so no test
touches the network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import secondbrain.embedding.providers.openai as openai_mod
import secondbrain.utils.tracing as tracing_module


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


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, list[Any]]:
    spans: dict[str, list[Any]] = {}
    for span in exporter.get_finished_spans():
        spans.setdefault(span.name, []).append(span)
    return spans


class TestSyncEmbeddingSpans:
    def test_generate_emits_span_with_text_length_and_dimensions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.return_value = _response([(0, [0.1, 0.2, 0.3])])

        embedding = provider.generate("hello world")

        assert embedding == [0.1, 0.2, 0.3]
        spans = _spans_by_name(exporter)
        span = spans["embedding.generate"][0]
        assert span.attributes["embedding.text_length"] == len("hello world")
        assert span.attributes["embedding.dimensions"] == 3

    def test_generate_batch_emits_span_with_batch_size_and_dimensions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.return_value = _response(
            [(1, [0.2, 0.3, 0.4]), (0, [0.1, 0.2, 0.3])]
        )

        embeddings = provider.generate_batch(["hello", "world", "   "])

        # The blank text is filtered out before the API call.
        assert embeddings == [[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]]
        spans = _spans_by_name(exporter)
        span = spans["embedding.generate_batch"][0]
        assert span.attributes["embedding.batch_size"] == 2
        assert span.attributes["embedding.dimensions"] == 3

    def test_generate_span_records_error_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = ValueError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            provider.generate("hello")

        span = _spans_by_name(exporter)["embedding.generate"][0]
        assert span.status.status_code == StatusCode.ERROR
        exception_events = [
            event for event in span.events if "ValueError" in str(event.attributes)
        ]
        assert exception_events


class TestAsyncEmbeddingSpans:
    async def test_generate_async_emits_span_with_text_length_and_dimensions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(
            return_value=_response([(0, [0.4, 0.5])])
        )

        embedding = await provider.generate_async("async hello")

        assert embedding == [0.4, 0.5]
        spans = _spans_by_name(exporter)
        span = spans["embedding.generate_async"][0]
        assert span.attributes["embedding.text_length"] == len("async hello")
        assert span.attributes["embedding.dimensions"] == 2

    async def test_generate_batch_async_emits_span_with_batch_size_and_dimensions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(
            return_value=_response([(1, [0.7, 0.8]), (0, [0.5, 0.6])])
        )

        embeddings = await provider.generate_batch_async(["alpha", "beta"])

        assert embeddings == [[0.5, 0.6], [0.7, 0.8]]
        spans = _spans_by_name(exporter)
        span = spans["embedding.generate_batch_async"][0]
        assert span.attributes["embedding.batch_size"] == 2
        assert span.attributes["embedding.dimensions"] == 2

    async def test_generate_async_span_records_error_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(side_effect=ValueError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await provider.generate_async("hello")

        span = _spans_by_name(exporter)["embedding.generate_async"][0]
        assert span.status.status_code == StatusCode.ERROR
        exception_events = [
            event for event in span.events if "ValueError" in str(event.attributes)
        ]
        assert exception_events


class TestEmbeddingSpansDisabled:
    async def test_no_spans_when_tracing_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tracing disabled: provider works with zero span overhead."""
        exporter = InMemorySpanExporter()
        provider_obj = TracerProvider()
        provider_obj.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider_obj.get_tracer("test")
        monkeypatch.setattr(tracing_module, "OTTEL_AVAILABLE", True)
        monkeypatch.setattr(tracing_module, "get_tracer", lambda: tracer)
        monkeypatch.setattr(tracing_module, "is_tracing_enabled", lambda: False)

        provider, sync_client, async_client = _make_provider()
        sync_client.embeddings.create.return_value = _response([(0, [0.1])])
        async_client.embeddings.create = AsyncMock(return_value=_response([(0, [0.2])]))

        assert provider.generate("hello") == [0.1]
        assert await provider.generate_async("hello") == [0.2]
        assert not exporter.get_finished_spans()
