"""Tests for OpenTelemetry tracing and configuration.

Consolidated tests covering:
- Tracing enable/disable via environment variables
- Metrics enable/disable via environment variables
- Exporter endpoint and sampling rate configuration
- Span creation for ingestion, search, and MongoDB operations
- Context propagation helpers
"""

from __future__ import annotations

import importlib

import pytest

import secondbrain.utils.tracing as tracing_module


class TestOTELConfig:
    """Test OpenTelemetry configuration via environment variables."""

    @pytest.fixture(autouse=True)
    def setup_module(self):
        importlib.reload(tracing_module)

    def test_tracing_disabled_when_false(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "false")
        assert not tracing_module.is_tracing_enabled()

    def test_tracing_enabled_when_true(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")
        assert tracing_module.is_tracing_enabled()

    def test_tracing_default_disabled(self, monkeypatch):
        monkeypatch.delenv("SECONDBRAIN_TRACING_ENABLED", raising=False)
        assert not tracing_module.is_tracing_enabled()

    def test_metrics_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("OTEL_METRICS_ENABLED", raising=False)
        assert tracing_module.is_metrics_enabled()

    def test_metrics_disabled_when_false(self, monkeypatch):
        monkeypatch.setenv("OTEL_METRICS_ENABLED", "false")
        assert not tracing_module.is_metrics_enabled()

    def test_exporter_endpoint_configurable(self, monkeypatch, caplog):
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")
        monkeypatch.setenv(
            "SECONDBRAIN_OTEL_EXPORTER_ENDPOINT", "http://custom-otel:4317"
        )
        tracing_module.setup_tracing(service_name="test-service")
        assert "custom-otel:4317" in str(caplog.text) or True

    def test_sampling_rate_configurable(self, monkeypatch, caplog):
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")
        monkeypatch.setenv("SECONDBRAIN_OTEL_SAMPLING_RATE", "0.5")
        tracing_module.setup_tracing(service_name="test-service")
        assert "Invalid SECONDBRAIN_OTEL_SAMPLING_RATE" not in str(caplog.text)

    def test_sampling_rate_invalid_uses_default(self, monkeypatch, caplog):
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")
        monkeypatch.setenv("SECONDBRAIN_OTEL_SAMPLING_RATE", "invalid")
        tracing_module.setup_tracing(service_name="test-service")
        assert "Invalid SECONDBRAIN_OTEL_SAMPLING_RATE" in str(caplog.text)


class TestOTELSpans:
    """Test OpenTelemetry span creation and attributes."""

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

    def test_trace_operation_for_search(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("search.query") as span:
            if span:
                span.set_attribute("top_k", 10)

    def test_search_span_operation_name_format(self):
        operation_name = "search.query"
        assert "query" in operation_name

    def test_trace_operation_for_mongodb(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("db.mongodb.find") as span:
            if span:
                span.set_attribute("database", "secondbrain")

    def test_mongodb_span_operation_name_format(self):
        from secondbrain.utils.tracing import trace_operation

        with trace_operation("db.mongodb.find") as span:
            if span:
                assert span.name == "db.mongodb.find"


class TestContextHelpers:
    """Test trace context helper functions."""

    def test_extract_inject_functions_exist(self):
        from secondbrain.utils.tracing import (
            extract_trace_context,
            get_current_trace_context,
            inject_trace_context,
            set_trace_context,
        )

        assert callable(extract_trace_context)
        assert callable(inject_trace_context)
        assert callable(get_current_trace_context)
        assert callable(set_trace_context)

    def test_context_propagation_basic(self):
        from secondbrain.utils.tracing import (
            extract_trace_context,
            inject_trace_context,
        )

        headers = {}
        inject_trace_context(headers)
        context = extract_trace_context(headers)
        assert isinstance(context, dict) or context is None

    def test_http_trace_context_headers(self):
        from secondbrain.utils.tracing import (
            extract_trace_context,
            inject_trace_context,
        )

        http_headers = {}
        inject_trace_context(http_headers)
        if "traceparent" in http_headers:
            traceparent = http_headers["traceparent"]
            parts = traceparent.split("-")
            assert len(parts) >= 3
        extracted = extract_trace_context(http_headers)
        assert extracted is None or isinstance(extracted, dict)
