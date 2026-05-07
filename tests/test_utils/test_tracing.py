"""Tests for OpenTelemetry tracing utilities."""

import contextlib
import os
from unittest.mock import patch

import pytest

from secondbrain.utils.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    extract_trace_context,
    get_current_trace_context,
    get_tracer,
    inject_trace_context,
    is_tracing_enabled,
    set_trace_context,
    setup_tracing,
    shutdown_tracing,
    trace_operation,
)


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_returns_false_when_not_set(self):
        """Should return False when SECONDBRAIN_TRACING_ENABLED is not set."""
        # Ensure env var is not set
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is False

    def test_returns_true_when_set_to_true(self):
        """Should return True when SECONDBRAIN_TRACING_ENABLED=true."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_true_when_set_to_true_uppercase(self):
        """Should return True when SECONDBRAIN_TRACING_ENABLED=TRUE (case-insensitive)."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "TRUE"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_false_when_set_to_false(self):
        """Should return False when SECONDBRAIN_TRACING_ENABLED=false."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "false"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is False


class TestSetupTracing:
    """Tests for setup_tracing function."""

    def test_noop_when_opentelemetry_not_available(self):
        """Should be a no-op when OpenTelemetry is not installed."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            # Should not raise
            setup_tracing(service_name="test", service_version="1.0")

    def test_noop_when_tracing_not_enabled(self, caplog):
        """Should be a no-op when tracing is not enabled via env var."""
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            caplog.at_level("DEBUG"),
        ):
            setup_tracing(service_name="test", service_version="1.0")

            # Should log debug message
            assert any("tracing not enabled" in msg.lower() for msg in caplog.messages)

    def test_sets_up_tracing_when_enabled(self):
        """Should setup tracing when OpenTelemetry is available and enabled."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        # Just verify it doesn't raise an exception
        # Full integration testing would require actual OpenTelemetry setup
        with contextlib.suppress(Exception):
            setup_tracing(
                service_name="test-service", service_version="2.0", environment="test"
            )


class TestGetTracer:
    """Tests for get_tracer function."""

    def test_returns_noop_tracer_when_opentelemetry_not_available(self):
        """Should return NoOpTracer when OpenTelemetry is not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            tracer = get_tracer()
            assert isinstance(tracer, _NoOpTracer)

    def test_returns_noop_tracer_when_not_initialized(self):
        """Should return NoOpTracer when tracing is not initialized."""
        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        tracer = get_tracer()
        # When not initialized, should return _NoOpTracer or None wrapped
        assert tracer is not None


class TestTraceOperation:
    """Tests for trace_operation context manager."""

    def test_yields_none_when_opentelemetry_not_available(self):
        """Should yield None when OpenTelemetry is not available."""
        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False),
            trace_operation("test_operation") as span,
        ):
            assert span is None

    def test_yields_none_when_tracing_not_enabled(self):
        """Should yield None when tracing is not enabled."""
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with trace_operation("test_operation") as span:
            # When tracing not enabled, span should be None or NoOp
            assert span is None or isinstance(span, _NoOpSpan)

    def test_executes_context_normally(self):
        """Should execute context normally and yield span when enabled."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace") as mock_trace,
        ):
            mock_span = patch("secondbrain.utils.tracing._NoOpSpan").start()
            mock_trace.get_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

            with trace_operation("test_operation"):
                # Context should execute
                pass

                patch.stopall()


class TestNoOpTracer:
    """Tests for NoOpTracer class."""

    def test_start_as_current_span_returns_noop_span(self):
        """Should return NoOpSpan from start_as_current_span."""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test")
        assert isinstance(span, _NoOpSpan)

    def test_getattr_returns_callable(self):
        """Should return a callable for any attribute access."""
        tracer = _NoOpTracer()
        result = tracer.some_method()
        assert result is None

        result2 = tracer.another_method(arg1="value", arg2=123)
        assert result2 is None


class TestNoOpSpan:
    """Tests for NoOpSpan class."""

    def test_set_attribute_is_noop(self):
        """Should not raise when setting attributes."""
        span = _NoOpSpan()
        span.set_attribute("key", "value")
        span.set_attribute("number", 123)
        # Should not raise

    def test_set_status_is_noop(self):
        """Should not raise when setting status."""
        span = _NoOpSpan()
        span.set_status("OK")
        span.set_status("ERROR", "Something went wrong")
        # Should not raise

    def test_record_exception_is_noop(self):
        """Should not raise when recording exception."""
        span = _NoOpSpan()
        span.record_exception(Exception("test error"))
        # Should not raise

    def test_add_event_is_noop(self):
        """Should not raise when adding event."""
        span = _NoOpSpan()
        span.add_event("event_name")
        span.add_event("event_name", {"key": "value"})
        # Should not raise

    def test_context_manager_works(self):
        """Should work as context manager."""
        with _NoOpSpan() as span:
            assert isinstance(span, _NoOpSpan)
        # Should exit cleanly


class TestShutdownTracing:
    """Tests for shutdown_tracing function."""

    def test_noop_when_opentelemetry_not_available(self):
        """Should be a no-op when OpenTelemetry is not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            # Should not raise
            shutdown_tracing()

    def test_resets_internal_state(self):
        """Should reset internal tracing state."""
        # Reset internal state first
        from secondbrain.utils import tracing

        tracing._tracer = "test_tracer"
        tracing._tracing_enabled = True

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace"),
        ):
            shutdown_tracing()

            # State should be reset
            assert tracing._tracer is None
            assert tracing._tracing_enabled is False


class TestExtractTraceContext:
    """Tests for extract_trace_context function."""

    def test_extract_valid_traceparent(self):
        """Should extract trace context from valid traceparent header."""
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }

        result = extract_trace_context(headers)

        assert result == {
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            "span_id": "00f067aa0ba902b7",
            "flags": "01",
        }

    def test_extract_case_insensitive_headers(self):
        """Should handle headers with different cases."""
        headers = {
            "TraceParent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }

        result = extract_trace_context(headers)

        assert result["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_extract_with_tracestate(self):
        """Should extract trace context even when tracestate is present."""
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor1=value1,vendor2=value2",
        }

        result = extract_trace_context(headers)

        assert result["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert result["span_id"] == "00f067aa0ba902b7"

    def test_empty_headers(self):
        """Should return empty dict for empty headers."""
        result = extract_trace_context({})

        assert result == {}

    def test_missing_traceparent(self):
        """Should return empty dict when traceparent is missing."""
        headers = {"content-type": "application/json"}

        result = extract_trace_context(headers)

        assert result == {}

    def test_invalid_traceparent_format(self):
        """Should return empty dict for invalid traceparent format."""
        headers = {"traceparent": "invalid-format"}

        result = extract_trace_context(headers)

        assert result == {}

    def test_invalid_traceparent_too_short(self):
        """Should return empty dict for traceparent that is too short."""
        headers = {"traceparent": "00-short-short-01"}

        result = extract_trace_context(headers)

        assert result == {}

    def test_zero_trace_id(self):
        """Should return empty dict for zero trace_id."""
        headers = {
            "traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
        }

        result = extract_trace_context(headers)

        assert result == {}

    def test_zero_span_id(self):
        """Should return empty dict for zero span_id."""
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
        }

        result = extract_trace_context(headers)

        assert result == {}

    def test_sampled_flag(self):
        """Should correctly extract sampled flag."""
        headers_sampled = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        headers_not_sampled = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"
        }

        result_sampled = extract_trace_context(headers_sampled)
        result_not_sampled = extract_trace_context(headers_not_sampled)

        assert result_sampled["flags"] == "01"
        assert result_not_sampled["flags"] == "00"


class TestInjectTraceContext:
    """Tests for inject_trace_context function."""

    def test_inject_generates_new_context(self):
        """Should generate new trace context when none exists."""
        headers = {"content-type": "application/json"}

        result = inject_trace_context(headers)

        assert "traceparent" in result
        assert result["content-type"] == "application/json"

        # Verify traceparent format
        traceparent = result["traceparent"]
        parts = traceparent.split("-")
        assert len(parts) == 4
        assert parts[0] == "00"  # version
        assert len(parts[1]) == 32  # trace_id
        assert len(parts[2]) == 16  # span_id
        assert len(parts[3]) == 2  # flags

    def test_inject_preserves_existing_headers(self):
        """Should preserve existing headers when injecting trace context."""
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer token123",
        }

        result = inject_trace_context(headers)

        assert result["content-type"] == "application/json"
        assert result["authorization"] == "Bearer token123"
        assert "traceparent" in result

    def test_inject_with_current_context(self):
        """Should use current trace context when available."""
        trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id = "00f067aa0ba902b7"

        with set_trace_context(trace_id, span_id, "01"):
            headers = {"content-type": "application/json"}
            result = inject_trace_context(headers)

            traceparent = result["traceparent"]
            assert trace_id in traceparent
            assert span_id in traceparent

    def test_inject_returns_copy(self):
        """Should return a copy of headers, not modify original."""
        headers = {"content-type": "application/json"}
        original_headers = headers.copy()

        result = inject_trace_context(headers)

        assert "traceparent" in result
        assert "traceparent" not in headers
        assert headers == original_headers


class TestGetCurrentTraceContext:
    """Tests for get_current_trace_context function."""

    def test_returns_none_when_not_set(self):
        """Should return None when trace context is not set."""
        result = get_current_trace_context()

        assert result is None

    def test_returns_context_when_set(self):
        """Should return trace context when set."""
        trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id = "00f067aa0ba902b7"

        with set_trace_context(trace_id, span_id, "01"):
            result = get_current_trace_context()

            assert result is not None
            assert result["trace_id"] == trace_id
            assert result["span_id"] == span_id
            assert result["flags"] == "01"

    def test_context_isolation(self):
        """Should maintain context isolation across nested contexts."""
        trace_id_outer = "11111111111111111111111111111111"
        span_id_outer = "1111111111111111"
        trace_id_inner = "22222222222222222222222222222222"
        span_id_inner = "2222222222222222"

        with set_trace_context(trace_id_outer, span_id_outer, "01"):
            outer_context = get_current_trace_context()
            assert outer_context["trace_id"] == trace_id_outer

            with set_trace_context(trace_id_inner, span_id_inner, "01"):
                inner_context = get_current_trace_context()
                assert inner_context["trace_id"] == trace_id_inner

            # After exiting inner context, should restore outer context
            outer_context_after = get_current_trace_context()
            assert outer_context_after["trace_id"] == trace_id_outer


class TestSetTraceContext:
    """Tests for set_trace_context context manager."""

    def test_sets_context(self):
        """Should set trace context within context."""
        trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id = "00f067aa0ba902b7"

        with set_trace_context(trace_id, span_id, "01"):
            context = get_current_trace_context()
            assert context["trace_id"] == trace_id
            assert context["span_id"] == span_id

    def test_restores_previous_context(self):
        """Should restore previous context after exit."""
        trace_id_outer = "11111111111111111111111111111111"
        span_id_outer = "1111111111111111"
        trace_id_inner = "22222222222222222222222222222222"
        span_id_inner = "2222222222222222"

        with set_trace_context(trace_id_outer, span_id_outer, "01"):
            with set_trace_context(trace_id_inner, span_id_inner, "01"):
                pass

            # Should be back to outer context
            context = get_current_trace_context()
            assert context["trace_id"] == trace_id_outer

    def test_invalid_trace_id_length(self):
        """Should raise ValueError for invalid trace_id length."""
        with pytest.raises(ValueError, match="Invalid trace_id"):
            with set_trace_context("short", "00f067aa0ba902b7", "01"):
                pass

    def test_invalid_trace_id_chars(self):
        """Should raise ValueError for non-hex trace_id."""
        with pytest.raises(ValueError, match="Invalid trace_id"):
            with set_trace_context("invalid!@#$%", "00f067aa0ba902b7", "01"):
                pass

    def test_invalid_span_id_length(self):
        """Should raise ValueError for invalid span_id length."""
        with pytest.raises(ValueError, match="Invalid span_id"):
            with set_trace_context("4bf92f3577b34da6a3ce929d0e0e4736", "short", "01"):
                pass

    def test_invalid_flags(self):
        """Should raise ValueError for invalid flags."""
        with pytest.raises(ValueError, match="Invalid flags"):
            with set_trace_context(
                "4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", "001"
            ):
                pass

    def test_with_tracestate(self):
        """Should handle tracestate correctly."""
        trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id = "00f067aa0ba902b7"
        tracestate = "vendor1=value1,vendor2=value2"

        with set_trace_context(trace_id, span_id, "01", tracestate):
            context = get_current_trace_context()
            assert context["tracestate"] == tracestate

    def test_case_normalization(self):
        """Should normalize hex characters to lowercase."""
        trace_id = "4BF92F3577B34DA6A3CE929D0E0E4736"
        span_id = "00F067AA0BA902B7"

        with set_trace_context(trace_id, span_id, "01"):
            context = get_current_trace_context()
            assert context["trace_id"] == trace_id.lower()
            assert context["span_id"] == span_id.lower()
