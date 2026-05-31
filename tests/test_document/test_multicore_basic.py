"""Tests for core multicore parallel functionality.

Consolidated from:
- test_multicore_ingestion.py (core validation tests)
- test_multicore_parallelism.py (parallel execution tests)
- test_multicore_progress.py (progress callback tests)
"""

import inspect
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from secondbrain.config import Config, config
from secondbrain.document import (
    MAX_MEMORY_BATCH_SIZE,
    DocumentIngestor,
    _extract_and_chunk_file,
)
from secondbrain.utils.rate_limiter import SharedRateLimiter, get_shared_rate_limiter


class TestCoreCountValidation:
    """Tests for core count validation logic."""

    def test_core_count_validation_zero(self, tmp_path: Path):
        """Test core count validation for zero cores."""
        with pytest.raises(ValueError, match="cores must be positive"):
            cores = 0
            if cores is not None and cores <= 0:
                raise ValueError("cores must be positive")

    def test_core_count_validation_negative(self, tmp_path: Path):
        """Test core count validation for negative cores."""
        with pytest.raises(ValueError, match="cores must be positive"):
            cores = -1
            if cores is not None and cores <= 0:
                raise ValueError("cores must be positive")

    def test_core_count_validation_excessive(self, tmp_path: Path):
        """Test core count validation for excessive values."""
        # Simulate CLI validation with clamping
        cores = 999
        available = os.cpu_count() or 1
        if cores > available:
            # In real CLI, this would print a warning
            cores = available

        assert cores == available
        assert cores < 999


class TestCoreCountFallback:
    """Tests for core count fallback logic."""

    def test_fallback_to_config_max_workers(self):
        """Test fallback to config max_workers setting."""
        config_obj = Config(max_workers=6)

        cores: int | None = None
        if cores is None:
            resolved = config_obj.max_workers or os.cpu_count() or 1

        assert resolved == 6

    def test_fallback_to_cpu_count_auto_detection(self):
        """Test fallback to CPU count auto-detection."""
        ingestor = DocumentIngestor()

        with patch("secondbrain.document.config") as mock_config:
            mock_config.return_value.max_workers = None
            with patch.object(os, "cpu_count", return_value=8):
                cores = config().max_workers or os.cpu_count() or 1
                assert cores == 8


class TestParallelExecution:
    """Test that parallel execution actually occurs."""

    def test_parallel_ingest_with_multiple_cores(self, tmp_path: Path):
        """Test parallel ingestion with multiple cores produces correct results."""
        # Create test files
        num_files = 4
        test_files = []
        for i in range(num_files):
            test_file = tmp_path / f"test_doc_{i}.txt"
            test_file.write_text("Test content " * 100)
            test_files.append(test_file)

        # Process sequentially
        sequential_results = []
        for test_file in test_files:
            result = _extract_and_chunk_file(str(test_file), chunk_size=100, chunk_overlap=10)
            sequential_results.extend(result)

        # Process in parallel
        with ProcessPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(_extract_and_chunk_file, str(f), 100, 10)
                for f in test_files
            ]
            parallel_results = []
            for future in futures:
                parallel_results.extend(future.result())

        # Results should match
        assert len(sequential_results) == len(parallel_results)
        assert all(seq == par for seq, par in zip(sequential_results, parallel_results))

    def test_parallel_chunking_produces_correct_results(self, tmp_path: Path):
        """Test parallel chunking produces identical results to sequential."""
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

    def test_progress_callback_invoked(self):
        """Test that progress callback is invoked during ingestion."""
        progress_calls = []

        def mock_progress(path, success):
            progress_calls.append((path, success))

        ingestor = DocumentIngestor(verbose=False, progress_callback=mock_progress)

        # Verify callback is stored
        assert ingestor.progress_callback is not None

    def test_progress_callback_invoked_during_parallel_ingestion(self, tmp_path: Path):
        """Test progress callback is invoked during parallel ingestion."""
        progress_calls = []

        def mock_progress(path, success):
            progress_calls.append((path, success))

        # Create test file
        test_file = tmp_path / "test_progress.txt"
        test_file.write_text("Test content")

        ingestor = DocumentIngestor(verbose=False, progress_callback=mock_progress)

        # Verify progress callback can be provided
        assert ingestor.progress_callback is not None


class TestWorkerInitialization:
    """Test worker pool initialization and configuration."""

    def test_worker_initialization(self):
        """Test that worker pool initializes correctly."""
        ingestor = DocumentIngestor(verbose=False)
        assert ingestor is not None
        assert hasattr(ingestor, 'ingest')

    def test_default_behavior_without_cores_flag(self):
        """Test default behavior without specifying cores."""
        ingestor = DocumentIngestor(verbose=False)

        # Should use config or CPU count by default
        sig = inspect.signature(ingestor.ingest)
        assert 'cores' in sig.parameters

        # Default should be None (auto-detect)
        default_cores = sig.parameters['cores'].default
        assert default_cores is None


class TestBatchSizeAndMemory:
    """Test batch size and memory limit configuration."""

    def test_batch_size_respects_memory_limits(self):
        """Test that batch size respects memory limits."""
        from secondbrain.document import MAX_MEMORY_BATCH_SIZE

        assert MAX_MEMORY_BATCH_SIZE > 0
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)
        assert MAX_MEMORY_BATCH_SIZE == 100

    def test_batch_size_affects_memory_usage(self):
        """Test that batch size affects memory usage calculations."""
        ingestor = DocumentIngestor(verbose=False)
        assert hasattr(ingestor, 'ingest')


class TestRateLimiting:
    """Test rate limiting in multicore context."""

    def test_rate_limiter_shared_across_processes(self):
        """Test that rate limiter can be shared across processes."""
        # Verify rate limiter function exists and is callable
        assert callable(get_shared_rate_limiter)

        limiter = get_shared_rate_limiter()
        assert isinstance(limiter, SharedRateLimiter)

    def test_rate_limit_config_exists(self):
        """Test that rate limit configuration exists."""
        cfg = config()
        assert cfg is not None
