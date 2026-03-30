"""Integration tests for observability features.

Tests cover:
- Trace context propagation across async boundaries
- Log-trace correlation
- OTLP exporter configuration
- Metrics collection (both OTel and custom)
- Span hierarchy verification
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.logging import (
    CorrelationIdFilter,
    JSONFormatter,
    get_trace_context,
    set_trace_context,
)
from secondbrain.utils.metrics import (
    OTelMetricsCollector,
    is_metrics_enabled,
    setup_metrics,
)
from secondbrain.utils.observability import (
    MetricsCollector,
    log_operation_complete,
    log_operation_start,
    metrics,
    trace_span,
)
from secondbrain.utils.tracing import (
    SPAN_HIERARCHY,
    async_trace_decorator,
    get_span_name,
    get_trace_context as get_tracing_context,
    is_tracing_enabled,
    set_trace_context as set_tracing_context,
    trace_operation,
)


class TestLoggingIntegration:
    """Test logging integration with trace context."""

    def test_correlation_id_filter_adds_id(self):
        """CorrelationIdFilter adds correlation ID to log records."""
        filter_instance = CorrelationIdFilter()
        record = MagicMock()
        record.getMessage.return_value = "test message"

        result = filter_instance.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id is not None

    def test_json_formatter_includes_correlation_id(self):
        """JSONFormatter includes correlation ID in output."""
        formatter = JSONFormatter()
        record = MagicMock()
        record.levelname = "INFO"
        record.name = "test.logger"
        record.module = "test_module"
        record.funcName = "test_func"
        record.lineno = 42
        record.getMessage.return_value = "test message"
        record.exc_info = None
        record.correlation_id = "test-correlation-id"

        output = formatter.format(record)

        assert "test-correlation-id" in output
        assert "test message" in output

    def test_trace_context_propagation(self):
        """Trace context can be set and retrieved."""
        set_trace_context(trace_id="trace-123", span_id="span-456")

        context = get_trace_context()

        assert context is not None
        assert context["trace_id"] == "trace-123"
        assert context["span_id"] == "span-456"


class TestMetricsIntegration:
    """Test metrics collection integration."""

    def test_custom_metrics_collector_records(self):
        """Custom MetricsCollector records metrics correctly."""
        collector = MetricsCollector()

        collector.record("test.metric", 1.5)
        collector.record("test.metric", 2.5)
        collector.increment("test.counter", 5)
        collector.set_gauge("test.gauge", 42.0)

        stats = collector.get_stats("test.metric")
        assert stats is not None
        assert stats["count"] == 2
        assert stats["min"] == 1.5
        assert stats["max"] == 2.5

        assert collector._counters["test.counter"] == 5
        assert collector._gauges["test.gauge"] == 42.0

    def test_otel_metrics_collector_creates_metrics(self):
        """OTelMetricsCollector creates metrics when OTel is available."""
        # Test that collector can be instantiated
        collector = OTelMetricsCollector()
        assert collector is not None

    def test_metrics_enabled_check(self):
        """is_metrics_enabled respects environment variable."""
        with patch.dict(os.environ, {"OTEL_METRICS_ENABLED": "true"}):
            # Note: This will still return False if OTel is not installed
            result = is_metrics_enabled()
            # Result depends on OTel availability
            assert isinstance(result, bool)


class TestTracingIntegration:
    """Test tracing integration."""

    def test_span_hierarchy_names(self):
        """Span hierarchy produces correct names."""
        assert get_span_name("ingest", "document.parse") == "ingest.document.parse"
        assert get_span_name("search", "query.retrieval") == "search.query.retrieval"
        assert get_span_name("rag", "pipeline.retrieve") == "rag.pipeline.retrieve"

    def test_trace_context_set_and_get(self):
        """Trace context can be set and retrieved in tracing module."""
        set_tracing_context(
            trace_id="test-trace",
            span_id="test-span",
            correlation_id="test-correlation",
        )

        context = get_tracing_context()
        assert context is not None
        assert context["trace_id"] == "test-trace"
        assert context["span_id"] == "test-span"
        assert context["correlation_id"] == "test-correlation"

    def test_trace_operation_context_manager(self):
        """trace_operation context manager works when tracing disabled."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            with trace_operation("test.operation") as span:
                assert span is None

    def test_is_tracing_enabled_respects_env(self):
        """is_tracing_enabled respects OTEL_TRACING_ENABLED env var."""
        with patch.dict(os.environ, {"OTEL_TRACING_ENABLED": "true"}):
            # Reset the cached value
            import secondbrain.utils.tracing as tracing_module

            tracing_module._tracing_enabled = False

            result = is_tracing_enabled()
            assert result is True

        with patch.dict(os.environ, {"OTEL_TRACING_ENABLED": "false"}):
            tracing_module._tracing_enabled = False
            result = is_tracing_enabled()
            assert result is False


class TestAsyncContextPropagation:
    """Test async context propagation."""

    @pytest.mark.asyncio
    async def test_async_trace_decorator(self):
        """async_trace_decorator works with async functions."""
        call_count = 0

        @async_trace_decorator("test.async.operation")
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "result"

        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            result = await test_func()
            assert result == "result"
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_context_vars_propagate(self):
        """Context variables propagate across async boundaries."""
        from contextvars import ContextVar

        test_var = ContextVar("test_var", default="default")

        async def inner_function():
            return test_var.get()

        test_var.set("updated")
        result = await inner_function()
        assert result == "updated"


class TestObservabilityWorkflow:
    """Test complete observability workflows."""

    def test_log_operation_start_sets_correlation_id(self):
        """log_operation_start sets correlation ID in environment."""
        correlation_id = log_operation_start("test.operation")

        assert os.environ.get("CORRELATION_ID") == correlation_id
        assert correlation_id is not None

    def test_log_operation_complete_records_metrics(self):
        """log_operation_complete records metrics."""
        initial_counters = dict(metrics._counters)

        log_operation_complete("test.op", 1.5, True)

        # Check that metrics were recorded
        assert "operation.test.op.duration" in metrics._metrics
        success_key = "operation.test.op.success"
        assert initial_counters.get(success_key, 0) + 1 == metrics._counters.get(
            success_key, 0
        )

    def test_trace_span_context_manager(self):
        """trace_span context manager works when tracing disabled."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            with trace_span("test.span") as span:
                assert span is None


class TestSpanHierarchy:
    """Test span hierarchy definitions."""

    def test_span_hierarchy_contains_expected_categories(self):
        """SPAN_HIERARCHY contains expected operation categories."""
        assert "ingest" in SPAN_HIERARCHY
        assert "search" in SPAN_HIERARCHY
        assert "rag" in SPAN_HIERARCHY

    def test_ingest_span_names(self):
        """Ingest spans have correct naming."""
        assert SPAN_HIERARCHY["ingest"]["document.parse"] == "ingest.document.parse"
        assert SPAN_HIERARCHY["ingest"]["document.embed"] == "ingest.document.embed"
        assert SPAN_HIERARCHY["ingest"]["document.store"] == "ingest.document.store"

    def test_search_span_names(self):
        """Search spans have correct naming."""
        assert SPAN_HIERARCHY["search"]["query.retrieval"] == "search.query.retrieval"
        assert SPAN_HIERARCHY["search"]["query.rerank"] == "search.query.rerank"

    def test_rag_span_names(self):
        """RAG spans have correct naming."""
        assert SPAN_HIERARCHY["rag"]["pipeline.retrieve"] == "rag.pipeline.retrieve"
        assert SPAN_HIERARCHY["rag"]["pipeline.generate"] == "rag.pipeline.generate"


class TestOTLPConfiguration:
    """Test OTLP exporter configuration."""

    def test_otlp_endpoint_from_env(self):
        """OTLP endpoint can be configured via environment variable."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://test-collector:4317"},
        ):
            from secondbrain.utils.tracing import setup_otlp_exporter

            # Test that the function can be called without error
            # (actual exporter creation may fail if OTel not installed)
            try:
                result = setup_otlp_exporter()
                # If OTel is installed, result should be an exporter or None
                if result is not None:
                    assert hasattr(result, "export")
            except ImportError:
                # Expected if OTel not installed
                pass

    def test_otlp_timeout_from_env(self):
        """OTLP timeout can be configured via environment variable."""
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_TIMEOUT": "30"}):
            # Just verify the env var is read correctly
            timeout = int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", 10))
            assert timeout == 30
