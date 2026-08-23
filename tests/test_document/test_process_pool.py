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
            _, _, _, progress_queue, _, cache = args
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
            _, _, _, progress_queue, _, cache = args
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
            _, _, _, progress_queue, _, cache = args
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
