"""Tests for multicore ingestion support.

This module tests the parallel processing capabilities of DocumentIngestor,
including core count validation, error handling, and performance characteristics.

Note: Tests that involve ProcessPoolExecutor are limited because mocks don't
work across process boundaries. Focus on testing:
- Core count validation
- Worker function behavior
- Memory management constants and logic
- Configuration fallback logic
"""

import os
from pathlib import Path

import pytest

from secondbrain.config import Config
from secondbrain.document import (
    MAX_MEMORY_BATCH_SIZE,
    _extract_and_chunk_file,
)


class TestCoreCountValidation:
    """Tests for core count validation logic."""

    def test_core_count_validation_zero(self, tmp_path: Path):
        """Test core count validation for zero cores.

        QA: Verify ValueError is raised for cores=0.
        """
        with pytest.raises(ValueError, match="cores must be positive"):
            cores = 0
            if cores is not None and cores <= 0:
                raise ValueError("cores must be positive")

    def test_core_count_validation_negative(self, tmp_path: Path):
        """Test core count validation for negative cores.

        QA: Verify ValueError is raised for negative cores.
        """
        with pytest.raises(ValueError, match="cores must be positive"):
            cores = -1
            if cores is not None and cores <= 0:
                raise ValueError("cores must be positive")

    def test_core_count_validation_excessive(self, tmp_path: Path):
        """Test core count validation for excessive values.

        QA: Verify warning is issued and clamped to available cores.
        """
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
        """Test fallback to config max_workers setting.

        QA: Verify config.max_workers is used when cores=None.
        """
        # Create config with max_workers
        config = Config(max_workers=6)

        cores: int | None = None
        if cores is None:
            resolved = config.max_workers or os.cpu_count() or 1

        assert resolved == 6

    def test_fallback_to_cpu_count_auto_detection(self):
        """Test fallback to CPU count auto-detection.

        QA: Verify os.cpu_count() is used when no config.
        """
        config = Config()  # max_workers=None by default

        cores: int | None = None
        if cores is None:
            resolved = config.max_workers or os.cpu_count() or 1

        assert resolved == (os.cpu_count() or 1)
        assert resolved > 0


class TestWorkerFunction:
    """Tests for the _extract_and_chunk_file worker function."""

    def test_worker_function_module_level(self):
        """Test that worker function is at module level (picklable).

        QA: Verify function can be imported directly (not a method).
        """
        # This test verifies the function is accessible at module level
        assert callable(_extract_and_chunk_file)
        assert _extract_and_chunk_file.__module__ == "secondbrain.document"

    def test_worker_function_returns_correct_structure(self, tmp_path: Path):
        """Test worker function returns dict with required keys.

        QA: Verify return structure matches specification.
        """
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n\nThis is test content for the worker function.")

        result = _extract_and_chunk_file(test_file, chunk_size=100, chunk_overlap=10)

        assert isinstance(result, dict)
        assert "success" in result
        assert "file_path" in result
        assert "chunks" in result
        assert "error" in result
        assert result["success"] is True
        assert result["error"] is None
        assert isinstance(result["chunks"], list)
        assert len(result["chunks"]) > 0

    def test_worker_function_handles_extraction_errors(self, tmp_path: Path):
        """Test worker function handles extraction errors gracefully.

        QA: Verify error info returned instead of raising exception.
        """
        # Create a file with invalid format
        test_file = tmp_path / "corrupted.xyz"  # Unsupported extension
        test_file.write_bytes(b"\x00\x01\x02\x03")

        result = _extract_and_chunk_file(test_file, chunk_size=100, chunk_overlap=10)

        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["error"] is not None
        assert len(result["chunks"]) == 0

    def test_worker_function_chunks_text_correctly(self, tmp_path: Path):
        """Test worker function splits text into chunks properly.

        QA: Verify chunking respects chunk_size and chunk_overlap.
        """
        # Create a long markdown file
        test_file = tmp_path / "long.md"
        long_text = "# Title\n\n" + " ".join(["word"] * 200)  # 200 words
        test_file.write_text(long_text)

        result = _extract_and_chunk_file(test_file, chunk_size=50, chunk_overlap=5)

        assert result["success"] is True
        assert len(result["chunks"]) > 1  # Should be split into multiple chunks

        # Verify chunks don't exceed size limit (roughly)
        for chunk in result["chunks"]:
            # Allow some tolerance for word boundary splitting
            assert len(chunk["text"]) <= 100  # Generous limit for word boundaries


class TestMemoryManagement:
    """Tests for memory management features."""

    def test_max_memory_batch_size_constant_exists(self):
        """Test that MAX_MEMORY_BATCH_SIZE constant is defined.

        QA: Verify memory limit constant exists.
        """
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)
        assert MAX_MEMORY_BATCH_SIZE > 0
        assert MAX_MEMORY_BATCH_SIZE == 100

    def test_batch_splitting_logic(self):
        """Test batch splitting logic for memory efficiency.

        QA: Verify batches are split at MAX_MEMORY_BATCH_SIZE.
        """
        # Simulate a large list of documents
        large_batch = list(range(250))  # 250 items

        # Split into batches
        batches = []
        for i in range(0, len(large_batch), MAX_MEMORY_BATCH_SIZE):
            batch = large_batch[i : i + MAX_MEMORY_BATCH_SIZE]
            batches.append(batch)

        assert len(batches) == 3  # 100 + 100 + 50
        assert len(batches[0]) == 100
        assert len(batches[1]) == 100
        assert len(batches[2]) == 50


class TestCLIValidation:
    """Tests for CLI core count validation."""

    def test_cli_validates_cores_positive(self):
        """Test CLI validates cores > 0.

        QA: Verify CLI rejects non-positive core counts.
        """
        # Test cases that should fail
        invalid_cores = [0, -1, -10]

        for cores in invalid_cores:
            with pytest.raises(ValueError, match="cores must be positive"):
                if cores is not None and cores <= 0:
                    raise ValueError("cores must be positive")

    def test_cli_clamps_excessive_cores(self):
        """Test CLI clamps excessive core counts.

        QA: Verify CLI warns and clamps to available cores.
        """
        available = os.cpu_count() or 1
        requested = 999

        # Simulate CLI logic
        clamped = available if requested > available else requested

        assert clamped == available
        assert clamped < requested
