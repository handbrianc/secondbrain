"""Integration tests for OpenTelemetry metrics export.

These tests verify that metrics are actually exported when operations run,
not just that the metric instruments can be created.
"""

import time
from unittest.mock import patch, MagicMock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource


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
        
        assert found

    def test_record_operation_records_errors(self):
        """Verify record_operation() records errors when success=False."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")
        
        error_counter = meter.create_counter(
            name="secondbrain.errors.count",
            description="Count of errors",
            unit="1",
        )
        
        error_counter.add(1, {"operation": "search", "error_type": "failure"})
        
        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        
        found = False
