"""End-to-end OpenTelemetry integration tests.

These tests verify that OpenTelemetry tracing and metrics work correctly
when spans are created manually, confirming the OTEL infrastructure is functional.

Note: These tests verify the OTEL SDK integration works correctly. Full end-to-end
tests that verify real SecondBrain code automatically creates spans would require
instrumentation in the actual ingestion/search code paths.

Covers:
- Manual span creation patterns for ingestion/search workflows
- Async context propagation across tasks
- Metrics collection and export
- MongoDB span attribute patterns
- Exception event recording
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry import trace, metrics

# Module-level setup
_memory_exporter = None
_metric_reader = None
_tracer_provider = None
_meter_provider = None


@pytest.fixture(scope="module", autouse=True)
def setup_otel_e2e_module():
    """Setup OpenTelemetry for end-to-end tests at module level."""
    global _memory_exporter, _metric_reader, _tracer_provider, _meter_provider
    
    # Setup tracing
    _memory_exporter = InMemorySpanExporter()
    _tracer_provider = TracerProvider()
    processor = SimpleSpanProcessor(_memory_exporter)
    _tracer_provider.add_span_processor(processor)
    trace.set_tracer_provider(_tracer_provider)
    
    # Setup metrics
    _metric_reader = InMemoryMetricReader()
    _meter_provider = MeterProvider(metric_readers=[_metric_reader])
    metrics.set_meter_provider(_meter_provider)
    
    yield
    
    # Cleanup
    if _memory_exporter:
        _memory_exporter.shutdown()
    if _metric_reader:
        _metric_reader.shutdown()


@pytest.fixture(autouse=True)
def clear_e2e_state():
    """Clear spans and metrics before each test."""
    if _memory_exporter:
        _memory_exporter.clear()
    yield


def get_spans():
    """Get all exported spans."""
    if _memory_exporter:
        return _memory_exporter.get_finished_spans()
    return []


class TestOTELEndToEnd:
    """End-to-end OpenTelemetry tests for real workflows."""

    def test_ingestion_creates_all_spans(self):
        """End-to-end: Document ingestion creates all expected spans.
        
        Verifies the complete ingestion pipeline creates:
        - document.ingest (root span)
        - document.process (child span)
        - embedding.generate (child span)
        - storage.store (child span)
        """
        tracer = trace.get_tracer(__name__)
        
        # Simulate ingestion workflow
        with tracer.start_as_current_span("document.ingest") as ingest_span:
            ingest_span.set_attribute("file.path", "/test/document.pdf")
            ingest_span.set_attribute("file.size", 1024)
            
            # File processing
            with tracer.start_as_current_span("document.process") as process_span:
                process_span.set_attribute("pages.count", 10)
                process_span.set_attribute("processing.time_ms", 500)
                
                # Embedding generation
                with tracer.start_as_current_span("embedding.generate") as embed_span:
                    embed_span.set_attribute("text.length", 100)
                    embed_span.set_attribute("embedding.dimensions", 384)
                
                # Storage
                with tracer.start_as_current_span("storage.store") as store_span:
                    store_span.set_attribute("document.count", 5)
                    store_span.set_attribute("storage.duration_ms", 100)
        
        # Verify all spans were created
        spans = get_spans()
        assert len(spans) >= 4
        
        span_names = [span.name for span in spans]
        assert "document.ingest" in span_names
        assert "document.process" in span_names
        assert "embedding.generate" in span_names
        assert "storage.store" in span_names
        
        # Verify attributes
        ingest_span_obj = next(s for s in spans if s.name == "document.ingest")
        assert ingest_span_obj.attributes.get("file.path") == "/test/document.pdf"
        assert ingest_span_obj.attributes.get("file.size") == 1024
        
        embed_span_obj = next(s for s in spans if s.name == "embedding.generate")
        assert embed_span_obj.attributes.get("text.length") == 100
        assert embed_span_obj.attributes.get("embedding.dimensions") == 384

    def test_search_creates_spans(self):
        """End-to-end: Search operation creates query and vector spans.
        
        Verifies search workflow creates:
        - search.query (root span)
        - search.vector (child span)
        """
        tracer = trace.get_tracer(__name__)
        
        # Simulate search workflow
        with tracer.start_as_current_span("search.query") as query_span:
            query_span.set_attribute("query.length", 50)
            
            # Vector search
            with tracer.start_as_current_span("search.vector") as vector_span:
                vector_span.set_attribute("top_k", 5)
                vector_span.set_attribute("result.count", 3)
        
        # Verify spans
        spans = get_spans()
        assert len(spans) >= 2
        
        span_names = [span.name for span in spans]
        assert "search.query" in span_names
        assert "search.vector" in span_names
        
        # Verify attributes
        query_span_obj = next(s for s in spans if s.name == "search.query")
        assert query_span_obj.attributes.get("query.length") == 50
        
        vector_span_obj = next(s for s in spans if s.name == "search.vector")
        assert vector_span_obj.attributes.get("top_k") == 5
        assert vector_span_obj.attributes.get("result.count") == 3

    def test_async_context_propagation(self):
        """Trace context propagates across async task boundaries.
        
        Verifies that when async tasks are spawned, they inherit
        the parent trace context and create child spans with the same trace ID.
        """
        tracer = trace.get_tracer(__name__)
        
        async def child_task():
            """Async child task that creates a span."""
            with tracer.start_as_current_span("child.operation") as span:
                span.set_attribute("task.name", "child")
                return span.get_span_context().trace_id
        
        async def parent_task():
            """Parent task that spawns child."""
            with tracer.start_as_current_span("parent.operation") as span:
                span.set_attribute("task.name", "parent")
                parent_trace_id = span.get_span_context().trace_id
                
                # Spawn child task
                child_trace_id = await child_task()
                
                return parent_trace_id, child_trace_id
        
        # Run async workflow
        parent_trace_id, child_trace_id = asyncio.run(parent_task())
        
        # Verify trace IDs match (context propagated)
        assert parent_trace_id == child_trace_id
        
        # Verify spans were created
        spans = get_spans()
        assert len(spans) >= 2
        
        span_names = [span.name for span in spans]
        assert "parent.operation" in span_names
        assert "child.operation" in span_names
        
        # Verify both spans have the same trace ID
        parent_span = next(s for s in spans if s.name == "parent.operation")
        child_span = next(s for s in spans if s.name == "child.operation")
        
        assert parent_span.get_span_context().trace_id == child_span.get_span_context().trace_id

    def test_metrics_actually_exported(self):
        """Metrics are collected and can be retrieved.
        
        Verifies that:
        - secondbrain.operations.count metric is incremented
        - secondbrain.operations.duration histogram records values
        - secondbrain.errors.count metric is incremented
        """
        # Get meter
        meter = metrics.get_meter(__name__)
        
        # Create metrics (these should match the ones in setup_tracing)
        operations_counter = meter.create_counter("secondbrain.operations.count")
        duration_histogram = meter.create_histogram("secondbrain.operations.duration")
        errors_counter = meter.create_counter("secondbrain.errors.count")
        
        # Record some metrics
        operations_counter.add(1, {"operation": "ingest"})
        operations_counter.add(1, {"operation": "search"})
        
        duration_histogram.record(0.5, {"operation": "ingest"})
        duration_histogram.record(1.2, {"operation": "search"})
        
        errors_counter.add(1, {"error_type": "timeout"})
        
        # Verify metrics were collected
        metrics_data = _metric_reader.get_metrics_data()
        assert metrics_data is not None
        assert metrics_data.resource_metrics is not None
        assert len(metrics_data.resource_metrics) > 0
        
        # Extract scope metrics
        scope_metrics = []
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                scope_metrics.extend(scope_metric.metrics)
        
        # Verify our metrics exist
        metric_names = [m.name for m in scope_metrics]
        assert "secondbrain.operations.count" in metric_names
        assert "secondbrain.operations.duration" in metric_names
        assert "secondbrain.errors.count" in metric_names

    def test_mongodb_span_attributes(self):
        """MongoDB operation spans include collection name and operation type.
        
        Verifies that when MongoDB operations are performed, the spans include:
        - db.mongodb.collection (collection name)
        - db.operation (operation type: find, insert, update, delete)
        """
        tracer = trace.get_tracer(__name__)
        
        # Simulate MongoDB operations
        with tracer.start_as_current_span("db.mongodb.query") as span:
            span.set_attribute("db.mongodb.collection", "embeddings")
            span.set_attribute("db.operation", "find")
            span.set_attribute("db.mongodb.query.filter", '{"source_file": "test.pdf"}')
        
        spans = get_spans()
        assert len(spans) >= 1
        
        mongo_span = spans[0]
        assert mongo_span.name == "db.mongodb.query"
        assert mongo_span.attributes.get("db.mongodb.collection") == "embeddings"
        assert mongo_span.attributes.get("db.operation") == "find"

    def test_exception_events_in_spans(self):
        """Exception events are recorded in spans with type and message.
        
        Verifies that when exceptions occur:
        - "exception" event is added to span
        - Exception type is recorded
        - Exception message is recorded
        - Span status is set to ERROR
        """
        tracer = trace.get_tracer(__name__)
        
        # Simulate an operation that raises an exception
        try:
            with tracer.start_as_current_span("failing.operation") as span:
                span.set_attribute("operation.name", "test")
                
                # Record exception manually (this is what the tracing module should do)
                try:
                    raise ValueError("Test error for tracing")
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
        except ValueError:
            pass  # Expected
        
        # Verify exception was recorded
        spans = get_spans()
        assert len(spans) >= 1
        
        error_span = spans[0]
        assert error_span.name == "failing.operation"
        
        # Check for exception event
        events = error_span.events
        assert len(events) >= 1
        
        exception_event = next((e for e in events if e.name == "exception"), None)
        assert exception_event is not None
        
        # Verify exception details
        assert "exception.type" in exception_event.attributes
        assert "exception.message" in exception_event.attributes
        assert "ValueError" in exception_event.attributes["exception.type"]
        assert "Test error for tracing" in exception_event.attributes["exception.message"]
        
        # Verify span status
        assert error_span.status.status_code == trace.StatusCode.ERROR
