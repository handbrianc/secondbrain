"""Tests for the ingestion executor pool selection (process vs thread).

Covers baseline thread-pool characterization, the new process-pool branch, the
forced-OCR worker cap, config validation, and exactly-once progress aggregation.
All pool-behavior tests use a fake executor so no real OS processes are spawned.
"""

import queue
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from secondbrain.config import Config
from secondbrain.document import DocumentIngestor
from secondbrain.document.ingestor import _sync
from secondbrain.document.processor import _extract_chunk_and_embed_file


class ExecutorRecord:
    """Collects fake-executor instances constructed during a call."""

    def __init__(self):
        self.constructed = []


class _FakeExecutor:
    """Fake executor returning real, pre-resolved futures.

    The owner loop's ``as_completed`` works on real
    :class:`concurrent.futures.Future` objects, so results seeded here make the
    loop terminate deterministically without spawning an OS process.
    """

    def __init__(self, max_workers, result_factory=None, record=None, **kwargs):
        self.max_workers = max_workers
        self.submitted = []
        self._result_factory = result_factory or (
            lambda _i: {
                "success": True,
                "file_path": "fake",
                "documents": [],
                "error": None,
            }
        )
        if record is not None:
            record.constructed.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        future = Future()
        future.set_result(self._result_factory(len(self.submitted) - 1))
        return future


def make_fake(result_factory=None, record=None):
    def _fake_cls(max_workers, **kwargs):
        return _FakeExecutor(max_workers, result_factory=result_factory, record=record)

    return _fake_cls


def _make_ingestor(progress_callback=None, on_chunk_progress=None):
    ingestor = DocumentIngestor.__new__(DocumentIngestor)
    ingestor.chunk_size = 100
    ingestor.chunk_overlap = 20
    ingestor.embedding_cache = object()
    ingestor.progress_callback = progress_callback
    ingestor.on_chunk_progress = on_chunk_progress
    ingestor.on_phase_progress = None
    return ingestor


def _patch_config(monkeypatch, pdf_ocr_enabled=False, ingest_pool="process"):
    mock_cfg = MagicMock()
    mock_cfg.pdf_ocr_enabled = pdf_ocr_enabled
    mock_cfg.ingest_pool = ingest_pool
    mock_cfg.embedding_model = "test-model"
    monkeypatch.setattr("secondbrain.config.config", lambda: mock_cfg)
    return mock_cfg


def _run(monkeypatch, pool, files, max_workers, ingestor, storage=None):
    record = ExecutorRecord()
    fake = make_fake(record=record)
    monkeypatch.setattr(_sync, "ProcessPoolExecutor", fake)
    monkeypatch.setattr(_sync, "ThreadPoolExecutor", fake)
    storage = storage if storage is not None else MagicMock()
    result = ingestor._process_parallel_with_progress(
        files, MagicMock(), storage, max_workers, pool
    )
    return result, record


class TestBaselineThreadPool:
    """Baseline characterization (runs against current behavior as regression)."""

    def test_thread_pool_uses_threadpool_executor(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        _, record = _run(monkeypatch, "thread", files, 4, ingestor)

        assert len(record.constructed) == 1
        assert record.constructed[0].max_workers == 4


class TestProcessPoolSelection:
    def test_process_pool_uses_processpool_executor(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        _, record = _run(monkeypatch, "process", files, 8, ingestor)

        assert len(record.constructed) == 1
        assert record.constructed[0].max_workers == 8

    def test_process_pool_no_progress_channel_without_callback(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        _, record = _run(monkeypatch, "process", files, 4, ingestor)

        executor = record.constructed[0]
        assert executor.submitted
        for fn, args, _kwargs in executor.submitted:
            assert fn is _extract_chunk_and_embed_file
            _, _, _, progress_queue, _, cache, _skip, _scrape = args
            # No on_chunk_progress consumer -> no queue is shared with child
            # processes (a raw queue cannot cross spawn); cache stays None too.
            assert progress_queue is None
            assert cache is None

    def test_thread_pool_no_progress_channel_without_callback(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        _, record = _run(monkeypatch, "thread", files, 4, ingestor)

        executor = record.constructed[0]
        assert executor.submitted
        for fn, args, _kwargs in executor.submitted:
            assert fn is _extract_chunk_and_embed_file
            _, _, _, progress_queue, _, cache, _skip, _scrape = args
            assert progress_queue is None
            assert cache is ingestor.embedding_cache

    def test_thread_pool_uses_queue_when_on_chunk_progress_set(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        ingestor.on_chunk_progress = lambda *_: None
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        _, record = _run(monkeypatch, "thread", files, 4, ingestor)

        executor = record.constructed[0]
        assert executor.submitted
        for fn, args, _kwargs in executor.submitted:
            assert fn is _extract_chunk_and_embed_file
            _, _, _, progress_queue, _, cache, _skip, _scrape = args
            # Thread pool shares memory, so a plain queue.Queue carries within-file
            # progress; the thread-local cache is reused too.
            assert isinstance(progress_queue, queue.Queue)
            assert cache is ingestor.embedding_cache


class TestOcrCapsProcessWorkers:
    def test_force_ocr_caps_process_workers(self, monkeypatch):
        _patch_config(monkeypatch, pdf_ocr_enabled=True)
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.pdf")]

        _, record = _run(monkeypatch, "process", files, 8, ingestor)

        assert record.constructed[0].max_workers == 1

    def test_ocr_off_does_not_cap_process_workers(self, monkeypatch):
        _patch_config(monkeypatch, pdf_ocr_enabled=False)
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.pdf")]

        _, record = _run(monkeypatch, "process", files, 8, ingestor)

        assert record.constructed[0].max_workers == 8


class TestIngestPoolValidator:
    def test_rejects_bogus(self):
        with pytest.raises(ValidationError):
            Config(ingest_pool="bogus")

    def test_accepts_process(self):
        assert Config(ingest_pool="process").ingest_pool == "process"

    def test_accepts_thread(self):
        assert Config(ingest_pool="thread").ingest_pool == "thread"


class TestProcessPoolProgress:
    def test_process_pool_progress_advances_once_per_file(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")

        def result_factory(_i):
            return {
                "success": True,
                "file_path": "fake",
                "documents": [{"chunk_id": "x", "text": "hello"}],
                "error": None,
            }

        calls = []
        ingestor = _make_ingestor(
            progress_callback=lambda fp, success: calls.append((fp, success))
        )
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]
        storage = MagicMock()

        record = ExecutorRecord()
        monkeypatch.setattr(
            _sync,
            "ProcessPoolExecutor",
            make_fake(result_factory=result_factory, record=record),
        )

        successful, failed, _reasons = ingestor._process_parallel_with_progress(
            files, MagicMock(), storage, 4, "process"
        )

        assert successful == 2
        assert failed == 0
        assert len(calls) == 2
        assert all(success for _, success in calls)

    def test_worker_phase_events_drain_before_file_done(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        event_order = []
        ingestor = _make_ingestor(
            progress_callback=lambda _path, _success: event_order.append("done")
        )
        ingestor.on_phase_progress = lambda _path, _phase, _done, _total: (
            event_order.append("phase")
        )

        class _LateProgressFuture(Future):
            def __init__(self, progress_queue):
                super().__init__()
                self._progress_queue = progress_queue
                self.set_result(
                    {
                        "success": True,
                        "file_path": "fake",
                        "documents": [],
                        "error": None,
                        "skipped": True,
                    }
                )

            def result(self, timeout=None):
                self._progress_queue.put_nowait(("phase", "/tmp/a.txt", "embed", 1, 1))
                return super().result(timeout)

        class _FakeLateProgressExecutor(_FakeExecutor):
            def submit(self, fn, *args, **kwargs):
                self.submitted.append((fn, args, kwargs))
                return _LateProgressFuture(args[3])

        def _executor(max_workers, **kwargs):
            return _FakeLateProgressExecutor(max_workers)

        monkeypatch.setattr(_sync, "ThreadPoolExecutor", _executor)
        monkeypatch.setattr(_sync, "ProcessPoolExecutor", _executor)

        result = ingestor._process_parallel_with_progress(
            [Path("/tmp/a.txt")], MagicMock(), MagicMock(), 1, "thread"
        )

        assert result[:2] == (1, 0)
        assert event_order == ["phase", "done"]


class TestSkippedFileAccounting:
    """A fully-skipped file (skipped=True, no docs) must count as success."""

    def test_skipped_result_counts_as_success_and_advances_once(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")

        def result_factory(_i):
            return {
                "success": True,
                "file_path": "fake",
                "documents": [],
                "error": None,
                "skipped": True,
            }

        calls = []
        ingestor = _make_ingestor(
            progress_callback=lambda fp, success: calls.append((fp, success))
        )
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]
        storage = MagicMock()

        record = ExecutorRecord()
        monkeypatch.setattr(
            _sync,
            "ProcessPoolExecutor",
            make_fake(result_factory=result_factory, record=record),
        )

        successful, failed, reasons = ingestor._process_parallel_with_progress(
            files, MagicMock(), storage, 4, "process"
        )

        assert successful == 2
        assert failed == 0
        assert reasons == []
        assert len(calls) == 2
        assert all(success for _, success in calls)
        storage.store_batch.assert_not_called()


class TestOnChunkProgressDispatch:
    """Within-file progress events dispatched to ``on_chunk_progress``."""

    def test_handle_progress_event_dispatches_started_and_progress(self) -> None:
        updates: list[tuple[Path, int, int]] = []
        ingestor = _make_ingestor()
        ingestor.on_chunk_progress = lambda fp, done, total: updates.append(
            (fp, done, total)
        )

        ingestor._handle_progress_event(("started", "/tmp/a.txt", 25))
        ingestor._handle_progress_event(("progress", "/tmp/a.txt", 10, 25))
        ingestor._handle_progress_event(("progress", "/tmp/a.txt", 25, 25))

        assert updates == [
            (Path("/tmp/a.txt"), 0, 25),
            (Path("/tmp/a.txt"), 10, 25),
            (Path("/tmp/a.txt"), 25, 25),
        ]

    def test_handle_progress_event_noop_without_on_chunk_progress(self) -> None:
        ingestor = _make_ingestor()
        ingestor.on_chunk_progress = None

        # Should not raise and should not dispatch.
        ingestor._handle_progress_event(("started", "/tmp/a.txt", 5))

    def test_callback_exception_is_swallowed(self) -> None:
        ingestor = _make_ingestor()
        ingestor.on_chunk_progress = lambda *_: (_ for _ in ()).throw(RuntimeError)

        # Should be swallowed and not propagate.
        ingestor._handle_progress_event(("started", "/tmp/a.txt", 5))


class TestOnPhaseProgressDispatch:
    """Per-phase ("phase", path, phase, done, total) events dispatch."""

    def test_phase_event_dispatches_to_on_phase_progress(self) -> None:
        calls: list[tuple[Path, str, int, int]] = []
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = lambda fp, phase, done, total: calls.append(
            (fp, phase, done, total)
        )

        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "extract", 10, 20))
        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "chunk", 0, 1))
        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "embed", 2, 5))
        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "store", 1, 3))

        assert calls == [
            (Path("/tmp/a.txt"), "extract", 10, 20),
            (Path("/tmp/a.txt"), "chunk", 0, 1),
            (Path("/tmp/a.txt"), "embed", 2, 5),
            (Path("/tmp/a.txt"), "store", 1, 3),
        ]

    def test_phase_event_noop_without_on_phase_progress(self) -> None:
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = None

        # Should not raise and should not dispatch.
        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "extract", 0, 0))

    def test_phase_callback_exception_is_swallowed(self) -> None:
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = lambda *_: (_ for _ in ()).throw(RuntimeError)

        # Should be swallowed and not propagate.
        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "embed", 1, 2))

    def test_phase_event_ignored_by_chunk_callback_and_vice_versa(self) -> None:
        """Each event kind routes only to its own callback."""
        chunk_calls: list[tuple[Path, int, int]] = []
        phase_calls: list[tuple[Path, str, int, int]] = []
        ingestor = _make_ingestor()
        ingestor.on_chunk_progress = lambda fp, done, total: chunk_calls.append(
            (fp, done, total)
        )
        ingestor.on_phase_progress = lambda fp, phase, done, total: phase_calls.append(
            (fp, phase, done, total)
        )

        ingestor._handle_progress_event(("phase", "/tmp/a.txt", "extract", 1, 4))
        ingestor._handle_progress_event(("progress", "/tmp/a.txt", 1, 4))

        assert chunk_calls == [(Path("/tmp/a.txt"), 1, 4)]
        assert phase_calls == [(Path("/tmp/a.txt"), "extract", 1, 4)]

    def test_safe_phase_progress_swallow_and_guard(self) -> None:
        """_safe_phase_progress mirrors _safe_chunk_progress semantics."""
        calls: list[tuple[Path, str, int, int]] = []
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = lambda fp, phase, done, total: calls.append(
            (fp, phase, done, total)
        )
        ingestor._safe_phase_progress(Path("/tmp/a.txt"), "store", 2, 3)
        assert calls == [(Path("/tmp/a.txt"), "store", 2, 3)]

        ingestor.on_phase_progress = lambda *_: (_ for _ in ()).throw(RuntimeError)
        # Swallowed, no raise.
        ingestor._safe_phase_progress(Path("/tmp/a.txt"), "store", 3, 3)


class TestStorePhaseProgress:
    """Owner-side "store" phase ticks during MAX_MEMORY_BATCH_SIZE slices."""

    def test_store_phase_emitted_before_and_after_each_slice(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")

        # 250 documents -> 3 storage slices of MAX_MEMORY_BATCH_SIZE=100.
        documents = [{"chunk_id": f"c{n}", "text": "t"} for n in range(250)]

        def result_factory(_i):
            return {
                "success": True,
                "file_path": "fake",
                "documents": documents,
                "error": None,
            }

        phase_calls: list[tuple[Path, str, int, int]] = []
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = lambda fp, phase, done, total: phase_calls.append(
            (fp, phase, done, total)
        )
        files = [Path("/tmp/a.txt")]
        store_calls: list[int] = []
        storage = MagicMock()
        storage.store_batch.side_effect = lambda batch: (
            store_calls.append(len(batch)) or None
        )

        record = ExecutorRecord()
        monkeypatch.setattr(
            _sync,
            "ProcessPoolExecutor",
            make_fake(result_factory=result_factory, record=record),
        )

        ingestor._process_parallel_with_progress(
            files, MagicMock(), storage, 4, "process"
        )

        assert store_calls == [100, 100, 50]
        assert phase_calls == [
            (Path("/tmp/a.txt"), "store", 0, 3),
            (Path("/tmp/a.txt"), "store", 1, 3),
            (Path("/tmp/a.txt"), "store", 2, 3),
            (Path("/tmp/a.txt"), "store", 3, 3),
        ]

    def test_store_phase_not_emitted_without_on_phase_progress(self, monkeypatch):
        """With no phase consumer, storage slices still run, silently."""
        _patch_config(monkeypatch, ingest_pool="process")

        documents = [{"chunk_id": "x", "text": "hello"}]

        def result_factory(_i):
            return {
                "success": True,
                "file_path": "fake",
                "documents": documents,
                "error": None,
            }

        ingestor = _make_ingestor()
        ingestor.on_phase_progress = None
        files = [Path("/tmp/a.txt")]
        storage = MagicMock()

        record = ExecutorRecord()
        monkeypatch.setattr(
            _sync,
            "ProcessPoolExecutor",
            make_fake(result_factory=result_factory, record=record),
        )

        successful, failed, _ = ingestor._process_parallel_with_progress(
            files, MagicMock(), storage, 4, "process"
        )

        assert (successful, failed) == (1, 0)
        assert storage.store_batch.call_count == 1


class TestScrapeDoclingPagesFlag:
    """scrape_docling_pages is passed to workers only when safe."""

    def test_thread_pool_multi_worker_disables_scrape(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.pdf")]

        _, record = _run(monkeypatch, "thread", files, 4, ingestor)

        for _fn, args, _kwargs in record.constructed[0].submitted:
            assert args[-1] is False
            assert "scrape_docling_pages" not in _kwargs

    def test_thread_pool_single_worker_enables_scrape(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.pdf")]

        _, record = _run(monkeypatch, "thread", files, 1, ingestor)

        for _fn, args, _kwargs in record.constructed[0].submitted:
            assert args[-1] is True

    def test_process_pool_always_enables_scrape(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")
        ingestor = _make_ingestor()
        files = [Path("/tmp/a.pdf")]

        _, record = _run(monkeypatch, "process", files, 8, ingestor)

        for _fn, args, _kwargs in record.constructed[0].submitted:
            assert args[-1] is True
            assert "scrape_docling_pages" not in _kwargs

    def test_queue_created_for_phase_consumer_without_chunk_consumer(self, monkeypatch):
        """on_phase_progress alone must open the progress channel."""
        _patch_config(monkeypatch, ingest_pool="thread")
        ingestor = _make_ingestor()
        ingestor.on_phase_progress = lambda *_: None
        files = [Path("/tmp/a.txt")]

        _, record = _run(monkeypatch, "thread", files, 4, ingestor)

        executor = record.constructed[0]
        assert executor.submitted
        for _fn, args, _kwargs in executor.submitted:
            assert isinstance(args[3], queue.Queue)
