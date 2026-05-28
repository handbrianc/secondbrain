"""Tests for multicore cross-platform compatibility."""
import pytest
import multiprocessing


class TestMulticoreCrossPlatform:
    """Test multiprocessing works across platforms."""

    def test_cpu_count_detection(self):
        """CPU count should be detectable."""
        count = multiprocessing.cpu_count()
        assert count > 0

    def test_multiprocessing_available(self):
        """multiprocessing module should be available."""
        assert multiprocessing.Pool is not None
        assert multiprocessing.Process is not None
