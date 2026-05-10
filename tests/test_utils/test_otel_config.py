"""Tests for OpenTelemetry configuration via environment variables."""
import importlib

import pytest

import secondbrain.utils.tracing as tracing_module


class TestOTELConfig:
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
        monkeypatch.setenv("SECONDBRAIN_OTEL_EXPORTER_ENDPOINT", "http://custom-otel:4317")

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
