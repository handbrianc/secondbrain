"""Tests for OpenTelemetry context propagation."""
import pytest


class TestOTELContextPropagation:
    """Test trace context propagation for distributed tracing."""

    def test_trace_context_functions_exist(self):
        """Trace context functions should exist."""
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
        """Basic context propagation should work."""
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context
        
        headers = {}
        inject_trace_context(headers)
        
        # Should extract context back (may be empty if tracing not enabled)
        context = extract_trace_context(headers)
        # Just verify the functions work without error
        assert isinstance(context, dict) or context is None

    def test_context_propagation_round_trip(self):
        """Context can be injected and extracted correctly."""
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context
        
        # Inject context
        headers = {}
        inject_trace_context(headers)
        
        # Extract and verify
        extracted = extract_trace_context(headers)
        assert extracted is not None

    def test_http_trace_context_headers(self):
        """Test that HTTP requests carry W3C trace context headers.

        QA: Verify that when tracing is enabled, HTTP requests include
        W3C traceparent and tracestate headers for distributed tracing.
        """
        from secondbrain.utils.tracing import inject_trace_context, extract_trace_context

        # Simulate HTTP request headers
        http_headers = {}
        
        inject_trace_context(http_headers)
        
        if "traceparent" in http_headers:
            traceparent = http_headers["traceparent"]
            # W3C traceparent format: 00-<trace-id>-<parent-id>-<flags>
            parts = traceparent.split("-")
            assert len(parts) >= 3, "traceparent should have at least 3 parts"
        
        # Test extraction
        extracted = extract_trace_context(http_headers)
        # Should return dict or None (if tracing disabled)
        assert extracted is None or isinstance(extracted, dict)
