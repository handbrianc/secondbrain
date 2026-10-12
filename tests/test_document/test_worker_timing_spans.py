"""Tests for worker phase timing spans in _extract_chunk_and_embed_file.

Verifies that the extract, chunk, and embed phases of the sync worker are each
wrapped in a ``trace_operation`` span so stage timing is visible per file.

Also asserts the async ingestor's ``storage.store`` span (name + attributes)
and its per-batch ``ingest_worker_embed`` span emitted by
``_store_embedding_batch_async``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import secondbrain.document.processor as processor
import secondbrain.embedding as embedding_module
import secondbrain.utils.tracing as tracing_module
from secondbrain.document.ingestor import AsyncDocumentIngestor

_SAMPLE_TEXT = (
    "SecondBrain is a local document intelligence CLI for semantic search. "
    "It uses Qdrant vector search and OpenAI-compatible embedding APIs to "
    "ingest, chunk, embed, and retrieve documents from a personal knowledge "
    "base. This sentence supplies enough characters to exercise the chunker "
    "and produce at least one deterministic chunk for the worker pipeline."
) * 4


class _TextItem:
    def __init__(self, text: str, page_no: int = 1) -> None:
        self.text = text
        self.prov = [type("_Prov", (), {"page_no": page_no})()]


class _Content:
    def __init__(self, texts: list[_TextItem]) -> None:
        self.texts = texts


class _Result:
    def __init__(self, document: _Content) -> None:
        self.document = document


class _FakeConverter:
    def __init__(self, texts: list[_TextItem]) -> None:
        self._texts = texts

    def convert(self, file_path):
        return _Result(_Content(self._texts))


class _FakeEmbeddingModel:
    def generate_batch(self, texts):
        return [[0.1] * 4 for _ in texts]


def setup_span_capture(monkeypatch) -> InMemorySpanExporter:
    """Route trace_operation spans into an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(tracing_module, "OTTEL_AVAILABLE", True)
    monkeypatch.setattr(tracing_module, "get_tracer", lambda: tracer)
    monkeypatch.setattr(tracing_module, "is_tracing_enabled", lambda: True)
    return exporter


def run_worker(monkeypatch, tmp_path) -> dict:
    """Run the worker against fake converter + fake embedding model."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text(_SAMPLE_TEXT, encoding="utf-8")

    converter = _FakeConverter(
        [_TextItem(_SAMPLE_TEXT, page_no=1), _TextItem("Introduction.", page_no=2)]
    )

    import secondbrain.document.docling_factory as docling_factory

    monkeypatch.setattr(docling_factory, "get_converter_for_path", lambda _p: converter)
    monkeypatch.setattr(
        embedding_module.EmbeddingProviderFactory,
        "create_from_config",
        lambda _cfg: _FakeEmbeddingModel(),
    )

    return processor._extract_chunk_and_embed_file(
        str(file_path),
        chunk_size=512,
        chunk_overlap=50,
        progress_queue=None,
        embedding_model_name="test-model",
    )


def span_names_and_durations(exporter) -> dict[str, float]:
    spans = exporter.get_finished_spans()
    return {s.name: (s.end_time - s.start_time) for s in spans}


def test_worker_emits_stage_spans(monkeypatch, tmp_path):
    exporter = setup_span_capture(monkeypatch)
    result = run_worker(monkeypatch, tmp_path)

    assert result["success"] is True

    spans = span_names_and_durations(exporter)
    for expected in (
        "ingest_worker_extract",
        "ingest_worker_chunk",
        "ingest_worker_embed",
    ):
        assert expected in spans, f"missing span {expected!r} in {sorted(spans)}"
        assert spans[expected] >= 0


def test_worker_span_order_and_attributes(monkeypatch, tmp_path):
    exporter = setup_span_capture(monkeypatch)
    run_worker(monkeypatch, tmp_path)

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]

    assert "ingest_worker_extract" in names
    assert "ingest_worker_chunk" in names
    assert "ingest_worker_embed" in names

    assert names.index("ingest_worker_extract") < names.index("ingest_worker_chunk")
    assert names.index("ingest_worker_chunk") < names.index("ingest_worker_embed")

    for span in spans:
        attrs = span.attributes or {}
        if span.name == "ingest_worker_extract":
            assert "ingest.filesize_bytes" in attrs
        elif span.name == "ingest_worker_chunk":
            assert "ingest.segments_count" in attrs
        elif span.name == "ingest_worker_embed":
            assert "ingest.chunks_count" in attrs


class TestAsyncStoreSpans:
    """Async batch storage emits real ``storage.store``/embed spans."""

    @pytest.mark.asyncio
    async def test_async_store_span_name_and_attributes(self, monkeypatch) -> None:
        """storage.store carries documents_stored + duration_ms; embed carries chunks_count."""
        exporter = setup_span_capture(monkeypatch)

        ingestor = AsyncDocumentIngestor()
        gen = MagicMock()
        gen.generate_batch_async = AsyncMock(return_value=[[0.1] * 4, [0.2] * 4])
        storage = MagicMock()
        storage.store_batch_async = AsyncMock(return_value=["id1", "id2"])

        chunks = [
            {
                "file_path": Path("/tmp/sample.pdf"),
                "original_index": n,
                "text": f"async stored chunk {n}",
                "page": 1,
                "text_hash": n,
                "chunk_role": "body",
                "element_type": "body",
            }
            for n in range(2)
        ]

        stored = await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"), chunks, gen, storage
        )

        assert stored == 2

        spans = exporter.get_finished_spans()
        store_spans = [s for s in spans if s.name == "storage.store"]
        assert len(store_spans) == 1
        store_attrs = store_spans[0].attributes or {}
        assert store_attrs["storage.documents_stored"] == 2
        assert "storage.duration_ms" in store_attrs

        embed_spans = [s for s in spans if s.name == "ingest_worker_embed"]
        assert len(embed_spans) == 1
        embed_attrs = embed_spans[0].attributes or {}
        assert embed_attrs["ingest.chunks_count"] == 2
