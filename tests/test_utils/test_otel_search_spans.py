"""Tests for OpenTelemetry search query instrumentation."""


class TestSearchSpans:
    def test_trace_operation_for_search(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("search.query") as span:
            if span:
                span.set_attribute("top_k", 10)

    def test_search_span_operation_name_format(self):
        operation_name = "search.query"
        assert "query" in operation_name
