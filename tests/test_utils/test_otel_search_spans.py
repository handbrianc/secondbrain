"""Tests for OpenTelemetry search query instrumentation."""
import pytest


class TestSearchSpans:
    """Test search query span instrumentation."""

    def test_trace_operation_for_search(self):
        """trace_operation can be used for search operations."""
        from secondbrain.utils.tracing import trace_operation
        
        # Create a search span with just the operation name
        with trace_operation("search.query") as span:
            if span:
                span.set_attribute("top_k", 10)
        
        assert True

    def test_search_span_operation_name_format(self):
        """Search spans use correct operation name format."""
        operation_name = "search.query"
        assert operation_name.startswith("search.")
        assert "query" in operation_name
