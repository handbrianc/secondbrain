"""Tests for OpenTelemetry context propagation."""
import pytest


class TestOTELContextPropagation:
    def test_trace_context_functions_exist(self):
        from secondbrain.utils.tracing import (
            extract_trace_context,
            inject_trace_context,
            get_current_trace_context,
            set_trace_context
        )
        
        assert callable(extract_trace_context)
        assert callable(inject_trace_context)
        assert callable(get_current_trace_context)
        assert callable(set_trace_context)

    def test_context_propagation_basic(self):
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context
        
        headers = {}
        inject_trace_context(headers)
        
        context = extract_trace_context(headers)
        assert isinstance(context, dict) or context is None

    def test_context_propagation_round_trip(self):
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context
        
        headers = {}
        inject_trace_context(headers)
        
        extracted = extract_trace_context(headers)
        assert extracted is not None

    def test_http_trace_context_headers(self):
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context

        http_headers = {}
        
        inject_trace_context(http_headers)
        
        if "traceparent" in http_headers:
            traceparent = http_headers["traceparent"]
            parts = traceparent.split("-")
            assert len(parts) >= 3, "traceparent should have at least 3 parts"
        
        extracted = extract_trace_context(http_headers)
        assert extracted is None or isinstance(extracted, dict)
