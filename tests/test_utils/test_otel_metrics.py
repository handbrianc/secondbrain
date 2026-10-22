"""Tests for OpenTelemetry metrics collection.

The instrument names used here are the production names wired in
``secondbrain.utils.tracing.setup_tracing`` (tracing.py:291-295):
``secondbrain_operations``, ``secondbrain_operation_duration_ms`` and
``secondbrain_errors``. The integration tests drive the REAL
``record_operation`` over an ``InMemoryMetricReader`` (same pattern as
``test_otel_integration.py::test_metrics_actually_exported``), so the two
files agree on instrument names.
"""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import Histogram, InMemoryMetricReader, Sum
from opentelemetry.sdk.resources import Resource

# Production instrument names (secondbrain/utils/tracing.py:291-295).
OPERATIONS_COUNTER = "secondbrain_operations"
DURATION_HISTOGRAM = "secondbrain_operation_duration_ms"
ERRORS_COUNTER = "secondbrain_errors"


def _collect_metric_names(metrics_data) -> set[str]:
    """Collect the instrument names present in collected metrics data."""
    return {
        metric.name
        for resource_metric in metrics_data.resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
    }


def _collect_data_points(metrics_data) -> tuple[dict[str, list], dict[str, list]]:
    """Split collected data points into ``{name: [points]}`` sums/histograms."""
    sums: dict[str, list] = {}
    histograms: dict[str, list] = {}
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if isinstance(metric.data, Sum):
                    sums.setdefault(metric.name, []).extend(metric.data.data_points)
                elif isinstance(metric.data, Histogram):
                    histograms.setdefault(metric.name, []).extend(
                        metric.data.data_points
                    )
    return sums, histograms


class TestOTELMetrics:
    """Test OpenTelemetry metrics are collected under production instrument names."""

    def test_operations_counter_works(self):
        """Operations counter increments for each operation."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")

        counter = meter.create_counter(OPERATIONS_COUNTER)
        counter.add(1, {"operation": "ingest"})
        counter.add(1, {"operation": "search"})

        sums, _ = _collect_data_points(reader.get_metrics_data())
        op_points = sums.get(OPERATIONS_COUNTER, [])
        by_operation = {dp.attributes.get("operation"): dp.value for dp in op_points}
        assert by_operation["ingest"] >= 1
        assert by_operation["search"] >= 1

    def test_duration_histogram_records(self):
        """Duration histogram records operation timing."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")

        histogram = meter.create_histogram(DURATION_HISTOGRAM)
        histogram.record(0.5, {"operation": "ingest"})
        histogram.record(1.2, {"operation": "search"})

        _, histograms = _collect_data_points(reader.get_metrics_data())
        hist_points = histograms.get(DURATION_HISTOGRAM, [])
        by_operation = {dp.attributes.get("operation"): dp for dp in hist_points}
        assert by_operation["ingest"].count >= 1
        assert by_operation["ingest"].sum >= 0.5
        assert by_operation["search"].sum >= 1.2

    def test_error_counter_works(self):
        """Error counter increments on failures."""
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test")

        error_counter = meter.create_counter(ERRORS_COUNTER)
        error_counter.add(1, {"error_type": "timeout"})
        error_counter.add(1, {"error_type": "connection_error"})

        sums, _ = _collect_data_points(reader.get_metrics_data())
        error_points = sums.get(ERRORS_COUNTER, [])
        by_error_type = {
            dp.attributes.get("error_type"): dp.value for dp in error_points
        }
        assert by_error_type["timeout"] >= 1
        assert by_error_type["connection_error"] >= 1


def _wire_real_record_operation(monkeypatch, reader):
    """Point the tracing module's globals at production-named instruments.

    Mirrors the instrument wiring ``setup_tracing`` performs
    (tracing.py:291-295) over an in-memory reader, so the REAL
    ``record_operation`` can be driven and its exported data points asserted.
    """
    from secondbrain.utils import tracing as tracing_mod

    provider = MeterProvider(
        metric_readers=[reader],
        resource=Resource.create({"service.name": "secondbrain-test"}),
    )
    meter = provider.get_meter("secondbrain.tracing.record_operation")
    monkeypatch.setattr(tracing_mod, "_metrics_enabled", True)
    monkeypatch.setattr(tracing_mod, "_meter", meter)
    monkeypatch.setattr(
        tracing_mod,
        "_operations_counter",
        meter.create_counter(OPERATIONS_COUNTER),
    )
    monkeypatch.setattr(
        tracing_mod,
        "_duration_histogram",
        meter.create_histogram(DURATION_HISTOGRAM),
    )
    monkeypatch.setattr(
        tracing_mod,
        "_errors_counter",
        meter.create_counter(ERRORS_COUNTER),
    )
    return tracing_mod


@pytest.mark.integration
class TestOTELMetricsIntegration:
    """Integration tests verifying the real record_operation exports metrics."""

    def test_metrics_exported_on_ingest_operation(self, monkeypatch):
        """Verify metrics are exported when ingest operation completes."""
        reader = InMemoryMetricReader()
        tracing_mod = _wire_real_record_operation(monkeypatch, reader)

        tracing_mod.record_operation("ingest", 25.0, success=True)

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        names = _collect_metric_names(metrics_data)
        assert OPERATIONS_COUNTER in names
        assert DURATION_HISTOGRAM in names
        assert ERRORS_COUNTER not in names

        sums, histograms = _collect_data_points(metrics_data)
        ingest_sums = [
            dp
            for dp in sums.get(OPERATIONS_COUNTER, [])
            if dp.attributes.get("operation") == "ingest"
        ]
        assert ingest_sums, "operations counter must carry the 'ingest' label"
        assert sum(dp.value for dp in ingest_sums) >= 1

        ingest_histograms = [
            dp
            for dp in histograms.get(DURATION_HISTOGRAM, [])
            if dp.attributes.get("operation") == "ingest"
        ]
        assert ingest_histograms, "duration histogram must carry the 'ingest' label"
        assert sum(dp.count for dp in ingest_histograms) >= 1
        assert sum(dp.sum for dp in ingest_histograms) >= 25.0

    def test_record_operation_records_duration(self, monkeypatch):
        """Verify record_operation() records duration to the histogram."""
        reader = InMemoryMetricReader()
        tracing_mod = _wire_real_record_operation(monkeypatch, reader)

        tracing_mod.record_operation("search", 100.5, success=True)

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        sums, histograms = _collect_data_points(metrics_data)

        search_histograms = [
            dp
            for dp in histograms.get(DURATION_HISTOGRAM, [])
            if dp.attributes.get("operation") == "search"
        ]
        assert search_histograms, "duration histogram must carry the 'search' label"
        assert sum(dp.count for dp in search_histograms) >= 1
        assert sum(dp.sum for dp in search_histograms) >= 100.5

        # A successful operation never feeds the errors counter.
        assert not any(
            dp.attributes.get("operation") == "search"
            for dp in sums.get(ERRORS_COUNTER, [])
        )

    def test_error_counter_increments_only_on_failure(self, monkeypatch):
        """record_operation(success=False) feeds only the errors counter."""
        reader = InMemoryMetricReader()
        tracing_mod = _wire_real_record_operation(monkeypatch, reader)

        tracing_mod.record_operation("search", 3.0, success=False)

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        sums, _ = _collect_data_points(metrics_data)

        error_points = sums.get(ERRORS_COUNTER, [])
        failures = [
            dp for dp in error_points if dp.attributes.get("operation") == "search"
        ]
        assert failures, "errors counter must carry the 'search' label on failure"
        assert sum(dp.value for dp in failures) >= 1
        assert all(dp.attributes.get("error_type") == "failure" for dp in failures)
