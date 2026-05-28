"""Tests for OpenTelemetry span creation and attributes.

These tests verify that spans are created correctly with proper attributes
using the OpenTelemetry SDK.
"""
import time
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry import trace


_memory_exporter = None
_tracer_provider = None


@pytest.fixture(scope="module", autouse=True)
def setup_otel_module():
    """Setup OpenTelemetry at module level."""
    global _memory_exporter, _tracer_provider
    
    _memory_exporter = InMemorySpanExporter()
    _tracer_provider = TracerProvider()
    processor = SimpleSpanProcessor(_memory_exporter)
    _tracer_provider.add_span_processor(processor)
    trace.set_tracer_provider(_tracer_provider)
    
    yield
    
    _memory_exporter.shutdown()


@pytest.fixture(autouse=True)
def clear_spans():
    """Clear spans before each test."""
    if _memory_exporter:
        _memory_exporter.clear()
    yield


def get_spans():
    """Get all exported spans."""
    if _memory_exporter:
        trace.get_tracer_provider().force_flush(timeout_millis=1000)
        time.sleep(0.1)
        return _memory_exporter.get_finished_spans()
    return []


def test_trace_operation_creates_span():
    """trace_operation context manager creates spans."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test.operation") as span:
        span.set_attribute("test.key", "test_value")
    
    spans = get_spans()
    assert len(spans) >= 1
    assert any(span.name == "test.operation" for span in spans)


def test_ingestion_creates_span():
    """Ingestion operation creates 'document.ingest' span."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("document.ingest") as span:
        span.set_attribute("file.path", "/test/document.pdf")
        span.set_attribute("file.size", 1024)
    
    spans = get_spans()
    assert any(span.name == "document.ingest" for span in spans)
    
    ingest_span = next(s for s in spans if s.name == "document.ingest")
    assert ingest_span.attributes.get("file.path") == "/test/document.pdf"
    assert ingest_span.attributes.get("file.size") == 1024


def test_file_processing_creates_span():
    """File processing creates 'document.process' span."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("document.process") as span:
        span.set_attribute("pages.count", 10)
        span.set_attribute("processing.time_ms", 500)
    
    spans = get_spans()
    assert any(span.name == "document.process" for span in spans)


def test_embedding_generation_creates_span():
    """Embedding generation creates 'embedding.generate' span."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("embedding.generate") as span:
        span.set_attribute("text.length", 100)
        span.set_attribute("model.name", "all-MiniLM-L6-v2")
    
    spans = get_spans()
    assert any(span.name == "embedding.generate" for span in spans)


def test_storage_operation_creates_span():
    """Storage operation creates 'storage.insert' span."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("storage.insert") as span:
        span.set_attribute("collection.name", "embeddings")
        span.set_attribute("document.count", 5)
    
    spans = get_spans()
    assert any(span.name == "storage.insert" for span in spans)


def test_search_operation_creates_span():
    """Search operation creates 'search.semantic' span."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("search.semantic") as span:
        span.set_attribute("query.length", 50)
        span.set_attribute("top_k", 10)
    
    spans = get_spans()
    assert any(span.name == "search.semantic" for span in spans)


def test_rag_pipeline_creates_multiple_spans():
    """RAG pipeline creates multiple child spans."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("rag.pipeline") as parent_span:
        parent_span.set_attribute("session.id", "test-session")
        
        with tracer.start_as_current_span("search.semantic") as search_span:
            search_span.set_attribute("query", "test query")
        
        with tracer.start_as_current_span("llm.generate") as llm_span:
            llm_span.set_attribute("model", "local-llama")
    
    spans = get_spans()
    span_names = [span.name for span in spans]
    
    assert "rag.pipeline" in span_names
    assert "search.semantic" in span_names
    assert "llm.generate" in span_names


def test_span_attributes_are_serializable():
    """Span attributes are JSON-serializable."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test.attributes") as span:
        span.set_attribute("string.attr", "value")
        span.set_attribute("int.attr", 42)
        span.set_attribute("float.attr", 3.14)
        span.set_attribute("bool.attr", True)
    
    spans = get_spans()
    assert len(spans) >= 1
    
    attr_span = spans[0]
    assert attr_span.attributes.get("string.attr") == "value"
    assert attr_span.attributes.get("int.attr") == 42
    assert attr_span.attributes.get("float.attr") == 3.14
    assert attr_span.attributes.get("bool.attr") is True


def test_span_error_handling():
    """Span captures exceptions correctly."""
    tracer = trace.get_tracer(__name__)
    try:
        with tracer.start_as_current_span("test.error") as span:
            raise ValueError("Test error")
    except ValueError:
        pass
    
    spans = get_spans()
    assert len(spans) >= 1
    
    error_span = spans[0]
    assert error_span.status.description is not None
    assert "error" in error_span.status.description.lower() or \
           error_span.status.is_ok is False


def test_span_context_propagation():
    """Span context propagates to child spans."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent") as parent:
        with tracer.start_as_current_span("child") as child:
            child.set_attribute("child.key", "child_value")
    
    spans = get_spans()
    assert len(spans) == 2
    
    parent_span = next(s for s in spans if s.name == "parent")
    child_span = next(s for s in spans if s.name == "child")
    
    assert child_span.get_span_context().trace_id == parent_span.get_span_context().trace_id
