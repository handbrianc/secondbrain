"""Tests for multicore parallel execution verification."""
import pytest
from multiprocessing import Pool, cpu_count
import time
from pathlib import Path
import tempfile


def _process_file(path):
    """Worker function for parallel processing."""
    time.sleep(0.1)  # Simulate work
    return True


class TestMulticoreParallel:
    """Test parallel execution across multiple cores."""

    def test_parallel_execution_speedup(self):
        """Multiple cores process faster than single core."""
        num_files = 10
        files = [f"file_{i}.txt" for i in range(num_files)]
        
        # Sequential processing
        start = time.time()
        for f in files:
            _process_file(f)
        sequential_time = time.time() - start
        
        # Parallel processing with 4 cores
        start = time.time()
        with Pool(processes=4) as pool:
            pool.map(_process_file, files)
        parallel_time = time.time() - start
        
        # Parallel should be significantly faster (not just linear)
        # Allow for some overhead in test environment
        assert parallel_time < sequential_time * 0.8, \
            f"Parallel ({parallel_time:.2f}s) should be faster than sequential ({sequential_time:.2f}s)"

    def test_all_files_processed(self):
        """All files are processed successfully in parallel."""
        num_files = 20
        files = [f"file_{i}.txt" for i in range(num_files)]
        
        with Pool(processes=4) as pool:
            results = pool.map(_process_file, files)
        
        assert len(results) == num_files
        assert all(results)
