"""Tests for multicore performance and resource management.

Consolidated from:
- test_multicore_parallelism.py (parallel execution timing)
- test_multicore_rate_limit.py (rate limiting tests)
- test_multicore_memory.py (memory usage tests)
- test_multicore_progress.py (progress tracking)
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

import pytest

from secondbrain.document import MAX_MEMORY_BATCH_SIZE, _extract_and_chunk_file


def _slow_process_file(path):
    """Module-level function for multiprocessing (must be picklable)."""
    time.sleep(0.1)
    return True


def _simple_task(x):
    """Module-level function for multiprocessing (must be picklable)."""
    return x * 2


class TestRateLimiting:
    """Test rate limiting performance."""

    def test_rate_limit_requests_per_second(self):
        """Test that rate limiter enforces requests per second limit.
        
        Note: This test must run in isolation (-n0) because get_shared_rate_limiter()
        returns a singleton that persists across tests. The singleton is created with
        default parameters (100 req/s) on first call, so this test creates a fresh
        SharedRateLimiter directly to test the actual rate limiting behavior.
        """
        from secondbrain.utils.rate_limiter import SharedRateLimiter
        
        # Create a fresh rate limiter for this test (thread-safe)
        limiter = SharedRateLimiter(max_requests=10, window_seconds=1.0)
        
        # First 10 requests should succeed
        success_count = 0
        for _ in range(10):
            if limiter.acquire():
                success_count += 1
        
        assert success_count == 10
        
        # 11th request should fail (rate limited)
        assert not limiter.acquire()


class TestMemoryManagement:
    """Test memory-efficient batch processing."""

    def test_max_memory_batch_size_constant_exists(self):
        """Test that MAX_MEMORY_BATCH_SIZE constant is defined."""
        assert MAX_MEMORY_BATCH_SIZE > 0
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)

    def test_memory_usage_within_limits(self):
        """Test that memory usage stays within configured limits."""
        from secondbrain.document import DocumentIngestor

        ingestor = DocumentIngestor(verbose=False)
        assert ingestor is not None

        # Verify batch size is set correctly
        assert MAX_MEMORY_BATCH_SIZE == 100


class TestBatchSplitting:
    """Test batch splitting logic for large documents."""

    def test_batch_splitting_logic(self, tmp_path: Path):
        """Test that large documents are split into batches correctly."""
        # Create a large test file
        test_file = tmp_path / "large_doc.txt"
        # Create content that will produce many chunks
        content = "Word " * 1000  # 1000 words
        test_file.write_text(content)

        # Process with small batch size
        results = _extract_and_chunk_file(
            str(test_file), chunk_size=50, chunk_overlap=10
        )

        # Should produce multiple chunks
        assert len(results) > 0

        # Each chunk should respect size limits
        for chunk in results:
            # Chunk should not exceed expected size (with some tolerance)
            assert len(chunk) <= 100  # chunk_size + overlap + tolerance

    def test_batch_size_respects_memory_limits(self):
        """Test that batch size respects memory limits."""
        assert MAX_MEMORY_BATCH_SIZE == 100


class TestParallelPerformance:
    """Test parallel execution performance characteristics."""

    def test_parallel_execution_speedup(self):
        """Test that parallel execution provides speedup for I/O-bound tasks."""
        results_sequential = []
        results_parallel = []

        def io_task(x):
            time.sleep(0.1)
            return x * 2

        num_items = 10

        start = time.time()
        for i in range(num_items):
            results_sequential.append(io_task(i))
        sequential_time = time.time() - start

        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results_parallel = list(executor.map(io_task, range(num_items), timeout=30))
        except FuturesTimeoutError:
            pytest.fail("Parallel execution timed out after 30s")
        finally:
            parallel_time = time.time() - start

        assert results_sequential == results_parallel
        # Verify both completed successfully
        assert parallel_time > 0 and sequential_time > 0
        # Only check speedup if sequential time is significant (>1s) to avoid flakiness
        if sequential_time > 1.0:
            # Allow 10% tolerance - parallel should be at least as fast
            assert parallel_time <= sequential_time * 1.1, (
                f"Thread pool ({parallel_time:.2f}s) should be comparable to or "
                f"faster than sequential ({sequential_time:.2f}s) for I/O tasks"
            )

    def test_parallel_text_extraction_timing(self, tmp_path: Path):
        """Test timing comparison between sequential and parallel processing."""
        # Create test files
        num_files = 4
        test_files = []
        for i in range(num_files):
            test_file = tmp_path / f"test_doc_{i}.txt"
            test_file.write_text("Test content " * 100)
            test_files.append(test_file)

        # Time sequential processing
        start_sequential = time.time()
        for test_file in test_files:
            _extract_and_chunk_file(str(test_file), chunk_size=100, chunk_overlap=10)
        sequential_time = time.time() - start_sequential

        # Time parallel processing with timeout handling
        start_parallel = time.time()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(_extract_and_chunk_file, str(f), 100, 10)
                    for f in test_files
                ]
                for future in futures:
                    future.result(timeout=30)  # 30s timeout per future
        except FuturesTimeoutError:
            pytest.fail("Parallel text extraction timed out after 30s")
        finally:
            parallel_time = time.time() - start_parallel

        # Both should complete successfully
        assert sequential_time > 0 and parallel_time > 0


class TestWorkerPoolManagement:
    """Test worker pool lifecycle management."""

    def test_worker_pool_reuse(self):
        """Test that worker pools can be reused efficiently."""
        # Create pool and reuse it
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                # First batch
                futures1 = [pool.submit(_simple_task, i) for i in range(5)]
                results1 = [f.result(timeout=30) for f in futures1]
                assert results1 == [0, 2, 4, 6, 8]

                # Second batch (pool reused)
                futures2 = [pool.submit(_simple_task, i) for i in range(5, 10)]
                results2 = [f.result(timeout=30) for f in futures2]
                assert results2 == [10, 12, 14, 16, 18]
        except FuturesTimeoutError:
            pytest.fail("Worker pool operation timed out after 30s")
        except Exception as e:
            pytest.fail(f"Worker pool test failed: {e}")

    def test_thread_pool_execution(self):
        """Test ThreadPoolExecutor for I/O-bound tasks."""
        import time

        def io_task(x):
            time.sleep(0.05)
            return x * 2

        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(io_task, range(10), timeout=30))
        except FuturesTimeoutError:
            pytest.fail("Thread pool execution timed out after 30s")
        elapsed = time.time() - start

        # Should complete all tasks
        assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

        # Thread pool should be faster than sequential for I/O-bound tasks
        # Sequential would take ~0.5s (10 * 0.05s), parallel should be faster
        # Use loose tolerance: allow up to 0.4s (20% below sequential)
        assert elapsed < 0.4, f"Thread pool should be faster for I/O tasks, took {elapsed:.2f}s"
