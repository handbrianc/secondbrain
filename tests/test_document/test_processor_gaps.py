"""Gap tests for secondbrain.document.processor error branches and fast path.

Targets the uncovered branches reported by coverage for
``secondbrain/document/processor.py``:

- ``_segment_as_text`` table-item fallbacks (export_to_data_frame present,
  raising; text attr only; empty item);
- ``convert_file_to_segments`` fast-PDF path returning segments directly;
- ``_extract_and_chunk_file`` success and error result dicts;
- ``_extract_chunk_and_embed_file`` error result dict with failure queued on
  the progress queue;
- blank-chunk dropping and ``skip_existing`` filtering (skip off / on with
  storage answering);
- re-ingest skip lookup degrading to "embed everything" on storage errors;
- progress "started" / "progress" / final messages on a fake queue;
- ``_existing_text_hashes`` returning empty on storage failure and for an
  empty hash list;
- ``_embed_unique_chunks`` progress callbacks and cache-less embedding.

Mocking style matches ``tests/test_document/test_worker_timing_spans.py``:
fake converter items + fake embedding model + monkeypatched
``docling_factory.get_converter_for_path``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

import secondbrain.embedding as embedding_module
import secondbrain.utils.tracing as tracing_module
from secondbrain.document import processor
from secondbrain.utils.embedding_cache import EmbeddingCache


class _TextItem:
    def __init__(self, text: str, page_no: int = 1, label: str | None = None) -> None:
        self.text = text
        self.prov = [type("_Prov", (), {"page_no": page_no})()]
        if label is not None:
            self.label = label


class _Content:
    def __init__(self, texts: list[Any]) -> None:
        self.texts = texts


class _Result:
    def __init__(self, document: _Content) -> None:
        self.document = document


class _FakeConverter:
    def __init__(self, texts: list[_TextItem]) -> None:
        self._texts = texts
        self.convert_calls = 0

    def convert(self, file_path: Any) -> _Result:
        self.convert_calls += 1
        return _Result(_Content(self._texts))


class _FakeEmbeddingModel:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.1] * 4 for _ in texts]


def _install_converter(monkeypatch: pytest.MonkeyPatch, converter: Any) -> None:
    import secondbrain.document.docling_factory as docling_factory

    monkeypatch.setattr(docling_factory, "get_converter_for_path", lambda _p: converter)


def _install_embedder(monkeypatch: pytest.MonkeyPatch, model: Any) -> None:
    monkeypatch.setattr(
        embedding_module.EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(lambda _cfg: model),
    )


def _sample_text() -> str:
    return (
        "SecondBrain is a local document intelligence CLI for semantic search. "
        "It uses Qdrant vector search and OpenAI-compatible embedding APIs to "
        "ingest, chunk, embed, and retrieve documents from a personal knowledge "
        "base. This sentence supplies enough characters to exercise the chunker "
        "and produce at least one deterministic chunk for the worker pipeline."
    ) * 4


def _write_sample(tmp_path: Path) -> Path:
    f = tmp_path / "sample.txt"
    f.write_text(_sample_text(), encoding="utf-8")
    return f


def _hash_of(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


@pytest.fixture
def span_capture(monkeypatch: pytest.MonkeyPatch):
    """Route trace_operation spans into an in-memory exporter."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(tracing_module, "OTTEL_AVAILABLE", True)
    monkeypatch.setattr(tracing_module, "get_tracer", lambda: tracer)
    monkeypatch.setattr(tracing_module, "is_tracing_enabled", lambda: True)
    return exporter


class TestSegmentAsText:
    """_segment_as_text table/text/empty fallbacks."""

    def test_table_item_uses_dataframe_csv(self) -> None:
        class _Table:
            def export_to_data_frame(self) -> Any:
                class _DF:
                    def to_csv(self, index: bool) -> str:
                        assert index is False
                        return "a,b\n1,2\n"

                return _DF()

        assert processor._segment_as_text(_Table()) == "a,b\n1,2\n"

    def test_table_item_dataframe_failure_falls_back_to_str(self) -> None:
        class _Table:
            def export_to_data_frame(self) -> Any:
                raise RuntimeError("df exploded")

            def __repr__(self) -> str:
                return "<table item>"

        assert processor._segment_as_text(_Table()) == "<table item>"

    def test_plain_text_item(self) -> None:
        class _Text:
            text = "hello body"

        assert processor._segment_as_text(_Text()) == "hello body"

    def test_empty_text_and_unknown_item_yield_empty(self) -> None:
        class _Empty:
            text = ""

        assert processor._segment_as_text(_Empty()) == ""
        assert processor._segment_as_text(object()) == ""


class TestConvertFileToSegments:
    """convert_file_to_segments fast path + plain-text fallback."""

    def test_fast_pdf_segments_returned_directly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import secondbrain.document.fast_text as fast_text

        monkeypatch.setattr(
            "secondbrain.config.config",
            lambda: _cfg(fast_text=True, ocr=False),
        )
        fast_segments = [{"text": "fast page one " * 40, "page": 1}]
        monkeypatch.setattr(
            fast_text, "extract_native_pdf_text", lambda p: fast_segments
        )

        pdf = tmp_path / "native.pdf"
        pdf.write_bytes(b"%PDF-1.4 minimal")

        result = processor.convert_file_to_segments(pdf)

        assert result == [{"text": "fast page one " * 40, "page": 1}]

    def test_docling_textless_file_falls_back_to_plain_read(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """No docling texts -> raw file content becomes a single page-1 segment."""
        import secondbrain.document.fast_text as fast_text

        monkeypatch.setattr(
            "secondbrain.config.config",
            lambda: _cfg(fast_text=False, ocr=False),
        )
        monkeypatch.setattr(
            fast_text,
            "extract_native_pdf_text",
            lambda p: (_ for _ in ()).throw(AssertionError("fast path must stay off")),
        )

        converter = _FakeConverter([])  # docling reports no text items
        monkeypatch.setattr(processor, "create_converter", lambda _p: converter)

        f = tmp_path / "plain.txt"
        f.write_text("raw fallback body", encoding="utf-8")

        result = processor.convert_file_to_segments(f)

        assert result == [{"text": "raw fallback body", "page": 1}]
        assert converter.convert_calls == 1

    def test_docling_labels_propagate_into_segments(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import secondbrain.document.fast_text as fast_text

        monkeypatch.setattr(
            "secondbrain.config.config",
            lambda: _cfg(fast_text=False, ocr=False),
        )
        monkeypatch.setattr(
            fast_text,
            "extract_native_pdf_text",
            lambda p: (_ for _ in ()).throw(AssertionError("fast path must stay off")),
        )

        converter = _FakeConverter(
            [_TextItem("A heading", page_no=2, label="section_header")]
        )
        monkeypatch.setattr(processor, "create_converter", lambda _p: converter)

        result = processor.convert_file_to_segments(tmp_path / "doc.txt")

        assert result == [{"text": "A heading", "page": 2, "label": "section_header"}]


def _cfg(*, fast_text: bool, ocr: bool, skip_existing: bool = False) -> Any:
    """Minimal config stand-in for the flags processor/fast_text read."""

    class _FakeCfg:
        pdf_fast_text_enabled = fast_text
        pdf_ocr_enabled = ocr
        pdf_structure_probe_enabled = False
        pdf_table_structure_enabled = False
        pdf_table_fast_mode = True
        pdf_table_cell_matching = False
        pdf_accelerator_device = "auto"
        pdf_num_threads = 4
        pdf_threaded_pipeline = False
        pdf_layout_batch_size = 4
        pdf_generate_page_images = False
        pdf_generate_picture_images = False
        pdf_images_scale = 1.0
        skip_existing_on_reingest = skip_existing
        embedding_batch_size = 8
        streaming_enabled = False

    return _FakeCfg()


class TestExtractAndChunkFile:
    """_extract_and_chunk_file success and error result dicts."""

    def test_success_result_dict(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )

        result = processor._extract_and_chunk_file(
            str(f), chunk_size=512, chunk_overlap=50
        )

        assert result["success"] is True
        assert result["error"] is None
        assert result["segments"] and result["segments"][0]["page"] == 1
        assert result["file_path"] == f

    def test_fast_pdf_result_segments(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import secondbrain.document.fast_text as fast_text

        monkeypatch.setattr(
            "secondbrain.config.config",
            lambda: _cfg(fast_text=True, ocr=False),
        )
        monkeypatch.setattr(
            fast_text,
            "extract_native_pdf_text",
            lambda p: [{"text": "fast body " * 40, "page": 1}],
        )

        pdf = tmp_path / "native.pdf"
        pdf.write_bytes(b"%PDF-1.4 minimal")

        result = processor._extract_and_chunk_file(
            str(pdf), chunk_size=512, chunk_overlap=50
        )

        assert result["success"] is True
        assert result["segments"] == [{"text": "fast body " * 40, "page": 1}]

    def test_error_result_dict_on_converter_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)

        class _BoomConverter:
            def convert(self, _p: Any) -> Any:
                raise RuntimeError("docling layout crash")

        _install_converter(monkeypatch, _BoomConverter())

        result = processor._extract_and_chunk_file(
            str(f), chunk_size=512, chunk_overlap=50
        )

        assert result["success"] is False
        assert result["segments"] == []
        assert result["error"] == "RuntimeError: docling layout crash"

    def test_nonexistent_path_error_result(self, tmp_path: Path) -> None:
        result = processor._extract_and_chunk_file(
            str(tmp_path / "nope.txt"), chunk_size=512, chunk_overlap=50
        )

        assert result["success"] is False
        assert "nope.txt" in result["error"]


class TestExtractChunkAndEmbedErrors:
    """_extract_chunk_and_embed_file error result + queue failure message."""

    def test_error_result_and_failure_queued(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        _install_embedder(monkeypatch, _BrokenEmbedder())
        queue = _Queue()

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=queue,
            embedding_model_name="test-model",
        )

        assert result["success"] is False
        assert result["documents"] == []
        assert result["error"].startswith("RuntimeError: embed blew up")
        assert queue.items[0][0] == "started"
        assert queue.items[-1] == (str(f), False)

    def test_success_without_queue_and_with_cache(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()
        _install_embedder(monkeypatch, model)
        cache = EmbeddingCache(max_size=1000)

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            embedding_cache=cache,
        )

        assert result["success"] is True
        assert result["error"] is None
        assert result["skipped"] is False
        assert result["documents"], "documents must be produced"
        for doc in result["documents"]:
            assert doc["embedding"] == [0.1] * 4
            assert doc["file_type"] == "text"
            assert doc["source_file"] == str(f)
        assert cache.hits + cache.misses >= 1

    def test_skip_existing_none_reads_config_true_and_skips_all(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """skip_existing=None + skip_existing_on_reingest=True -> skip lookup runs."""
        from unittest.mock import MagicMock

        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()
        _install_embedder(monkeypatch, model)

        seen: dict[str, int] = {}

        def _existing(hashes: list[str]) -> set[str]:
            for h in hashes:
                seen[h] = seen.get(h, 0) + 1
            return set(hashes)

        monkeypatch.setattr(processor, "_existing_text_hashes", _existing)
        mock_cfg = MagicMock()
        mock_cfg.embedding_model = "test-model"
        mock_cfg.embedding_batch_size = 100
        mock_cfg.skip_existing_on_reingest = True
        monkeypatch.setattr("secondbrain.config.config", lambda: mock_cfg)

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=None,
        )

        assert result["success"] is True
        assert result["documents"] == []
        assert result["skipped"] is True
        assert seen, "skip lookup must have run"
        assert model.batches == []

    def test_skip_existing_false_overrides_config_and_embeds(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()
        _install_embedder(monkeypatch, model)

        def _boom(_hashes: list[str]) -> set[str]:
            raise AssertionError("skip lookup must not run when skip_existing=False")

        monkeypatch.setattr(processor, "_existing_text_hashes", _boom)

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True
        assert result["skipped"] is False
        assert len(result["documents"]) >= 1

    def test_blank_and_duplicate_chunks_dropped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Chunker output includes whitespace-only chunks; worker must drop them."""
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()
        _install_embedder(monkeypatch, model)

        original_chunk = processor.chunk_segments

        def fake_chunk(
            segments: Any,
            chunk_size: int,
            chunk_overlap: int,
        ) -> Any:
            chunks = list(original_chunk(segments, chunk_size, chunk_overlap))
            dup = dict(chunks[0])
            chunks.insert(1, {"text": "   ", "page": 1})
            chunks.insert(1, dup)
            return chunks

        monkeypatch.setattr(processor, "chunk_segments", fake_chunk)

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True
        texts = [d["chunk_text"] for d in result["documents"]]
        assert len(texts) == len(set(texts)), "duplicates must be dropped"
        assert all(t.strip() for t in texts), "blank chunks must be dropped"

    def test_skip_lookup_storage_error_degrades_to_embed_all(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()
        _install_embedder(monkeypatch, model)

        def _broken_create(cfg: Any = None) -> Any:
            raise RuntimeError("qdrant unreachable")

        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            storage_mod.StorageFactory, "create_from_config", _broken_create
        )

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=True,
        )

        assert result["success"] is True
        assert result["skipped"] is False
        assert len(result["documents"]) >= 1


class _BrokenEmbedder:
    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed blew up")


class _Queue:
    """Stand-in for queue.Queue capturing put_nowait messages."""

    def __init__(self) -> None:
        self.items: list[Any] = []

    def put_nowait(self, item: Any) -> None:
        self.items.append(item)


class TestProgressQueueMessages:
    """started / progress / final messages flow through the queue."""

    def test_started_progress_and_final_messages(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch,
            _FakeConverter(
                [_TextItem(_sample_text(), page_no=1), _TextItem("Intro.", page_no=2)]
            ),
        )
        _install_embedder(monkeypatch, _FakeEmbeddingModel())
        queue = _Queue()

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=queue,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True
        kinds = [m[0] for m in queue.items if isinstance(m[0], str)]
        assert "started" in kinds
        assert kinds.count("progress") >= 1
        assert ("started", str(f), len(result["documents"])) in queue.items
        assert queue.items[-1] == (str(f), True)

    def test_queue_failures_are_suppressed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A hostile queue must not break the worker."""

        class _HostileQueue:
            def put_nowait(self, _item: Any) -> None:
                raise RuntimeError("queue closed")

        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        _install_embedder(monkeypatch, _FakeEmbeddingModel())

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=_HostileQueue(),
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True


class TestEmbedUniqueChunks:
    """_embed_unique_chunks batching, caching, and progress callbacks."""

    def test_batching_and_progress_callbacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        model = _FakeEmbeddingModel()
        chunks = [{"text": f"chunk {n}"} for n in range(5)]
        progress: list[tuple[int, int]] = []

        embeddings = processor._embed_unique_chunks(
            model,
            chunks,
            batch_size=2,
            progress_callback=lambda done, total: progress.append((done, total)),
        )

        assert len(embeddings) == 5
        assert [len(b) for b in model.batches] == [2, 2, 1]
        assert progress == [(2, 5), (4, 5), (5, 5)]

    def test_no_cache_calls_model_for_every_slice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        model = _FakeEmbeddingModel()
        chunks = [{"text": f"t{n}"} for n in range(3)]

        embeddings = processor._embed_unique_chunks(model, chunks, batch_size=8)

        assert len(embeddings) == 3
        assert len(model.batches) == 1

    def test_cache_hit_and_miss_mix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        model = _FakeEmbeddingModel()
        cache = EmbeddingCache(max_size=1000)
        cache.set("known text", [0.9, 0.9, 0.9, 0.9])
        chunks = [{"text": "known text"}, {"text": "fresh text"}]

        embeddings = processor._embed_unique_chunks(
            model, chunks, embedding_cache=cache, batch_size=8
        )

        assert embeddings[0] == [0.9, 0.9, 0.9, 0.9]
        assert embeddings[1] == [0.1] * 4
        assert model.batches == [["fresh text"]]

    def test_default_batch_size_comes_from_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "secondbrain.config.config", lambda: _cfg(fast_text=False, ocr=False)
        )
        model = _FakeEmbeddingModel()
        chunks = [{"text": f"t{n}"} for n in range(3)]

        processor._embed_unique_chunks(model, chunks)  # batch_size=None

        assert len(model.batches) == 1


class TestExistingTextHashes:
    """_existing_text_hashes storage query + graceful degradation."""

    def test_empty_hashes_returns_empty_set_without_storage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_a: Any) -> Any:
            raise AssertionError("storage must not be touched for empty hashes")

        import secondbrain.storage as storage_mod

        monkeypatch.setattr(storage_mod.StorageFactory, "create_from_config", _boom)
        assert processor._existing_text_hashes([]) == set()

    def test_storage_error_returns_empty_set(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _broken_create(cfg: Any = None) -> Any:
            raise RuntimeError("connection refused")

        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            storage_mod.StorageFactory, "create_from_config", _broken_create
        )

        with caplog.at_level("WARNING"):
            result = processor._existing_text_hashes(["abc"])

        assert result == set()
        assert any(
            "Could not query existing text hashes" in r.message for r in caplog.records
        )

    def test_storage_answer_is_set_converted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _St:
            def has_existing_hashes(self, hashes: list[str]) -> list[str]:
                assert hashes == ["h1", "h2"]
                return ["h1"]

        def _create(cfg: Any = None) -> Any:
            return _St()

        import secondbrain.storage as storage_mod

        monkeypatch.setattr(storage_mod.StorageFactory, "create_from_config", _create)
        assert processor._existing_text_hashes(["h1", "h2"]) == {"h1"}


class TestFilterAndSpans:
    """_filter_existing_chunks ordering + worker span coverage."""

    def test_filter_existing_chunks_preserves_order(self) -> None:
        chunks = [
            {"text": "a", "text_hash": "h1"},
            {"text": "b", "text_hash": "h2"},
            {"text": "c", "text_hash": "h3"},
        ]
        out = processor._filter_existing_chunks(chunks, {"h2"})
        assert [c["text"] for c in out] == ["a", "c"]
        assert processor._filter_existing_chunks(chunks, set()) is chunks

    def test_worker_spans_cover_chunk_and_embed_phases(
        self,
        span_capture: Any,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        _install_embedder(monkeypatch, _FakeEmbeddingModel())

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True
        names = [s.name for s in span_capture.get_finished_spans()]
        assert "ingest_worker_chunk" in names
        assert "ingest_worker_embed" in names

    def test_worker_error_path_still_queues_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Non-extraction failure deep in the worker still returns error dict."""
        f = _write_sample(tmp_path)
        _install_converter(
            monkeypatch, _FakeConverter([_TextItem(_sample_text(), page_no=1)])
        )
        model = _FakeEmbeddingModel()

        def boom_batch(texts: list[str]) -> list[list[float]]:
            raise ValueError("bad vector shape")

        model.generate_batch = boom_batch
        _install_embedder(monkeypatch, model)
        queue = _Queue()

        result = processor._extract_chunk_and_embed_file(
            str(f),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=queue,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is False
        assert result["error"] == "ValueError: bad vector shape"
        assert queue.items[0][0] == "started"
        assert queue.items[-1] == (str(f), False)
        del caplog
