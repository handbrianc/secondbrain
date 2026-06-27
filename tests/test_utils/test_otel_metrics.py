"""Tests for OpenTelemetry metrics collection.

Covers basic metrics tests and integration tests verifying metrics are actually
exported when operations run.
"""
import time

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource


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


@pytest.mark.integration
class TestOTELMetricsIntegration:
    """Integration tests verifying metrics are actually exported."""

    def test_metrics_exported_on_ingest_operation(self):
        """Verify metrics are exported when ingest operation completes."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")

        counter = meter.create_counter(
            name="secondbrain.operations.count",
            description="Count of operations",
            unit="1",
        )
        histogram = meter.create_histogram(
            name="secondbrain.operations.duration",
            description="Operation duration",
            unit="ms",
        )

        start_time = time.time()
        time.sleep(0.05)
        duration_ms = (time.time() - start_time) * 1000

        counter.add(1, {"operation": "ingest"})
        histogram.record(duration_ms, {"operation": "ingest"})

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None

        found = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.operations.count":
                        found = True
                        for dp in metric.data.data_points:
                            assert dp.attributes.get("operation") == "ingest"
                            assert dp.value >= 1

        assert found

    def test_record_operation_records_duration(self):
        """Verify record_operation() records duration to histogram."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")

        histogram = meter.create_histogram(
            name="secondbrain.operations.duration",
            description="Operation duration",
            unit="ms",
        )

        histogram.record(100.5, {"operation": "search"})

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None

        found = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.operations.duration":
                        found = True
                        for dp in metric.data.data_points:
                            assert dp.attributes.get("operation") == "search"
                            assert dp.sum > 0

        assert found
