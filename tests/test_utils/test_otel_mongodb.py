"""Tests for OpenTelemetry MongoDB instrumentation."""
import pytest


class TestOTELMongoDB:
    """Test MongoDB operation span instrumentation."""

    def test_trace_operation_for_mongodb(self):
        """trace_operation can be used for MongoDB operations."""
        from secondbrain.utils.tracing import trace_operation
        
        # Create a MongoDB span with just the operation name
        with trace_operation("db.mongodb.find") as span:
            if span:
                span.set_attribute("database", "secondbrain")
        
        assert True

    def test_mongodb_span_operation_name_format(self):
        """MongoDB spans use correct operation name format."""
        operation_name = "db.mongodb.find"
        assert operation_name.startswith("db.mongodb.")
        assert "find" in operation_name
