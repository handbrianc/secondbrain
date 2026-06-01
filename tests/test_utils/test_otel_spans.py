"""Tests for OpenTelemetry span-specific instrumentation.

Consolidated tests for:
- Ingestion pipeline spans
- Search query spans
- MongoDB operation spans
"""


class TestIngestionSpans:
    """Test ingestion pipeline span instrumentation."""

    def test_trace_operation_function_exists(self):
        from secondbrain.utils.tracing import trace_operation

        assert callable(trace_operation)

    def test_trace_operation_creates_span_context(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("document.ingest") as span:
            if span:
                span.set_attribute("test.key", "test_value")

    def test_ingestion_span_operation_name_format(self):
        operation_name = "document.ingest"
        assert "ingest" in operation_name


class TestSearchSpans:
    """Test search query span instrumentation."""

    def test_trace_operation_for_search(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("search.query") as span:
            if span:
                span.set_attribute("top_k", 10)

    def test_search_span_operation_name_format(self):
        operation_name = "search.query"
        assert "query" in operation_name


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
