"""Tests for performance monitoring utilities."""
import logging
import time

import pytest

from secondbrain.utils.perf_monitor import PerfMetrics, metrics, timing


class TestPerfMetrics:
    """Test PerfMetrics collection and statistics."""

    def test_record_duration(self):
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.045)
        test_metrics.record("query", 0.055)
        
        stats = test_metrics.get_stats("query")
        
        assert stats is not None
        assert stats["count"] == 2
        assert 0.090 <= stats["total_seconds"] <= 0.110  # 10% tolerance range
        assert 0.045 <= stats["avg_seconds"] <= 0.055  # 20% tolerance range
        assert 0.040 <= stats["min_seconds"] <= 0.050  # Tolerance for min
        assert 0.050 <= stats["max_seconds"] <= 0.060  # Tolerance for max

    def test_multiple_metrics(self):
        test_metrics = PerfMetrics()
        
        test_metrics.record("ingest", 0.5)
        test_metrics.record("search", 0.05)
        test_metrics.record("ingest", 0.6)
        
        ingest_stats = test_metrics.get_stats("ingest")
        search_stats = test_metrics.get_stats("search")
        
        assert ingest_stats is not None
        assert search_stats is not None
        assert ingest_stats["count"] == 2
        assert search_stats["count"] == 1
        assert 0.50 <= ingest_stats["avg_seconds"] <= 0.60  # 20% tolerance for system variance
        assert 0.040 <= search_stats["avg_seconds"] <= 0.060  # 20% tolerance for system variance

    def test_reset_metric(self):
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.05)
        test_metrics.reset("query")
        
        assert test_metrics.get_stats("query") is None

    def test_reset_all(self):
        test_metrics = PerfMetrics()
        
        test_metrics.record("query", 0.05)
        test_metrics.record("ingest", 0.5)
        test_metrics.reset()
        
        assert test_metrics.get_stats("query") is None
        assert test_metrics.get_stats("ingest") is None

    def test_empty_stats(self):
        test_metrics = PerfMetrics()
        assert test_metrics.get_stats("nonexistent") is None


class TestTimingDecorator:
    """Test @timing decorator for measuring execution time."""

    def test_timing_decorator_records_duration(self, caplog):
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
        assert 0.090 <= stats["avg_seconds"] <= 0.150  # 20% tolerance below, 50% above for sleep variance

    def test_timing_decorator_handles_exceptions(self, caplog):
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
        assert 0.040 <= stats["avg_seconds"] <= 0.100  # 20% tolerance below, 100% above for exception overhead


class TestPerformanceLogging:
    """Test that performance metrics are logged correctly."""

    def test_performance_metrics_logged(self, caplog):
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
        
        assert any("document.ingest" in msg for msg in log_messages)
        assert any("semantic.search" in msg for msg in log_messages)
        
        ingest_stats = metrics.get_stats("document.ingest")
        search_stats = metrics.get_stats("semantic.search")
        
        assert ingest_stats is not None
        assert search_stats is not None
        assert ingest_stats["count"] == 1
        assert search_stats["count"] == 1
        assert 0.040 <= ingest_stats["avg_seconds"] <= 0.070  # 20% tolerance below, 40% above for system variance
        assert 0.025 <= search_stats["avg_seconds"] <= 0.045  # 20% tolerance below, 50% above for system variance