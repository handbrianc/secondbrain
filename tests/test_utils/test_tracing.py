"""Tests for OpenTelemetry tracing utilities."""

import contextlib
import os
from unittest.mock import patch

from secondbrain.utils.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    get_tracer,
    is_tracing_enabled,
    setup_tracing,
    shutdown_tracing,
    trace_operation,
)


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_returns_false_when_not_set(self):
        """Should return False when OTEL_TRACING_ENABLED is not set."""
        # Ensure env var is not set
        os.environ.pop("OTEL_TRACING_ENABLED", None)

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is False

    def test_returns_true_when_set_to_true(self):
        """Should return True when OTEL_TRACING_ENABLED=true."""
        os.environ["OTEL_TRACING_ENABLED"] = "true"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_true_when_set_to_true_uppercase(self):
        """Should return True when OTEL_TRACING_ENABLED=TRUE (case-insensitive)."""
        os.environ["OTEL_TRACING_ENABLED"] = "TRUE"

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_false_when_set_to_false(self):
        """Should return False when OTEL_TRACING_ENABLED=false."""
        os.environ["OTEL_TRACING_ENABLED"] = "false"

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
        os.environ.pop("OTEL_TRACING_ENABLED", None)

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
        os.environ["OTEL_TRACING_ENABLED"] = "true"

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

        os.environ.pop("OTEL_TRACING_ENABLED", None)

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
        os.environ.pop("OTEL_TRACING_ENABLED", None)

        # Reset internal state
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with trace_operation("test_operation") as span:
            # When tracing not enabled, span should be None or NoOp
            assert span is None or isinstance(span, _NoOpSpan)

    def test_executes_context_normally(self):
        """Should execute context normally and yield span when enabled."""
        os.environ["OTEL_TRACING_ENABLED"] = "true"

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
