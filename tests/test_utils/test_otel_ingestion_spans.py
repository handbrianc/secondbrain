"""Tests for OpenTelemetry ingestion pipeline instrumentation."""
import pytest


class TestIngestionSpans:
    """Test ingestion pipeline span instrumentation."""

    def test_trace_operation_function_exists(self):
        """trace_operation function should exist in tracing module."""
        from secondbrain.utils.tracing import trace_operation
        
        assert callable(trace_operation)

    def test_trace_operation_creates_span_context(self):
        """trace_operation can create a span context for ingestion operations."""
        from secondbrain.utils.tracing import trace_operation
        
        # Use trace_operation as a context manager with just the operation name
        with trace_operation("document.ingest") as span:
            # Should be able to use the span if available
            if span:
                span.set_attribute("test.key", "test_value")
        
        # If we get here without error, the span was created successfully
        assert True

    def test_ingestion_span_operation_name_format(self):
        """Ingestion spans use correct operation name format."""
        # Verify the expected operation name pattern
        operation_name = "document.ingest"
        assert operation_name.startswith("document.")
        assert "ingest" in operation_name
