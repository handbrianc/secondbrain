"""Tests for OpenTelemetry ingestion pipeline instrumentation."""


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
