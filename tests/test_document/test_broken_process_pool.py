"""Tests for BrokenProcessPool resilience in the parallel ingest loop.

Covers the archived multicore spec's 6.4 claim: when a process-pool worker
crashes hard (segfault / OOM kill), the pool loop must keep the results
already collected, mark every still-in-flight file failed with one clear
reason, shut the pool down cleanly, and return the consistent
``(success, failed, failures, skipped)`` structure instead of crashing the
whole ingest.

All scenarios use fake executors returning real
:class:`concurrent.futures.Future` objects (no OS processes spawned), mirroring
``test_process_pool.py``.
"""

from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from unittest.mock import MagicMock

from secondbrain.document import DocumentIngestor
from secondbrain.document.ingestor import _sync


def _make_ingestor(progress_callback=None):
    """Build a bare DocumentIngestor with the attributes the pool loop reads."""
    ingestor = DocumentIngestor.__new__(DocumentIngestor)
    ingestor.chunk_size = 100
    ingestor.chunk_overlap = 20
    ingestor.embedding_cache = object()
    ingestor.progress_callback = progress_callback
    ingestor.on_chunk_progress = None
    ingestor.on_phase_progress = None
    return ingestor


def _patch_config(monkeypatch, ingest_pool="process"):
    mock_cfg = MagicMock()
    mock_cfg.pdf_ocr_enabled = False
    mock_cfg.ingest_pool = ingest_pool
    mock_cfg.embedding_model = "test-model"
    monkeypatch.setattr("secondbrain.config.config", lambda: mock_cfg)
    return mock_cfg


def _broken_future() -> Future:
    """A resolved future carrying a BrokenProcessPool (crashed worker)."""
    future = Future()
    future.set_exception(BrokenProcessPool("worker process died unexpectedly"))
    return future


class _TriggerFuture(Future):
    """A resolved success future that breaks other futures when consumed.

    ``as_completed`` yields pre-resolved futures in an unspecified order, so
    the mixed scenarios keep the crash futures *pending* and have the success
    future's ``result()`` break them: the success is always accounted first,
    then the pool break surfaces.
    """

    def __init__(self, targets: list[Future], result: dict | None = None):
        super().__init__()
        self.set_result(
            result
            or {
                "success": True,
                "file_path": "fake",
                "documents": [],
                "error": None,
                "skipped": True,
            }
        )
        self._targets = targets

    def result(self, timeout=None):
        for target in self._targets:
            target.set_exception(BrokenProcessPool("worker process died unexpectedly"))
        return super().result(timeout)


class _ScriptedExecutor:
    """Fake executor that hands out a scripted future per submit call."""

    def __init__(self, futures_script=None, submit_error=None):
        self.max_workers = None
        self.submitted = 0
        self._futures_script = futures_script or []
        self._submit_error = submit_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args, **kwargs):
        if self._submit_error is not None:
            raise self._submit_error
        index = min(self.submitted, len(self._futures_script) - 1)
        self.submitted += 1
        return self._futures_script[index]


def _executor_factory(script=None, submit_error=None):
    def _cls(max_workers, **kwargs):
        return _ScriptedExecutor(futures_script=script, submit_error=submit_error)

    return _cls


def _patch_executor(monkeypatch, script=None, submit_error=None):
    fake = _executor_factory(script=script, submit_error=submit_error)
    monkeypatch.setattr(_sync, "ProcessPoolExecutor", fake)
    monkeypatch.setattr(_sync, "ThreadPoolExecutor", fake)


class TestBrokenProcessPoolMidFlight:
    """Worker crash while futures are in flight (the drain-loop path)."""

    def test_bpp_after_success_keeps_results_and_fails_in_flight(
        self, monkeypatch, caplog
    ):
        """One file completed before the crash; the rest fail exactly once."""
        _patch_config(monkeypatch, ingest_pool="process")
        # b.txt and c.txt stay pending until a.txt's result is consumed, which
        # "crashes" them — forcing the success to be accounted first,
        # deterministically, before the pool break surfaces.
        b_future = Future()
        c_future = Future()
        script = [_TriggerFuture([b_future, c_future]), b_future, c_future]
        _patch_executor(monkeypatch, script=script)

        calls = []
        ingestor = _make_ingestor(
            progress_callback=lambda fp, ok: calls.append((fp, ok))
        )
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt"), Path("/tmp/c.txt")]

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            files, MagicMock(), MagicMock(), 4, "process"
        )

        assert (successful, skipped) == (1, 1)
        assert failed == 2
        assert {path for path, _ in reasons} == {"/tmp/b.txt", "/tmp/c.txt"}
        assert all("BrokenProcessPool" in reason for _, reason in reasons)
        # Progress: a.txt True, b.txt and c.txt False (UI stays consistent).
        assert sorted(calls) == [
            (Path("/tmp/a.txt"), True),
            (Path("/tmp/b.txt"), False),
            (Path("/tmp/c.txt"), False),
        ]
        # The crash is explained at pool level, not just per file.
        assert any("pool crashed" in record.getMessage() for record in caplog.records)

    def test_bpp_on_first_future_fails_everything(self, monkeypatch):
        """Crash before any completion: all files fail, none crash the loop."""
        _patch_config(monkeypatch, ingest_pool="process")
        script = [_broken_future()]
        _patch_executor(monkeypatch, script=script)

        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt")]

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            files, MagicMock(), MagicMock(), 2, "process"
        )

        assert (successful, failed, skipped) == (0, 2, 0)
        assert {path for path, _ in reasons} == {"/tmp/a.txt", "/tmp/b.txt"}
        assert all("BrokenProcessPool" in reason for _, reason in reasons)


class TestBrokenProcessPoolAtSubmit:
    """Pool already dead when futures are submitted."""

    def test_submit_time_bpp_marks_all_files_failed(self, monkeypatch):
        _patch_config(monkeypatch, ingest_pool="process")
        _patch_executor(monkeypatch, submit_error=BrokenProcessPool("pool is broken"))

        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt"), Path("/tmp/c.txt")]

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            files, MagicMock(), MagicMock(), 2, "process"
        )

        assert (successful, failed, skipped) == (0, 3, 0)
        assert {path for path, _ in reasons} == {
            "/tmp/a.txt",
            "/tmp/b.txt",
            "/tmp/c.txt",
        }
        assert all("BrokenProcessPool" in reason for _, reason in reasons)


class TestBrokenProcessPoolResultShape:
    """The returned structure stays consistent for the ingest() contract."""

    def test_mixed_success_and_crash_is_consistent(self, monkeypatch):
        """Success + failed + skipped accounts for every file exactly once."""
        _patch_config(monkeypatch, ingest_pool="process")
        storage = MagicMock()
        doc = {"chunk_id": "c1", "chunk_text": "text", "text_hash": "h1"}
        stored_future = Future()
        stored_future.set_result(
            {
                "success": True,
                "file_path": "fake",
                "documents": [doc],
                "error": None,
                "skipped": False,
            }
        )
        b_future = Future()
        c_future = Future()
        # a.txt stores real documents (exercises storage.store_batch); its
        # consumption then "crashes" b.txt and c.txt. The ordered executor
        # hands the success trigger out on the first submit; the scripted
        # success/broken futures for the other submits stay unused padding.
        script = [stored_future, b_future, c_future]

        class _OrderedExecutor(_ScriptedExecutor):
            def submit(self, fn, *args, **kwargs):
                if self.submitted == 0:
                    self.submitted += 1
                    return _TriggerFuture(
                        [b_future, c_future],
                        result={
                            "success": True,
                            "file_path": "fake",
                            "documents": [doc],
                            "error": None,
                            "skipped": False,
                        },
                    )
                return super().submit(fn, *args, **kwargs)

        def fake(max_workers, **kwargs):
            return _OrderedExecutor(futures_script=script)

        monkeypatch.setattr(_sync, "ProcessPoolExecutor", fake)
        monkeypatch.setattr(_sync, "ThreadPoolExecutor", fake)

        ingestor = _make_ingestor()
        files = [Path("/tmp/a.txt"), Path("/tmp/b.txt"), Path("/tmp/c.txt")]

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            files, MagicMock(), storage, 4, "process"
        )

        assert successful + failed + skipped == len(files)
        assert (successful, failed, skipped) == (1, 2, 0)
        # The completed file was stored before the crash; the broken ones were not.
        assert storage.store_batch.call_count == 1
        assert len(reasons) == failed
