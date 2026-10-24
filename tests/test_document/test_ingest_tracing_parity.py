"""Sync/async ingestor tracing and return-shape parity tests.

Covers the instrumentation compliance gaps shared by both ingest paths:

- the ``ingest_collect_files`` span carries the requested file path as an
  ``ingest.file_path`` attribute on BOTH the sync ``ingest()`` and the async
  ``ingest_async()`` entry points;
- the async ingestor mirrors the sync worker instrumentation, emitting
  ``ingest_worker_extract`` / ``ingest_worker_chunk`` / ``ingest_worker_embed``
  spans with the same ``ingest.*`` attributes the sync worker sets (plus the
  ``storage.store`` span), on the non-streaming and streaming flows alike;
- ``ingest_async()`` returns the same four keys as the sync ``ingest()``
  (``success`` / ``failed`` / ``failures`` / ``skipped``) for the same input
  scenario — including a raised per-file error, whose reason is recorded in
  the sync worker's ``"ExceptionType: message"`` format on both paths.

Mocking style matches ``tests/test_document/test_async_ingestor_gaps.py``:
AsyncMock storage/LLM plus MagicMock embedding generators, and the parallel
runner is replaced with a spy so no real pool/embedding work happens.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import secondbrain.embedding as embedding_module
import secondbrain.storage as storage_module
import secondbrain.utils.tracing as tracing_module
from secondbrain.document import DocumentIngestor
from secondbrain.document.ingestor import AsyncDocumentIngestor

_NO_DOCS_REASON = (
    "No documents produced (file may be empty, image-only, or extraction failed)"
)


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


def _patch_factories(
    monkeypatch: pytest.MonkeyPatch,
    gen: Any | None = None,
    st: Any | None = None,
) -> None:
    """Stub the embedding/storage factories both ingest paths construct."""
    monkeypatch.setattr(
        embedding_module.EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(lambda cfg: gen if gen is not None else MagicMock()),
    )
    monkeypatch.setattr(
        storage_module.StorageFactory,
        "create_from_config",
        staticmethod(lambda cfg: st if st is not None else MagicMock()),
    )


def spans_by_name(exporter: InMemorySpanExporter) -> dict[str, list[Any]]:
    """Group finished spans by span name (preserving emission order)."""
    grouped: dict[str, list[Any]] = {}
    for span in exporter.get_finished_spans():
        grouped.setdefault(span.name, []).append(span)
    return grouped


def _make_config() -> Any:
    from secondbrain.config import config

    return config()


class TestSyncCollectSpan:
    """Sync ingest() creates ingest_collect_files with the file path."""

    def test_collect_span_carries_file_path(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        _patch_factories(monkeypatch)
        (tmp_path / "doc.txt").write_text("sync content")

        ingestor = DocumentIngestor(verbose=False)

        def fake_parallel(
            files: Any,
            embedding_gen: Any,
            storage: Any,
            max_workers: int,
            pool: Any = None,
            skip_existing: Any = None,
        ) -> tuple[int, int, list[Any], int]:
            return (len(files), 0, [], 0)

        monkeypatch.setattr(ingestor, "_process_parallel_with_progress", fake_parallel)

        result = ingestor.ingest(str(tmp_path))

        collect = spans_by_name(exporter).get("ingest_collect_files")
        assert collect is not None, "sync ingest must emit ingest_collect_files"
        attrs = collect[0].attributes or {}
        assert attrs["ingest.file_path"] == str(tmp_path)
        assert result["success"] == 1


class TestAsyncCollectSpan:
    """Async ingest_async() creates the same collect span with the path."""

    @pytest.mark.asyncio
    async def test_collect_span_carries_file_path(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        _patch_factories(monkeypatch)
        (tmp_path / "doc.txt").write_text("async content")

        ingestor = AsyncDocumentIngestor()
        with patch.object(
            ingestor, "process_file_async", new=AsyncMock(return_value=True)
        ):
            result = await ingestor.ingest_async(str(tmp_path))

        collect = spans_by_name(exporter).get("ingest_collect_files")
        assert collect is not None, "async ingest must emit ingest_collect_files"
        attrs = collect[0].attributes or {}
        assert attrs["ingest.file_path"] == str(tmp_path)
        assert result["success"] == 1


class TestAsyncWorkerSpans:
    """The async path emits the sync worker spans with the same attributes."""

    @pytest.mark.asyncio
    async def test_nonstreaming_flow_emits_worker_spans(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exporter = setup_span_capture(monkeypatch)
        cfg = _make_config()
        monkeypatch.setattr(cfg, "streaming_enabled", False, raising=False)

        f = tmp_path / "doc.txt"
        f.write_text("body text")

        gen = MagicMock()
        gen.generate_batch_async = AsyncMock(return_value=[[0.1] * 8])
        st = MagicMock()
        st.store_batch_async = AsyncMock(return_value=["id1"])
        _patch_factories(monkeypatch, gen=gen, st=st)

        ingestor = AsyncDocumentIngestor()

        def one_seg(
            _p: Any, _structure_sink: list[Any] | None = None
        ) -> list[dict[str, Any]]:
            return [{"text": "body text", "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", one_seg)

        result = await ingestor.ingest_async(str(f))

        assert result == {
            "success": 1,
            "failed": 0,
            "failures": [],
            "skipped": 0,
        }

        spans = spans_by_name(exporter)
        extract_attrs = spans["ingest_worker_extract"][0].attributes or {}
        assert extract_attrs["ingest.filesize_bytes"] == f.stat().st_size
        chunk_attrs = spans["ingest_worker_chunk"][0].attributes or {}
        assert chunk_attrs["ingest.segments_count"] == 1
        embed_attrs = spans["ingest_worker_embed"][0].attributes or {}
        assert embed_attrs["ingest.chunks_count"] == 1
        store_attrs = spans["storage.store"][0].attributes or {}
        assert store_attrs["storage.documents_stored"] == 1
        assert "storage.duration_ms" in store_attrs

    @pytest.mark.asyncio
    async def test_streaming_flow_emits_worker_spans(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default streaming branch gets the same span names/attributes."""
        exporter = setup_span_capture(monkeypatch)
        cfg = _make_config()
        monkeypatch.setattr(cfg, "streaming_enabled", True, raising=False)
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 2, raising=False)

        f = tmp_path / "doc.txt"
        f.write_text("streaming body")

        gen = MagicMock()
        gen.generate_batch_async = AsyncMock(
            side_effect=[[[0.1] * 8, [0.2] * 8], [[0.3] * 8]]
        )
        st = MagicMock()
        st.store_batch_async = AsyncMock(return_value=["id1"])
        _patch_factories(monkeypatch, gen=gen, st=st)

        ingestor = AsyncDocumentIngestor()

        def segs(
            _p: Any, _structure_sink: list[Any] | None = None
        ) -> list[dict[str, Any]]:
            return [{"text": f"segment {n} text", "page": 1} for n in range(3)]

        monkeypatch.setattr(ingestor, "_extract_text", segs)

        result = await ingestor.ingest_async(str(f))

        assert result["success"] == 1
        assert result["failed"] == 0

        spans = spans_by_name(exporter)
        extract_attrs = spans["ingest_worker_extract"][0].attributes or {}
        assert extract_attrs["ingest.filesize_bytes"] == f.stat().st_size
        chunk_attrs = spans["ingest_worker_chunk"][0].attributes or {}
        assert chunk_attrs["ingest.segments_count"] == 3

        # One embed span + one storage.store span per flushed batch (2+1).
        assert len(spans["ingest_worker_embed"]) == 2
        embed_counts = {
            s.attributes["ingest.chunks_count"] for s in spans["ingest_worker_embed"]
        }
        assert embed_counts == {2, 1}
        assert len(spans["storage.store"]) == 2
        for span in spans["storage.store"]:
            assert "storage.documents_stored" in (span.attributes or {})


class TestSyncAsyncReturnParity:
    """ingest_async() returns the same four keys as sync ingest()."""

    @pytest.mark.asyncio
    async def test_same_scenario_yields_identical_result_dicts(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good = tmp_path / "good.txt"
        good.write_text("fine content " * 20)
        bad = tmp_path / "bad.txt"
        bad.write_text("doomed content " * 20)

        setup_span_capture(monkeypatch)
        _patch_factories(monkeypatch)

        # Sync side: one file ingests, one fails with the no-documents reason.
        sync_ingestor = DocumentIngestor(verbose=False)

        def fake_parallel(
            files: Any,
            embedding_gen: Any,
            storage: Any,
            max_workers: int,
            pool: Any = None,
            skip_existing: Any = None,
        ) -> tuple[int, int, list[tuple[str, str]], int]:
            return (1, 1, [(str(bad), _NO_DOCS_REASON)], 0)

        monkeypatch.setattr(
            sync_ingestor, "_process_parallel_with_progress", fake_parallel
        )
        sync_result = sync_ingestor.ingest(str(tmp_path))

        # Async side: the same two files, same outcome per file.
        async_ingestor = AsyncDocumentIngestor()

        async def fake_process(
            file_path: Any, _gen: Any, _st: Any, **_kwargs: Any
        ) -> bool:
            return bool(file_path == good)

        with patch.object(
            async_ingestor, "process_file_async", side_effect=fake_process
        ):
            async_result = await async_ingestor.ingest_async(str(tmp_path))

        expected_keys = {"success", "failed", "failures", "skipped"}
        assert set(sync_result) == expected_keys
        assert set(async_result) == expected_keys
        assert sync_result == async_result

    @pytest.mark.asyncio
    async def test_exception_scenario_yields_identical_result_dicts(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A raised per-file error records the same "Type: message" reason."""
        good = tmp_path / "good.txt"
        good.write_text("fine content " * 20)
        bad = tmp_path / "bad.txt"
        bad.write_text("doomed content " * 20)

        setup_span_capture(monkeypatch)
        _patch_factories(monkeypatch)

        # Sync side: one file ingests, one fails with the real error reason.
        sync_ingestor = DocumentIngestor(verbose=False)

        def fake_parallel(
            files: Any,
            embedding_gen: Any,
            storage: Any,
            max_workers: int,
            pool: Any = None,
            skip_existing: Any = None,
        ) -> tuple[int, int, list[tuple[str, str]], int]:
            return (1, 1, [(str(bad), "ValueError: qdrant unreachable")], 0)

        monkeypatch.setattr(
            sync_ingestor, "_process_parallel_with_progress", fake_parallel
        )
        sync_result = sync_ingestor.ingest(str(tmp_path))

        # Async side: the same two files; the bad file's worker raises.
        async_ingestor = AsyncDocumentIngestor()

        async def fake_process(
            file_path: Any, _gen: Any, _st: Any, **_kwargs: Any
        ) -> bool:
            if file_path == good:
                return True
            raise ValueError("qdrant unreachable")

        with patch.object(
            async_ingestor, "process_file_async", side_effect=fake_process
        ):
            async_result = await async_ingestor.ingest_async(str(tmp_path))

        expected_keys = {"success", "failed", "failures", "skipped"}
        assert set(sync_result) == expected_keys
        assert set(async_result) == expected_keys
        assert sync_result == async_result
