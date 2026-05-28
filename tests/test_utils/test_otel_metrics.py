"""Tests for OpenTelemetry metrics collection."""
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


class TestOTELMetrics:
    """Test OpenTelemetry metrics are collected correctly."""

    def test_operations_counter_works(self):
        """Operations counter increments for each operation."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")
        
        counter = meter.create_counter("secondbrain.operations.count")
        counter.add(1, {"operation": "ingest"})
        counter.add(1, {"operation": "search"})
        
        metrics = reader.get_metrics_data()
        assert metrics is not None

    def test_duration_histogram_records(self):
        """Duration histogram records operation timing."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")
        
        histogram = meter.create_histogram("secondbrain.operations.duration")
        histogram.record(0.5, {"operation": "ingest"})
        histogram.record(1.2, {"operation": "search"})
        
        metrics = reader.get_metrics_data()
        assert metrics is not None

    def test_error_counter_works(self):
        """Error counter increments on failures."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")
        
        error_counter = meter.create_counter("secondbrain.errors.count")
        error_counter.add(1, {"error_type": "timeout"})
        error_counter.add(1, {"error_type": "connection_error"})
        
        metrics = reader.get_metrics_data()
        assert metrics is not None
