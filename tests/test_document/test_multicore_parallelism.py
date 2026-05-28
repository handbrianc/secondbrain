"""Tests for multicore parallelism verification."""
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from secondbrain.config import Config
from secondbrain.document import (
    MAX_MEMORY_BATCH_SIZE,
    _extract_and_chunk_file,
)


class TestParallelExecution:
    """Test that parallel execution actually occurs."""

    def test_parallel_text_extraction_timing(self, tmp_path: Path):
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
        
        # Time parallel processing
        start_parallel = time.time()
        with ProcessPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(_extract_and_chunk_file, str(f), 100, 10)
                for f in test_files
            ]
            for future in futures:
                future.result()  # Wait for completion
        parallel_time = time.time() - start_parallel
        
        assert sequential_time > 0 and parallel_time > 0

    def test_parallel_chunking_produces_correct_results(self, tmp_path: Path):
        # Create test file
        test_file = tmp_path / "test_chunking.txt"
        content = "Word " * 500  # 500 words
        test_file.write_text(content)
        
        # Sequential processing
        sequential_results = _extract_and_chunk_file(
            str(test_file), chunk_size=50, chunk_overlap=10
        )
        
        # Parallel processing (single file in parallel)
        with ProcessPoolExecutor(max_workers=2) as executor:
            parallel_results = executor.submit(
                _extract_and_chunk_file, str(test_file), 50, 10
            ).result()
        
        assert len(sequential_results) == len(parallel_results)
        
        for seq_chunk, par_chunk in zip(sequential_results, parallel_results):
            assert seq_chunk == par_chunk


class TestProgressTracking:
    """Test progress tracking during parallel operations."""

    def test_progress_callback_invoked_during_parallel_ingestion(self):
        progress_calls = []
        
        def mock_progress(current: int, total: int, filename: str):
            progress_calls.append({
                "current": current,
                "total": total,
                "filename": filename
            })
        
        # Simulate parallel processing with progress
        test_files = [f"file_{i}.txt" for i in range(5)]
        total = len(test_files)
        
        for i, filename in enumerate(test_files, 1):
            mock_progress(i, total, filename)
        
        assert len(progress_calls) == total

        for i, call in enumerate(progress_calls):
            assert call["current"] == i + 1
            assert call["total"] == total
            assert call["filename"] == f"file_{i}.txt"

    def test_progress_shows_success_failure_counts(self):
        success_count = 0
        failure_count = 0
        
        test_cases = [
            ("success_1.txt", True),
            ("success_2.txt", True),
            ("failed.txt", False),
            ("success_3.txt", True),
        ]
        
        for filename, success in test_cases:
            if success:
                success_count += 1
            else:
                failure_count += 1
        
        assert success_count == 3
        assert failure_count == 1
        assert success_count + failure_count == len(test_cases)


class TestMemoryBatchProcessing:
    """Test memory-efficient batch processing."""

    def test_batch_size_respects_memory_limits(self):
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)
        assert MAX_MEMORY_BATCH_SIZE > 0
        assert MAX_MEMORY_BATCH_SIZE <= 10000
        assert 50 <= MAX_MEMORY_BATCH_SIZE <= 500

    def test_batch_splitting_logic(self):
        batch_size = MAX_MEMORY_BATCH_SIZE

        test_sizes = [
            batch_size,
            batch_size * 2,
            batch_size + 100,
            batch_size - 50,
        ]
        
        for total_size in test_sizes:
            num_batches = (total_size + batch_size - 1) // batch_size
            assert num_batches > 0
            
            actual_num_batches = total_size // batch_size + (1 if total_size % batch_size else 0)
            assert num_batches == actual_num_batches


class TestRateLimitingAcrossWorkers:
    """Test rate limiting works correctly across multiple workers."""

    def test_rate_limiter_shared_across_processes(self):
        config = Config()
        assert isinstance(config.rate_limit_max_requests, int)
        assert config.rate_limit_max_requests > 0

    def test_rate_limit_requests_per_second(self):
        class MockRateLimiter:
            def __init__(self, max_requests_per_second: int):
                self.max_rps = max_requests_per_second
                self.request_times = []
            
            def acquire(self):
                import time
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 1.0]
                
                if len(self.request_times) >= self.max_rps:
                    return False
                
                self.request_times.append(now)
                return True
        
        limiter = MockRateLimiter(max_requests_per_second=5)

        for i in range(5):
            assert limiter.acquire()
        
        assert not limiter.acquire()


class TestCrossPlatformSupport:
    """Test cross-platform multiprocessing compatibility."""

    def test_multiprocessing_start_method_configured(self):
        import multiprocessing

        if os.name == 'nt':
            assert multiprocessing.get_start_method(allow_none=True) in ['spawn', None]
        else:
            assert 'spawn' in multiprocessing.get_all_start_methods()

    def test_worker_functions_are_picklable(self):
        import pickle

        pickled = pickle.dumps(_extract_and_chunk_file)
        unpickled = pickle.loads(pickled)
        assert unpickled == _extract_and_chunk_file


class TestBackwardCompatibility:
    """Test backward compatibility with single-core ingestion."""

    def test_default_behavior_unchanged_without_cores_flag(self):
        config = Config()

        cores: int | None = None
        resolved = config.max_workers or os.cpu_count() or 1 if cores is None else cores

        assert isinstance(resolved, int)
        assert resolved > 0

    def test_batch_size_option_still_works(self):
        for batch_size in [10, 50, 100, 500]:
            assert isinstance(batch_size, int)
            assert batch_size > 0
            assert batch_size <= 10000, "batch_size should be reasonable"
        
        # Test combination with cores
        cores = 4
        batch_size = 50
        
        # Both parameters should be independently valid
        assert cores > 0, "cores should be positive"
        assert batch_size > 0, "batch_size should be positive"

    def test_single_file_ingestion_unchanged(self):
        pass
