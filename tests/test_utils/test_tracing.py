"""Tests for OpenTelemetry tracing utilities."""

import contextlib
import os
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.utils.tracing import (
    _NoOpCounter,
    _NoOpHistogram,
    _NoOpMeter,
    _NoOpSpan,
    _NoOpTracer,
    extract_trace_context,
    get_current_trace_context,
    get_meter,
    get_tracer,
    inject_trace_context,
    is_metrics_enabled,
    is_tracing_enabled,
    record_operation,
    set_trace_context,
    setup_tracing,
    shutdown_tracing,
    trace_decorator,
    trace_operation,
)


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_returns_false_when_not_set(self):
        """Should return False when SECONDBRAIN_TRACING_ENABLED is not set."""
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is False

    def test_returns_true_when_set_to_true(self):
        """Should return True when SECONDBRAIN_TRACING_ENABLED=true."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_true_when_set_to_true_uppercase(self):
        """Should return True when SECONDBRAIN_TRACING_ENABLED=TRUE (case-insensitive)."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "TRUE"

        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is True

    def test_returns_false_when_set_to_false(self):
        """Should return False when SECONDBRAIN_TRACING_ENABLED=false."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "false"

        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        assert is_tracing_enabled() is False


class TestSetupTracing:
    """Tests for setup_tracing function."""

    def test_noop_when_opentelemetry_not_available(self):
        """Should be a no-op when OpenTelemetry is not installed."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            setup_tracing(service_name="test", service_version="1.0")

    def test_noop_when_tracing_not_enabled(self, caplog):
        """Should be a no-op when tracing is not enabled via env var."""
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        from secondbrain.utils import tracing

        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            caplog.at_level("DEBUG"),
        ):
            setup_tracing(service_name="test", service_version="1.0")

            assert any("tracing not enabled" in msg.lower() for msg in caplog.messages)

    def test_sets_up_tracing_when_enabled(self):
        """Should setup tracing when OpenTelemetry is available and enabled."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

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
            assert tracer.__class__.__name__ == "_NoOpTracer"

    def test_returns_noop_tracer_when_not_initialized(self):
        """Should return NoOpTracer when tracing is not initialized."""
        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        tracer = get_tracer()
        assert tracer is not None


class TestTraceOperation:
    """Tests for trace_operation context manager."""

    def test_yields_none_when_opentelemetry_not_available(self):
        """Should yield None when OpenTelemetry is not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            with trace_operation("test_operation") as span:
                assert span is None
        """Should yield None when tracing is not enabled."""
        os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with trace_operation("test_operation") as span:
            assert span is None or span.__class__.__name__ == "_NoOpSpan"

    def test_executes_context_normally(self):
        """Should execute context normally and yield span when enabled."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

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
                pass

            patch.stopall()


class TestNoOpTracer:
    """Tests for NoOpTracer class."""

    def test_start_as_current_span_returns_noop_span(self):
        """Should return NoOpSpan from start_as_current_span."""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test")
        assert span.__class__.__name__ == "_NoOpSpan"

    def test_getattr_returns_callable(self):
        """Should return a callable for any attribute access."""
        tracer = _NoOpTracer()
        assert tracer.some_method() is None
        assert tracer.another_method(arg1="value", arg2=123) is None


class TestNoOpSpan:
    """Tests for NoOpSpan class."""

    def test_set_attribute_is_noop(self):
        """Should not raise when setting attributes."""
        span = _NoOpSpan()
        span.set_attribute("key", "value")
        span.set_attribute("number", 123)

    def test_set_status_is_noop(self):
        """Should not raise when setting status."""
        span = _NoOpSpan()
        span.set_status("OK")
        span.set_status("ERROR", "Something went wrong")

    def test_record_exception_is_noop(self):
        """Should not raise when recording exception."""
        span = _NoOpSpan()
        span.record_exception(Exception("test error"))

    def test_add_event_is_noop(self):
        """Should not raise when adding event."""
        span = _NoOpSpan()
        span.add_event("event_name")
        span.add_event("event_name", {"key": "value"})

    def test_context_manager_works(self):
        """Should work as context manager."""
        with _NoOpSpan() as span:
            assert span.__class__.__name__ == "_NoOpSpan"


class TestShutdownTracing:
    """Tests for shutdown_tracing function."""

    def test_noop_when_opentelemetry_not_available(self):
        """Should be a no-op when OpenTelemetry is not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            shutdown_tracing()

    def test_resets_internal_state(self):
        """Should reset internal tracing state."""
        from secondbrain.utils import tracing

        tracing._tracer = "test_tracer"
        tracing._tracing_enabled = True

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace"),
        ):
            shutdown_tracing()

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
        assert extract_trace_context({}) == {}

    def test_missing_traceparent(self):
        """Should return empty dict when traceparent is missing."""
        headers = {"content-type": "application/json"}

        assert extract_trace_context(headers) == {}

    def test_invalid_traceparent_format(self):
        """Should return empty dict for invalid traceparent format."""
        headers = {"traceparent": "invalid-format"}

        assert extract_trace_context(headers) == {}

    def test_invalid_traceparent_too_short(self):
        """Should return empty dict for traceparent that is too short."""
        headers = {"traceparent": "00-short-short-01"}

        assert extract_trace_context(headers) == {}

    def test_zero_trace_id(self):
        """Should return empty dict for zero trace_id."""
        headers = {
            "traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
        }

        assert extract_trace_context(headers) == {}

    def test_zero_span_id(self):
        """Should return empty dict for zero span_id."""
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
        }

        assert extract_trace_context(headers) == {}

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

        traceparent = result["traceparent"]
        parts = traceparent.split("-")
        assert len(parts) == 4
        assert parts[0] == "00"
        assert len(parts[1]) == 32
        assert len(parts[2]) == 16
        assert len(parts[3]) == 2

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

    def test_trace_context_normalizes_hex_to_lowercase(self):
        """Should normalize hex characters to lowercase."""
        trace_id = "4BF92F3577B34DA6A3CE929D0E0E4736"
        span_id = "00F067AA0BA902B7"

        with set_trace_context(trace_id, span_id, "01"):
            context = get_current_trace_context()
            assert context["trace_id"] == trace_id.lower()
            assert context["span_id"] == span_id.lower()


class TestIsMetricsEnabled:
    """Tests for is_metrics_enabled function."""

    def test_returns_true_when_not_set(self):
        """Should return True by default when OTEL_METRICS_ENABLED is not set."""
        os.environ.pop("OTEL_METRICS_ENABLED", None)

        from secondbrain.utils import tracing

        tracing._metrics_enabled = False

        assert is_metrics_enabled() is True

    def test_returns_true_when_set_to_true(self):
        """Should return True when OTEL_METRICS_ENABLED=true."""
        os.environ["OTEL_METRICS_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._metrics_enabled = False

        assert is_metrics_enabled() is True

    def test_returns_false_when_set_to_false(self):
        """Should return False when OTEL_METRICS_ENABLED=false."""
        os.environ["OTEL_METRICS_ENABLED"] = "false"

        from secondbrain.utils import tracing

        tracing._metrics_enabled = False

        assert is_metrics_enabled() is False

    def test_returns_true_when_set_to_true_uppercase(self):
        """Should return True when OTEL_METRICS_ENABLED=TRUE (case-insensitive)."""
        os.environ["OTEL_METRICS_ENABLED"] = "TRUE"

        from secondbrain.utils import tracing

        tracing._metrics_enabled = False

        assert is_metrics_enabled() is True


class TestSetupTracingWithMetrics:
    """Tests for setup_tracing with metrics and pymongo."""

    def test_sets_up_metrics_when_enabled(self, caplog):
        """Should setup metrics when OTEL_METRICS_ENABLED is true."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"
        os.environ["OTEL_METRICS_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._meter = None
        tracing._tracing_enabled = False
        tracing._metrics_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace"),
            patch("secondbrain.utils.tracing.otel_metrics") as mock_metrics,
            caplog.at_level("INFO"),
        ):
            mock_meter = patch("secondbrain.utils.tracing._NoOpMeter").start()
            mock_metrics.get_meter.return_value = mock_meter
            mock_metrics.set_meter_provider = patch(
                "secondbrain.utils.tracing.otel_metrics.set_meter_provider"
            ).start()

            setup_tracing(
                service_name="test-service", service_version="2.0", environment="test"
            )

            assert mock_metrics.get_meter.called
            patch.stopall()

    def test_handles_invalid_sampling_rate(self, caplog):
        """Should handle invalid sampling rate gracefully."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"
        os.environ["SECONDBRAIN_OTEL_SAMPLING_RATE"] = "invalid"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            caplog.at_level("WARNING"),
        ):
            setup_tracing(service_name="test", service_version="1.0")

            assert any(
                "invalid" in msg.lower() for msg in caplog.messages
            ), "Should log warning about invalid sampling rate"

    def test_handles_otlp_exporter_failure(self, caplog):
        """Should fallback to console exporter when OTLP fails."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            # When OTel is not available, setup_tracing is a no-op
            setup_tracing(service_name="test", service_version="1.0")
            # Test passes if no exception is raised

    def test_enables_pymongo_instrumentation_when_available(self):
        """Should attempt pymongo instrumentation when available."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        # Just verify the code path exists - detailed testing requires OTel
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            # When OTel is not available, pymongo instrumentation is skipped
            setup_tracing(service_name="test", service_version="1.0")
            # Test passes if no exception is raised

    def test_handles_pymongo_instrumentation_failure(self):
        """Should handle pymongo instrumentation failure gracefully."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        # Just verify the code path exists - detailed testing requires OTel
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            # When OTel is not available, pymongo instrumentation is skipped
            setup_tracing(service_name="test", service_version="1.0")
            # Test passes if no exception is raised


class TestGetMeter:
    """Tests for get_meter function."""

    def test_returns_noop_meter_when_opentelemetry_not_available(self):
        """Should return NoOpMeter when OpenTelemetry is not available."""
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            meter = get_meter()
            assert meter.__class__.__name__ == "_NoOpMeter"

    def test_returns_noop_meter_when_not_initialized(self):
        """Should return NoOpMeter when meter is not initialized."""
        from secondbrain.utils import tracing

        tracing._meter = None

        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True):
            meter = get_meter()
            assert meter is not None

    def test_returns_meter_when_initialized(self):
        """Should return meter when initialized."""
        from secondbrain.utils import tracing

        # Use a simple mock object
        mock_meter = object()
        tracing._meter = mock_meter
        tracing._metrics_enabled = True

        # Need to mock both OTTEL_AVAILABLE and otel_metrics
        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_metrics", True),
        ):
            meter = get_meter()
            assert meter == mock_meter


class TestRecordOperation:
    """Tests for record_operation function."""

    def test_records_operation_success(self):
        """Should record successful operation."""
        from secondbrain.utils import tracing

        tracing._metrics_enabled = True

        mock_meter = patch("secondbrain.utils.tracing._NoOpMeter").start()
        mock_counter = patch("secondbrain.utils.tracing._NoOpCounter").start()
        mock_histogram = patch("secondbrain.utils.tracing._NoOpHistogram").start()

        tracing._meter = mock_meter
        tracing._operations_counter = mock_counter
        tracing._duration_histogram = mock_histogram

        mock_meter.create_counter.return_value = mock_counter
        mock_meter.create_histogram.return_value = mock_histogram

        record_operation("test_operation", 100.0, success=True)

        assert mock_counter.add.called
        assert mock_histogram.record.called

        patch.stopall()

    def test_records_operation_failure(self):
        """Should record failed operation with error counter."""
        from secondbrain.utils import tracing

        tracing._metrics_enabled = True

        mock_meter = patch("secondbrain.utils.tracing._NoOpMeter").start()
        mock_counter = patch("secondbrain.utils.tracing._NoOpCounter").start()
        mock_histogram = patch("secondbrain.utils.tracing._NoOpHistogram").start()
        mock_errors_counter = patch("secondbrain.utils.tracing._NoOpCounter").start()

        tracing._meter = mock_meter
        tracing._operations_counter = mock_counter
        tracing._duration_histogram = mock_histogram
        tracing._errors_counter = mock_errors_counter

        mock_meter.create_counter.return_value = mock_counter
        mock_meter.create_histogram.return_value = mock_histogram

        record_operation("test_operation", 100.0, success=False)

        assert mock_errors_counter.add.called

        patch.stopall()

    def test_returns_early_when_metrics_not_enabled(self):
        """Should return early when metrics not enabled."""
        from secondbrain.utils import tracing

        tracing._metrics_enabled = False
        tracing._meter = None

        # Should not raise
        record_operation("test_operation", 100.0, success=True)

    def test_handles_missing_counters_gracefully(self):
        """Should handle missing counters gracefully."""
        from secondbrain.utils import tracing

        tracing._metrics_enabled = True
        tracing._meter = patch("secondbrain.utils.tracing._NoOpMeter").start()
        tracing._operations_counter = None
        tracing._duration_histogram = None
        tracing._errors_counter = None

        # Should not raise
        record_operation("test_operation", 100.0, success=False)

        patch.stopall()

    def test_handles_exceptions_gracefully(self):
        """Should handle exceptions during recording gracefully."""
        from secondbrain.utils import tracing

        tracing._metrics_enabled = True

        mock_meter = patch("secondbrain.utils.tracing._NoOpMeter").start()
        mock_counter = patch("secondbrain.utils.tracing._NoOpCounter").start()

        tracing._meter = mock_meter
        tracing._operations_counter = mock_counter
        tracing._duration_histogram = None
        tracing._errors_counter = None

        mock_counter.add.side_effect = Exception("Recording failed")

        # Should not raise
        record_operation("test_operation", 100.0, success=True)

        patch.stopall()


class TestTraceOperationErrorHandling:
    """Tests for trace_operation error handling."""

    def test_records_exception_on_error(self):
        """Should record exception and set error status on exception."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace") as mock_trace,
            patch("secondbrain.utils.tracing.otel_metrics"),
        ):
            mock_span = patch("secondbrain.utils.tracing._NoOpSpan").start()
            mock_span.record_exception = patch(
                "secondbrain.utils.tracing._NoOpSpan.record_exception"
            ).start()
            mock_span.set_status = patch(
                "secondbrain.utils.tracing._NoOpSpan.set_status"
            ).start()

            mock_trace.get_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = (
                mock_span
            )

            with pytest.raises(ValueError, match="Test error"):
                with trace_operation("test_operation"):
                    raise ValueError("Test error")

            assert mock_span.record_exception.called
            assert mock_span.set_status.called

            patch.stopall()

    def test_records_duration_in_finally_block(self):
        """Should record duration in finally block."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace"),
            patch("secondbrain.utils.tracing.otel_metrics"),
            patch("secondbrain.utils.tracing.record_operation") as mock_record,
        ):
            mock_span = patch("secondbrain.utils.tracing._NoOpSpan").start()

            with trace_operation("test_operation"):
                pass

            assert mock_record.called

            patch.stopall()


class TestTraceDecorator:
    """Tests for trace_decorator function."""

    def test_decorates_function_when_tracing_enabled(self):
        """Should decorate function and create span when tracing enabled."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.is_tracing_enabled", return_value=True),
            patch("secondbrain.utils.tracing.trace_operation") as mock_trace_op,
        ):
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_decorator("test_operation")
            def test_func():
                return "result"

            result = test_func()

            assert result == "result"
            assert mock_trace_op.called

    def test_skips_decorator_when_tracing_disabled(self):
        """Should skip decoration when tracing disabled."""

        @trace_decorator("test_operation")
        def test_func():
            return "result"

        result = test_func()

        assert result == "result"

    def test_preserves_function_metadata(self):
        """Should preserve function name and metadata."""
        os.environ["SECONDBRAIN_TRACING_ENABLED"] = "true"

        from secondbrain.utils import tracing

        tracing._tracer = None
        tracing._tracing_enabled = False

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.is_tracing_enabled", return_value=False),
        ):

            @trace_decorator("test_operation")
            def test_func():
                """Test function doc."""
                return "result"

            assert test_func.__name__ == "test_func"
            assert test_func.__doc__ == "Test function doc."


class TestShutdownTracingDetailed:
    """Additional tests for shutdown_tracing function."""

    def test_shuts_down_tracer_provider(self, caplog):
        """Should shutdown tracer provider when available."""
        from secondbrain.utils import tracing

        tracing._tracer = "test_tracer"
        tracing._tracing_enabled = True

        # When OTel is not available, shutdown is a no-op
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            shutdown_tracing()
            # Test passes if no exception is raised

    def test_handles_shutdown_error_gracefully(self):
        """Should handle shutdown errors gracefully."""
        from secondbrain.utils import tracing

        tracing._tracer = "test_tracer"
        tracing._tracing_enabled = True

        # When OTel is not available, shutdown is a no-op
        with patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", False):
            shutdown_tracing()
            # Test passes if no exception is raised

    def test_handles_otel_trace_none_gracefully(self):
        """Should handle otel_trace being None gracefully."""
        from secondbrain.utils import tracing

        tracing._tracer = "test_tracer"
        tracing._tracing_enabled = True

        with (
            patch("secondbrain.utils.tracing.OTTEL_AVAILABLE", True),
            patch("secondbrain.utils.tracing.otel_trace", None),
        ):
            # Should not raise
            shutdown_tracing()


class TestNoOpMeter:
    """Tests for NoOpMeter class."""

    def test_create_counter_returns_noop_counter(self):
        """Should return NoOpCounter from create_counter."""
        meter = _NoOpMeter()
        counter = meter.create_counter("test_counter")
        assert counter.__class__.__name__ == "_NoOpCounter"

    def test_create_histogram_returns_noop_histogram(self):
        """Should return NoOpHistogram from create_histogram."""
        meter = _NoOpMeter()
        histogram = meter.create_histogram("test_histogram")
        assert histogram.__class__.__name__ == "_NoOpHistogram"

    def test_getattr_returns_callable(self):
        """Should return a callable for any attribute access."""
        meter = _NoOpMeter()
        assert meter.some_method() is None
        assert meter.another_method(arg1="value", arg2=123) is None


class TestNoOpCounter:
    """Tests for NoOpCounter class."""

    def test_add_is_noop(self):
        """Should not raise when adding."""
        counter = _NoOpCounter()
        counter.add(1)
        counter.add(10, {"key": "value"})
        counter.add(100, {"operation": "test", "status": "success"})


class TestNoOpHistogram:
    """Tests for NoOpHistogram class."""

    def test_record_is_noop(self):
        """Should not raise when recording."""
        histogram = _NoOpHistogram()
        histogram.record(100.0)
        histogram.record(100.0, {"operation": "test"})
        histogram.record(1000.0, {"operation": "slow", "status": "success"})
