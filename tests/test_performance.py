"""Tests for performance monitoring utilities.

This module tests the PerfMetrics class and timing decorators to ensure
performance metrics are correctly collected and logged.
"""
import logging
import time

import pytest

from secondbrain.utils.perf_monitor import PerfMetrics, timing, async_timing, metrics


class TestPerfMetrics:
    """Test PerfMetrics collection and statistics."""

    def test_record_duration(self):
        """Test that duration is recorded correctly."""
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.045)
        test_metrics.record("query", 0.055)
        
        stats = test_metrics.get_stats("query")
        
        assert stats is not None
        assert stats["count"] == 2
        assert stats["total_seconds"] == pytest.approx(0.100, abs=0.001)
        assert stats["avg_seconds"] == pytest.approx(0.050, abs=0.001)
        assert stats["min_seconds"] == pytest.approx(0.045, abs=0.001)
        assert stats["max_seconds"] == pytest.approx(0.055, abs=0.001)

    def test_multiple_metrics(self):
        """Test that multiple metrics are tracked independently."""
        test_metrics = PerfMetrics()
        
        test_metrics.record("ingest", 0.5)
        test_metrics.record("search", 0.05)
        test_metrics.record("ingest", 0.6)
        
        ingest_stats = test_metrics.get_stats("ingest")
        search_stats = test_metrics.get_stats("search")
        
        assert ingest_stats["count"] == 2
        assert search_stats["count"] == 1
        assert abs(ingest_stats["avg_seconds"] - 0.55) < 0.01
        assert abs(search_stats["avg_seconds"] - 0.05) < 0.01

    def test_reset_metric(self):
        """Test that individual metric can be reset."""
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.05)
        test_metrics.reset("query")
        
        stats = test_metrics.get_stats("query")
        assert stats is None

    def test_reset_all(self):
        """Test that all metrics can be reset."""
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.05)
        test_metrics.record("ingest", 0.5)
        test_metrics.reset()
        
        assert test_metrics.get_stats("query") is None
        assert test_metrics.get_stats("ingest") is None

    def test_empty_stats(self):
        """Test that stats for non-existent metric returns None."""
        test_metrics = PerfMetrics()
        
        stats = test_metrics.get_stats("nonexistent")
        assert stats is None


class TestTimingDecorator:
    """Test @timing decorator for measuring execution time."""

    def test_timing_decorator_records_duration(self, caplog):
        """Test that timing decorator records execution time."""
        # Reset global metrics for clean test
        metrics.reset("test_operation")
        
        @timing("test_operation")
        def slow_function():
            time.sleep(0.1)
            return "done"
        
        with caplog.at_level(logging.DEBUG):
            result = slow_function()
        
        assert result == "done"
        
        stats = metrics.get_stats("test_operation")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["avg_seconds"] >= 0.1

    def test_timing_decorator_handles_exceptions(self, caplog):
        """Test that timing decorator still records even on exception."""
        metrics.reset("failing_operation")
        
        @timing("failing_operation")
        def failing_function():
            time.sleep(0.05)
            raise ValueError("Test error")
        
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ValueError):
                failing_function()
        
        stats = metrics.get_stats("failing_operation")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["avg_seconds"] >= 0.05


class TestPerformanceLogging:
    """Test that performance metrics are logged correctly."""

    def test_performance_metrics_logged(self, caplog):
        """Test that performance metrics are logged during operations.
        
        Verifies that:
        - Timing information is logged for operations
        - Logs contain metric name and duration
        - Multiple operations are tracked independently
        """
        metrics.reset("document.ingest")
        metrics.reset("semantic.search")
        
        @timing("document.ingest")
        def ingest_document():
            time.sleep(0.05)
            return {"status": "ingested"}
        
        @timing("semantic.search")
        def search_documents():
            time.sleep(0.03)
            return [{"chunk": "result"}]
        
        with caplog.at_level(logging.DEBUG):
            ingest_result = ingest_document()
            search_result = search_documents()
        
        assert ingest_result["status"] == "ingested"
        assert len(search_result) == 1
        
        log_messages = [record.message for record in caplog.records]
        
        ingest_logged = any("document.ingest" in msg for msg in log_messages)
        search_logged = any("semantic.search" in msg for msg in log_messages)
        
        assert ingest_logged, "Document ingestion timing should be logged"
        assert search_logged, "Search timing should be logged"
        
        ingest_stats = metrics.get_stats("document.ingest")
        search_stats = metrics.get_stats("semantic.search")
        
        assert ingest_stats is not None
        assert search_stats is not None
        assert ingest_stats["count"] == 1
        assert search_stats["count"] == 1
        assert ingest_stats["avg_seconds"] >= 0.05
        assert search_stats["avg_seconds"] >= 0.03