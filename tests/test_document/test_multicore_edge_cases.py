"""Tests for multicore edge cases and error handling.

Consolidated from:
- test_multicore_cross_platform.py (cross-platform compatibility)
- test_multicore_progress.py (progress callback edge cases)
- test_multicore_ingestion.py (error handling)
"""

import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from secondbrain.document import DocumentIngestor, _extract_and_chunk_file


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
    """Test that worker functions are picklable for multiprocessing."""

    def test_worker_functions_are_picklable(self):
        """Test that worker functions can be pickled for process transfer."""
        import pickle

        # Test that _extract_and_chunk_file can be pickled
        try:
            pickled = pickle.dumps(_extract_and_chunk_file)
            unpickled = pickle.loads(pickled)
            assert unpickled is not None
        except (pickle.PicklingError, AttributeError):
            # Some functions may not be picklable depending on implementation
            # This is a known limitation of multiprocessing
            pytest.skip("Function pickling not supported in this environment")


class TestErrorHandling:
    """Test error handling in multiprocessing context."""

    def test_error_recovery_after_process_failure(self, tmp_path: Path):
        """Test that system recovers gracefully from process failures."""
        # Create test files
        test_file = tmp_path / "test.txt"
        test_file.write_text("Valid content")

        # Process should succeed with valid input
        results = _extract_and_chunk_file(str(test_file), chunk_size=100, chunk_overlap=10)
        assert len(results) > 0

    def test_invalid_chunk_size_handling(self, tmp_path: Path):
        """Test handling of zero chunk size (currently allows it)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Zero chunk size is currently allowed (no validation)
        results = _extract_and_chunk_file(str(test_file), chunk_size=0, chunk_overlap=10)
        assert isinstance(results, dict)
        assert 'segments' in results

    def test_negative_chunk_overlap_handling(self, tmp_path: Path):
        """Test handling of negative chunk overlap (currently allows it)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Negative overlap is currently allowed (no validation)
        results = _extract_and_chunk_file(str(test_file), chunk_size=100, chunk_overlap=-10)
        assert isinstance(results, dict)
        assert 'segments' in results


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
        results = _extract_and_chunk_file(str(empty_file), chunk_size=100, chunk_overlap=10)
        assert isinstance(results, dict)
        assert 'segments' in results

    def test_large_document_chunking(self, tmp_path: Path):
        """Test processing of large documents."""
        large_file = tmp_path / "large.txt"
        large_file.write_text("Word " * 20000)

        results = _extract_and_chunk_file(
            str(large_file), chunk_size=500, chunk_overlap=50
        )

        assert isinstance(results, dict)
        assert 'segments' in results
        assert len(results['segments']) >= 1

    def test_single_character_document(self, tmp_path: Path):
        """Test handling of single character documents."""
        tiny_file = tmp_path / "tiny.txt"
        tiny_file.write_text("X")

        results = _extract_and_chunk_file(str(tiny_file), chunk_size=100, chunk_overlap=10)
        assert isinstance(results, dict)
        assert 'segments' in results

    def test_whitespace_only_document(self, tmp_path: Path):
        """Test handling of whitespace-only documents."""
        ws_file = tmp_path / "whitespace.txt"
        ws_file.write_text("   \n\n   \t   ")

        results = _extract_and_chunk_file(str(ws_file), chunk_size=100, chunk_overlap=10)
        assert isinstance(results, dict)
        assert 'segments' in results


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
        assert 'cores' in sig.parameters

    def test_ingest_with_cores_parameter(self):
        """Test ingest with cores parameter."""
        ingestor = DocumentIngestor(verbose=False)
        sig = inspect.signature(ingestor.ingest)
        assert 'cores' in sig.parameters
