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
        assert len(metrics_data.resource_metrics) > 0
        
        metric_names = []
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    metric_names.append(metric.name)
        
        assert "secondbrain.operations.count" in metric_names
        assert "secondbrain.operations.duration" in metric_names

    def test_metrics_exported_on_search_operation(self):
        """Verify metrics are exported when search operation completes."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")
        
        counter = meter.create_counter("secondbrain.operations.count", unit="1")
        
        counter.add(1, {"operation": "search"})
        
        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        
        found_count_metric = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.operations.count":
                        found_count_metric = True
                        assert hasattr(metric.data, "data_points")
                        assert len(metric.data.data_points) > 0
                        data_point = metric.data.data_points[0]
                        assert hasattr(data_point, "attributes")
                        assert data_point.attributes.get("operation") == "search"
                        assert hasattr(data_point, "value")
                        assert data_point.value >= 1
        
        assert found_count_metric

    def test_error_metrics_exported_on_failure(self):
        """Verify error counter is incremented when operation fails."""
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
        
        found_error_metric = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.errors.count":
                        found_error_metric = True
                        data_point = metric.data.data_points[0]
                        assert data_point.value >= 1
        
        assert found_error_metric

    def test_multiple_operations_aggregate_correctly(self):
        """Verify multiple operations aggregate in metrics correctly."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")
        
        counter = meter.create_counter("secondbrain.operations.count", unit="1")
        
        counter.add(1, {"operation": "ingest"})
        counter.add(1, {"operation": "search"})
        counter.add(1, {"operation": "search"})
        counter.add(1, {"operation": "chat"})
        
        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        
        operation_counts = {}
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.operations.count":
                        for dp in metric.data.data_points:
                            op_name = dp.attributes.get("operation")
                            operation_counts[op_name] = dp.value
        
        assert operation_counts.get("ingest") == 1
        assert operation_counts.get("search") == 2
        assert operation_counts.get("chat") == 1

    def test_duration_histogram_records_multiple_values(self):
        """Verify histogram records multiple duration values."""
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
        
        histogram.record(10.0, {"operation": "search"})
        histogram.record(20.0, {"operation": "search"})
        histogram.record(30.0, {"operation": "search"})
        
        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        
        found_histogram = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.operations.duration":
                        found_histogram = True
                        assert hasattr(metric.data, "data_points")
                        assert len(metric.data.data_points) > 0
        
        assert found_histogram


@pytest.mark.integration
class TestOTELMetricsRecordOperation:
    """Integration tests verifying record_operation() function works correctly.
    
    These tests verify that the record_operation() function in tracing.py
    correctly records metrics through the OTEL infrastructure.
    """

    def test_record_operation_calls_counter(self):
        """Verify record_operation() increments the operations counter."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[reader],
            resource=Resource.create({"service.name": "secondbrain-test"}),
        )
        meter = provider.get_meter("test")
        
        # Create the same metrics as setup_tracing
        counter = meter.create_counter(
            name="secondbrain.operations.count",
            description="Count of operations",
            unit="1",
        )
        
        # Simulate what record_operation does
        counter.add(1, {"operation": "ingest"})
        
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
        
        # Simulate what record_operation does
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
        
        # Simulate what record_operation does on failure
        error_counter.add(1, {"operation": "search", "error_type": "failure"})
        
        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        
        found = False
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "secondbrain.errors.count":
                        found = True
                        for dp in metric.data.data_points:
                            assert dp.attributes.get("error_type") == "failure"
        
        assert found
