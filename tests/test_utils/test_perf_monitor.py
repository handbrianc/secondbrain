"""Tests for performance monitoring utilities."""

import asyncio
import time
from unittest.mock import patch

import pytest

from secondbrain.utils.perf_monitor import PerfMetrics, async_timing, metrics, timing


class TestPerfMetrics:
    """Tests for PerfMetrics class."""

    def test_record_adds_duration(self) -> None:
        """Test that record adds duration to metrics."""
        perf = PerfMetrics()
        perf.record("test_metric", 0.5)

        stats = perf.get_stats("test_metric")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["total_seconds"] == 0.5

    def test_get_stats_returns_none_for_unknown_metric(self) -> None:
        """Test that get_stats returns None for unknown metric."""
        perf = PerfMetrics()
        stats = perf.get_stats("unknown_metric")
        assert stats is None

    def test_get_stats_calculates_correct_statistics(self) -> None:
        """Test that get_stats calculates correct statistics."""
        perf = PerfMetrics()
        perf.record("test_metric", 0.1)
        perf.record("test_metric", 0.2)
        perf.record("test_metric", 0.3)

        stats = perf.get_stats("test_metric")
        assert stats is not None
        assert stats["count"] == 3
        assert stats["total_seconds"] == pytest.approx(0.6)
        assert stats["avg_seconds"] == pytest.approx(0.2)
        assert stats["min_seconds"] == pytest.approx(0.1)
        assert stats["max_seconds"] == pytest.approx(0.3)

    def test_get_stats_empty_metrics(self) -> None:
        """Test get_stats with empty metric list returns None."""
        perf = PerfMetrics()
        # Record then reset
        perf.record("test_metric", 0.1)
        perf.reset("test_metric")

        stats = perf.get_stats("test_metric")
        assert stats is None

    def test_reset_specific_metric(self) -> None:
        """Test that reset clears specific metric only."""
        perf = PerfMetrics()
        perf.record("metric1", 0.1)
        perf.record("metric2", 0.2)

        perf.reset("metric1")

        stats1 = perf.get_stats("metric1")
        stats2 = perf.get_stats("metric2")

        assert stats1 is None
        assert stats2 is not None
        assert stats2["count"] == 1

    def test_reset_all_metrics(self) -> None:
        """Test that reset() clears all metrics."""
        perf = PerfMetrics()
        perf.record("metric1", 0.1)
        perf.record("metric2", 0.2)

        perf.reset()

        stats1 = perf.get_stats("metric1")
        stats2 = perf.get_stats("metric2")

        assert stats1 is None
        assert stats2 is None

    def test_thread_safety(self) -> None:
        """Test that metrics are thread-safe."""
        import threading

        perf = PerfMetrics()
        num_threads = 10
        records_per_thread = 100

        def record_metrics() -> None:
            for _ in range(records_per_thread):
                perf.record("concurrent_metric", 0.01)

        threads = [threading.Thread(target=record_metrics) for _ in range(num_threads)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        stats = perf.get_stats("concurrent_metric")
        assert stats is not None
        assert stats["count"] == num_threads * records_per_thread


class TestTimingDecorator:
    """Tests for timing decorator."""

    def test_timing_decorator_records_duration(self) -> None:
        """Test that timing decorator records execution time."""
        with patch.object(metrics, "record") as mock_record:

            @timing("test_timing")
            def test_func() -> None:
                time.sleep(0.01)

            test_func()
            mock_record.assert_called_once()
            assert mock_record.call_args[0][0] == "test_timing"
            assert mock_record.call_args[0][1] > 0

    def test_timing_decorator_handles_exceptions(self) -> None:
        """Test that timing decorator records duration even on exception."""
        with patch.object(metrics, "record") as mock_record:

            @timing("test_timing")
            def failing_func() -> None:
                time.sleep(0.01)
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                failing_func()

            mock_record.assert_called_once()

    def test_timing_decorator_preserves_function_metadata(self) -> None:
        """Test that timing decorator preserves function metadata."""

        @timing("test_timing")
        def test_func() -> str:
            """Test function docstring."""
            return "test"

        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test function docstring."


class TestAsyncTimingDecorator:
    """Tests for async_timing decorator."""

    @pytest.mark.asyncio
    async def test_async_timing_decorator_records_duration(self) -> None:
        """Test that async_timing decorator records execution time."""
        with patch.object(metrics, "record") as mock_record:

            @async_timing("test_async_timing")
            async def test_func() -> None:
                await asyncio.sleep(0.01)

            await test_func()
            mock_record.assert_called_once()
            assert mock_record.call_args[0][0] == "test_async_timing"
            assert mock_record.call_args[0][1] > 0

    @pytest.mark.asyncio
    async def test_async_timing_decorator_handles_exceptions(self) -> None:
        """Test that async_timing decorator records duration even on exception."""
        with patch.object(metrics, "record") as mock_record:

            @async_timing("test_async_timing")
            async def failing_func() -> None:
                await asyncio.sleep(0.01)
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                await failing_func()

            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_timing_decorator_preserves_function_metadata(self) -> None:
        """Test that async_timing decorator preserves function metadata."""

        @async_timing("test_async_timing")
        async def test_func() -> str:
            """Test async function docstring."""
            return "test"

        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test async function docstring."
