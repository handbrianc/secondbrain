"""Tests for worker phase timing spans in _extract_chunk_and_embed_file.

Verifies that the extract, chunk, and embed phases of the sync worker are each
wrapped in a ``trace_operation`` span so stage timing is visible per file.
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import secondbrain.document.processor as processor
import secondbrain.embedding as embedding_module
import secondbrain.utils.tracing as tracing_module

_SAMPLE_TEXT = (
    "SecondBrain is a local document intelligence CLI for semantic search. "
    "It uses MongoDB vector search and OpenAI-compatible embedding APIs to "
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
