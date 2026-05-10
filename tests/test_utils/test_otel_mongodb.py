"""Tests for OpenTelemetry MongoDB instrumentation."""


class TestOTELMongoDB:
    """Test MongoDB operation span instrumentation."""

    def test_trace_operation_for_mongodb(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("db.mongodb.find") as span:
            if span:
                span.set_attribute("database", "secondbrain")

    def test_mongodb_span_operation_name_format(self):
        """MongoDB spans use db.mongodb.<operation> format."""
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("db.mongodb.find") as span:
            if span:
                assert span.name == "db.mongodb.find"
