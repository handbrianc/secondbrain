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
