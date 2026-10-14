"""Real-code-path span tests for ``Searcher`` search spans.

The opentelemetry-integration spec requires ``search_generate_embedding`` to
carry the query length and ``search_storage`` to carry ``top_k``. Routes
``trace_operation`` spans into an ``InMemorySpanExporter`` (same pattern as
``tests/test_storage/test_qdrant_spans.py``) and asserts on spans emitted by
the real ``Searcher.search`` / ``Searcher.search_async`` code paths, with the
embedding provider and vector storage mocked so no test touches the network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import secondbrain.utils.tracing as tracing_module
from secondbrain.search import Searcher
from secondbrain.types import SearchResult

EMBEDDING_DIM = 8
QUERY = "hello world"


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


def _make_searcher() -> tuple[Searcher, MagicMock, MagicMock]:
    """Build a Searcher with mocked embedding provider and vector storage.

    The embedding provider stubs both the sync and the native-async generate
    methods so the async test exercises the real ``generate_async`` branch.
    """
    embedding_gen = MagicMock()
    embedding_gen.generate.return_value = [0.1] * EMBEDDING_DIM
    embedding_gen.generate_async = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)

    storage = MagicMock()
    storage.validate_connection.return_value = True
    storage.search.return_value = [_search_result("c1")]
    storage.search_async = AsyncMock(return_value=[_search_result("c1")])

    with (
        patch("secondbrain.search.EmbeddingProviderFactory") as embedding_factory,
        patch("secondbrain.search.StorageFactory") as storage_factory,
    ):
        embedding_factory.create_from_config.return_value = embedding_gen
        storage_factory.create_from_config.return_value = storage
        searcher = Searcher()

    return searcher, embedding_gen, storage


def _search_result(chunk_id: str) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        source_file="a.pdf",
        page_number=1,
        chunk_text="hello",
        element_type="paragraph",
        chunk_role="body",
        section_label="Chapter 1",
        score=0.9,
    )


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, list[Any]]:
    spans: dict[str, list[Any]] = {}
    for span in exporter.get_finished_spans():
        spans.setdefault(span.name, []).append(span)
    return spans


class TestSyncSearchSpans:
    def test_search_generate_embedding_span_has_query_length_and_top_k(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        results = searcher.search(QUERY, top_k=3)

        assert len(results) == 1
        spans = _spans_by_name(exporter)
        span = spans["search_generate_embedding"][0]
        assert span.attributes["search.query_length"] == len(QUERY)
        assert span.attributes["search.top_k"] == 3

    def test_search_generate_embedding_span_records_filters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        searcher.search(QUERY, top_k=2, source_filter="a.pdf", file_type_filter="pdf")

        span = _spans_by_name(exporter)["search_generate_embedding"][0]
        assert span.attributes["search.source_filter"] == "a.pdf"
        assert span.attributes["search.file_type_filter"] == "pdf"

    def test_search_storage_span_has_top_k_and_embedding_dim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        searcher.search(QUERY, top_k=3)

        span = _spans_by_name(exporter)["search_storage"][0]
        assert span.attributes["search.top_k"] == 3
        assert span.attributes["search.embedding_dim"] == EMBEDDING_DIM

    def test_search_spans_nest_under_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both search spans are children of the active caller span."""
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        with tracing_module.trace_operation("caller_op"):
            searcher.search(QUERY, top_k=1)

        spans = _spans_by_name(exporter)
        caller = spans["caller_op"][0]
        for name in ("search_generate_embedding", "search_storage"):
            span = spans[name][0]
            assert span.context.trace_id == caller.context.trace_id
            assert span.parent is not None
            assert span.parent.span_id == caller.context.span_id


class TestAsyncSearchSpans:
    async def test_search_async_generate_embedding_span_has_query_length(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        results = await searcher.search_async(QUERY, top_k=3)

        assert len(results) == 1
        spans = _spans_by_name(exporter)
        span = spans["search_generate_embedding_async"][0]
        assert span.attributes["search.query_length"] == len(QUERY)
        assert span.attributes["search.top_k"] == 3

    async def test_search_async_storage_span_has_top_k_and_embedding_dim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        searcher, _, _ = _make_searcher()

        await searcher.search_async(QUERY, top_k=3)

        span = _spans_by_name(exporter)["search_storage_async"][0]
        assert span.attributes["search.top_k"] == 3
        assert span.attributes["search.embedding_dim"] == EMBEDDING_DIM


class TestSearchSpansDisabled:
    def test_no_spans_when_tracing_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tracing disabled: search works with zero span overhead."""
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")
        monkeypatch.setattr(tracing_module, "OTTEL_AVAILABLE", True)
        monkeypatch.setattr(tracing_module, "get_tracer", lambda: tracer)
        monkeypatch.setattr(tracing_module, "is_tracing_enabled", lambda: False)
        searcher, _, _ = _make_searcher()

        results = searcher.search(QUERY, top_k=1)

        assert len(results) == 1
        assert not exporter.get_finished_spans()
