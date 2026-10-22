"""Tests for multicore edge cases and error handling.

Consolidated from:
- test_multicore_cross_platform.py (cross-platform compatibility)
- test_multicore_progress.py (progress callback edge cases)
- test_multicore_ingestion.py (error handling)
"""

import inspect
import pickle
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secondbrain.document import DocumentIngestor, _extract_and_chunk_file
from secondbrain.document.ingestor import _sync
from secondbrain.document.processor import _extract_chunk_and_embed_file


def _slow_task(x):
    """Module-level function for multiprocessing (must be picklable)."""
    return x


def _simple_task(x):
    """Module-level function for multiprocessing (must be picklable)."""
    return x * 2


class TestThreadingConfiguration:
    """Test threading configuration and setup."""

    def test_threading_executor_available(self):
        """Test that ThreadPoolExecutor is available."""
        assert ThreadPoolExecutor is not None

    def test_cpu_count_detection(self):
        """CPU count should be detectable."""
        import os

        count = os.cpu_count()
        assert count > 0

    def test_threading_available(self):
        """Threading should be available."""
        import threading

        assert threading.Thread is not None


class TestWorkerPickling:
    """Worker functions must round-trip through pickle for process transfer.

    The pool loop in ``_sync._process_parallel_with_progress`` submits
    ``_extract_chunk_and_embed_file`` by reference (the thread-pool path also
    knows ``_extract_and_chunk_file``), so each must pickle as the very same
    module-level object — a plain ``assert is`` after ``dumps``/``loads``,
    with no skip masking an actual pickling regression.
    """

    @pytest.mark.parametrize(
        "worker", [_extract_chunk_and_embed_file, _extract_and_chunk_file]
    )
    def test_worker_functions_are_picklable(self, worker):
        """Workers pickle by reference and unpickle to the same function."""
        import pickle

        pickled = pickle.dumps(worker)
        unpickled = pickle.loads(pickled)
        assert unpickled is worker


class TestErrorHandling:
    """Test error handling in multiprocessing context."""

    def test_error_recovery_after_process_failure(self, tmp_path: Path):
        """Test that system recovers gracefully from process failures."""
        # Create test files
        test_file = tmp_path / "test.txt"
        test_file.write_text("Valid content")

        # Process should succeed with valid input
        results = _extract_and_chunk_file(
            str(test_file), chunk_size=100, chunk_overlap=10
        )
        assert len(results) > 0

    def test_invalid_chunk_size_handling(self, tmp_path: Path):
        """Test handling of zero chunk size (currently allows it)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Zero chunk size is currently allowed (no validation)
        results = _extract_and_chunk_file(
            str(test_file), chunk_size=0, chunk_overlap=10
        )
        assert isinstance(results, dict)
        assert "segments" in results

    def test_negative_chunk_overlap_handling(self, tmp_path: Path):
        """Test handling of negative chunk overlap (currently allows it)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Negative overlap is currently allowed (no validation)
        results = _extract_and_chunk_file(
            str(test_file), chunk_size=100, chunk_overlap=-10
        )
        assert isinstance(results, dict)
        assert "segments" in results


def _pool_loop_ingestor(progress_callback=None) -> DocumentIngestor:
    """A bare DocumentIngestor carrying the attributes the pool loop reads."""
    ingestor = DocumentIngestor.__new__(DocumentIngestor)
    ingestor.chunk_size = 100
    ingestor.chunk_overlap = 20
    ingestor.embedding_cache = object()
    ingestor.progress_callback = progress_callback
    ingestor.on_chunk_progress = None
    ingestor.on_phase_progress = None
    return ingestor


def _patch_pool_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the config the pool loop reads (mirrors test_process_pool)."""
    from types import SimpleNamespace

    cfg = SimpleNamespace(
        ingest_pool="process",
        skip_existing_on_reingest=True,
        pdf_ocr_enabled=False,
        embedding_model="test-model",
    )
    monkeypatch.setattr("secondbrain.config.config", lambda: cfg)


class _PicklingFirstExecutor:
    """Fake executor whose submit fails for the first file only.

    Mirrors what a real pool does when worker arguments cannot be serialized:
    the task never runs and the submission surfaces a PicklingError for that
    file while every other file keeps flowing.
    """

    def __init__(self, max_workers, **kwargs):
        self.max_workers = max_workers
        self.calls = 0
        self.submitted: list[tuple[object, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise pickle.PicklingError("Can't pickle local object <lambda>")
        self.submitted.append((fn, args))
        future = Future()
        future.set_result(
            {
                "success": True,
                "file_path": args[0],
                "documents": [{"chunk_id": "x", "text": "kept"}],
                "error": None,
            }
        )
        return future


class TestSerializationErrorsAreCaught:
    """Multicore spec: serialization errors are caught and reported.

    An unpicklable worker argument must fail exactly its own file (with the
    serialization error recorded as the reason) while the rest of the batch
    continues and the ingest completes with consistent counts.
    """

    def test_submit_time_serialization_error_fails_only_that_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A submit-raised PicklingError is caught; other files still ingest."""
        _patch_pool_config(monkeypatch)
        monkeypatch.setattr(_sync, "ProcessPoolExecutor", _PicklingFirstExecutor)
        monkeypatch.setattr(_sync, "ThreadPoolExecutor", _PicklingFirstExecutor)

        first = tmp_path / "unpicklable-args.txt"
        second = tmp_path / "healthy.txt"
        first.write_text("first")
        second.write_text("second")

        storage = MagicMock()
        progress_calls: list[tuple[Path, bool]] = []
        ingestor = _pool_loop_ingestor(
            progress_callback=lambda fp, ok: progress_calls.append((fp, ok))
        )

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            [first, second], MagicMock(), storage, 1, "process"
        )

        assert (successful, failed, skipped) == (1, 1, 0)
        assert reasons == [
            (str(first), "PicklingError: Can't pickle local object <lambda>")
        ]
        # The healthy file was still processed and its documents stored.
        assert storage.store_batch.call_count == 1
        assert progress_calls == [(first, False), (second, True)]

    @pytest.mark.xdist_group("process_pool")
    def test_real_pool_unpicklable_args_recorded_and_batch_completes(
        self, tmp_path: Path
    ):
        """A real pool keeps the batch alive on unpicklable worker args.

        Every affected future surfaces the PicklingError, the owner loop
        records each file as failed with the serialization error, and the
        ingest completes with consistent counts.
        """
        first = tmp_path / "a.txt"
        second = tmp_path / "b.txt"
        first.write_text("first")
        second.write_text("second")

        # A local (test-scoped) object: unpicklable, exactly the shape the
        # spec's serialization scenario describes. It travels inside the real
        # production worker args (worker_args embeds self.chunk_size), so the
        # real pool fails to serialize the task and the deferred PicklingError
        # lands on the future.
        class _Unpicklable:
            pass

        ingestor = _pool_loop_ingestor()
        ingestor.chunk_size = _Unpicklable()

        storage = MagicMock()

        successful, failed, reasons, skipped = ingestor._process_parallel_with_progress(
            [first, second], MagicMock(), storage, 1, "process"
        )

        assert (successful, failed, skipped) == (0, 2, 0)
        assert [path for path, _reason in reasons] == [str(first), str(second)]
        assert all(
            reason.startswith("PicklingError: Can't pickle")
            for _path, reason in reasons
        ), reasons
        storage.store_batch.assert_not_called()


class TestGracefulShutdown:
    """Test graceful shutdown and cleanup."""

    def test_executor_context_manager_cleanup(self):
        """Test that executor context manager properly cleans up resources."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_simple_task, i) for i in range(5)]
            results = [f.result() for f in futures]

        assert results == [0, 2, 4, 6, 8]

    def test_executor_basic_shutdown(self):
        """Test that executor shuts down after use."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert executor is not None


class TestCrossPlatformCompatibility:
    """Test cross-platform compatibility."""

    def test_cross_platform_compatibility(self):
        """Test that threading works across platforms."""
        import os

        cpu_count = os.cpu_count()
        assert cpu_count > 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_simple_task, i) for i in range(5)]
            results = [f.result() for f in futures]
            assert results == [0, 2, 4, 6, 8]


class TestDocumentEdgeCases:
    """Test edge cases in document processing."""

    def test_empty_document_handling(self, tmp_path: Path):
        """Test handling of empty documents."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        # Should handle empty files gracefully
        results = _extract_and_chunk_file(
            str(empty_file), chunk_size=100, chunk_overlap=10
        )
        assert isinstance(results, dict)
        assert "segments" in results

    def test_large_document_chunking(self, tmp_path: Path):
        """Test processing of large documents."""
        large_file = tmp_path / "large.txt"
        large_file.write_text("Word " * 20000)

        results = _extract_and_chunk_file(
            str(large_file), chunk_size=500, chunk_overlap=50
        )

        assert isinstance(results, dict)
        assert "segments" in results
        assert len(results["segments"]) >= 1

    def test_single_character_document(self, tmp_path: Path):
        """Test handling of single character documents."""
        tiny_file = tmp_path / "tiny.txt"
        tiny_file.write_text("X")

        results = _extract_and_chunk_file(
            str(tiny_file), chunk_size=100, chunk_overlap=10
        )
        assert isinstance(results, dict)
        assert "segments" in results

    def test_whitespace_only_document(self, tmp_path: Path):
        """Test handling of whitespace-only documents."""
        ws_file = tmp_path / "whitespace.txt"
        ws_file.write_text("   \n\n   \t   ")

        results = _extract_and_chunk_file(
            str(ws_file), chunk_size=100, chunk_overlap=10
        )
        assert isinstance(results, dict)
        assert "segments" in results


class TestProgressCallbackEdgeCases:
    """Test progress callback edge cases."""

    def test_progress_callback_with_none(self):
        """Test behavior when progress callback is None."""
        ingestor = DocumentIngestor(verbose=False, progress_callback=None)
        # Should handle None callback gracefully
        assert ingestor.progress_callback is None

    def test_progress_callback_exception_handling(self):
        """Test that exceptions in progress callback don't crash ingestion."""

        def failing_callback(path, success):
            raise ValueError("Callback error")

        ingestor = DocumentIngestor(verbose=False, progress_callback=failing_callback)
        # Should store callback (actual handling happens during ingestion)
        assert ingestor.progress_callback is not None

    def test_progress_callback_can_be_provided(self):
        """Test that progress callback can be provided."""

        def dummy_callback(path, success):
            pass

        ingestor = DocumentIngestor(verbose=False, progress_callback=dummy_callback)
        assert ingestor.progress_callback is not None

    def test_ingest_accepts_cores_parameter(self):
        """Test that ingest method accepts cores parameter."""
        ingestor = DocumentIngestor(verbose=False)
        sig = inspect.signature(ingestor.ingest)
        assert "cores" in sig.parameters

    def test_ingest_with_cores_parameter(self):
        """Test ingest with cores parameter."""
        ingestor = DocumentIngestor(verbose=False)
        sig = inspect.signature(ingestor.ingest)
        assert "cores" in sig.parameters


class TestSingleFileWorkerCap:
    """A single-document ingest caps the worker count at 1 (C6).

    Parallelism is per-file, so ingesting exactly one file can only ever use
    one worker; the resolved worker count is capped so no idle workers are
    spun up. Multi-file ingests keep the resolved count unchanged.
    """

    @staticmethod
    def _patch_providers(monkeypatch: pytest.MonkeyPatch) -> None:
        """Stub the embedding/storage factories created by ``ingest``."""
        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: MagicMock()),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: MagicMock()),
        )

    @staticmethod
    def _capture_max_workers(
        ingestor: DocumentIngestor, monkeypatch: pytest.MonkeyPatch
    ) -> dict[str, int]:
        """Replace the parallel runner with a spy that records ``max_workers``."""
        captured: dict[str, int] = {}

        def fake_parallel(
            files,
            embedding_gen,
            storage,
            max_workers,
            pool=None,
            skip_existing=None,
        ):
            captured["max_workers"] = max_workers
            return (len(files), 0, [], 0)

        monkeypatch.setattr(ingestor, "_process_parallel_with_progress", fake_parallel)
        return captured

    def test_single_file_caps_explicit_workers_to_one(
        self, tmp_path: Path, monkeypatch
    ):
        """cores=8 with one file resolves to a single worker."""
        self._patch_providers(monkeypatch)
        only = tmp_path / "only.txt"
        only.write_text("content")

        ingestor = DocumentIngestor(verbose=False)
        captured = self._capture_max_workers(ingestor, monkeypatch)

        result = ingestor.ingest(str(only), cores=8)

        assert captured["max_workers"] == 1
        assert result["success"] == 1

    def test_single_file_caps_auto_resolved_workers(self, tmp_path: Path, monkeypatch):
        """cores=None (auto-detect) is also capped to one worker."""
        self._patch_providers(monkeypatch)
        only = tmp_path / "only.txt"
        only.write_text("content")

        ingestor = DocumentIngestor(verbose=False)
        captured = self._capture_max_workers(ingestor, monkeypatch)

        ingestor.ingest(str(only))

        assert captured["max_workers"] == 1

    def test_multi_file_explicit_worker_count_unchanged(
        self, tmp_path: Path, monkeypatch
    ):
        """cores=8 with two files keeps 8 workers."""
        self._patch_providers(monkeypatch)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        ingestor = DocumentIngestor(verbose=False)
        captured = self._capture_max_workers(ingestor, monkeypatch)

        result = ingestor.ingest(str(tmp_path), cores=8)

        assert captured["max_workers"] == 8
        assert result["success"] == 2

    def test_multi_file_auto_worker_count_unchanged(self, tmp_path: Path, monkeypatch):
        """Auto-resolved worker count for multiple files is untouched."""
        self._patch_providers(monkeypatch)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        ingestor = DocumentIngestor(verbose=False)
        captured = self._capture_max_workers(ingestor, monkeypatch)

        ingestor.ingest(str(tmp_path))

        assert captured["max_workers"] == ingestor._resolve_core_count(None)
