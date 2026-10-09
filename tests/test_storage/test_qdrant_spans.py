"""Span-attribute tests for Qdrant operations in ``QdrantVectorStorage``.

The opentelemetry-integration spec requires Qdrant spans to carry the
collection name and the operation type so slow queries are identifiable per
collection. Routes ``trace_operation`` spans into an ``InMemorySpanExporter``
(same pattern as ``tests/test_document/test_worker_timing_spans.py``) and
asserts on spans emitted by the real in-memory Qdrant storage.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from qdrant_client import QdrantClient

import secondbrain.utils.tracing as tracing_module
from secondbrain.storage.qdrant import QdrantVectorStorage
from secondbrain.utils.failure_injector.types import InjectedConnectionError

DIM = 4


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


@pytest.fixture()
def storage() -> QdrantVectorStorage:
    """A QdrantVectorStorage backed by a local-mode (in-memory) Qdrant."""
    instance = QdrantVectorStorage(collection_name="span_tests")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def _doc(chunk_id: str, source: str = "a.pdf") -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "source_file": source,
        "page_number": 1,
        "chunk_text": "hello",
        "element_type": "paragraph",
        "chunk_role": "body",
        "section_label": "Chapter 1",
        "file_type": "pdf",
        "text_hash": f"hash-{chunk_id}",
        "chapter_id": 1,
        "section_id": "1.1",
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, list[Any]]:
    spans: dict[str, list[Any]] = {}
    for span in exporter.get_finished_spans():
        spans.setdefault(span.name, []).append(span)
    return spans


def test_qdrant_operations_emit_spans_with_collection_and_operation(
    storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every Qdrant operation span carries qdrant.collection + qdrant.operation."""
    exporter = setup_span_capture(monkeypatch)

    storage.store(_doc("c1"))
    storage.store_batch([_doc("c2", source="b.pdf")])
    storage.search([0.1, 0.2, 0.3, 0.4], top_k=3)
    storage.list_chunks()
    storage.list_source_files()
    storage.count_chunks(chunk_role="body")
    storage.delete_by_source("a.pdf")

    spans = _spans_by_name(exporter)
    assert set(spans) == {
        "qdrant_upsert",
        "qdrant_search",
        "qdrant_scroll",
        "qdrant_facet",
        "qdrant_count",
        "qdrant_delete",
    }

    upserts = spans["qdrant_upsert"]
    assert len(upserts) == 2  # store() + store_batch()
    single = next(s for s in upserts if "qdrant.points" not in s.attributes)
    batch = next(s for s in upserts if "qdrant.points" in s.attributes)
    assert single.attributes["qdrant.collection"] == "span_tests"
    assert single.attributes["qdrant.operation"] == "upsert"
    assert batch.attributes["qdrant.points"] == 1

    search = spans["qdrant_search"][0]
    assert search.attributes["qdrant.collection"] == "span_tests"
    assert search.attributes["qdrant.operation"] == "search"
    assert search.attributes["qdrant.top_k"] == 3

    scroll = spans["qdrant_scroll"][0]
    assert scroll.attributes["qdrant.operation"] == "scroll"
    assert scroll.attributes["qdrant.limit"] == 50  # list_chunks default

    facet = spans["qdrant_facet"][0]
    assert facet.attributes["qdrant.operation"] == "facet"

    count = spans["qdrant_count"][0]
    assert count.attributes["qdrant.operation"] == "count"
    assert count.attributes["qdrant.role"] == "body"

    delete = spans["qdrant_delete"][0]
    assert delete.attributes["qdrant.operation"] == "delete"


def test_qdrant_span_records_error_status_on_failure(
    storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing Qdrant operation marks its span ERROR and records the error."""
    exporter = setup_span_capture(monkeypatch)

    def broken_upsert(*args: Any, **kwargs: Any) -> Any:
        raise InjectedConnectionError("qdrant unreachable")

    monkeypatch.setattr(storage._client, "upsert", broken_upsert)

    with pytest.raises(InjectedConnectionError, match="qdrant unreachable"):
        storage.store(_doc("c1"))

    spans = _spans_by_name(exporter)
    upsert = spans["qdrant_upsert"][0]
    assert upsert.status.status_code == StatusCode.ERROR
    assert upsert.attributes["qdrant.collection"] == "span_tests"
    assert upsert.attributes["qdrant.operation"] == "upsert"
    exception_events = [
        event
        for event in upsert.events
        if "InjectedConnectionError" in str(event.attributes)
    ]
    assert exception_events


def test_qdrant_spans_nest_under_caller_when_tracing_enabled(
    storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The qdrant_search span is a child of the active caller span."""
    exporter = setup_span_capture(monkeypatch)

    with tracing_module.trace_operation("caller_op"):
        storage.search([0.1, 0.2, 0.3, 0.4], top_k=2)

    spans = _spans_by_name(exporter)
    caller = spans["caller_op"][0]
    qdrant = spans["qdrant_search"][0]
    assert qdrant.context.trace_id == caller.context.trace_id
    assert qdrant.parent is not None
    assert qdrant.parent.span_id == caller.context.span_id
