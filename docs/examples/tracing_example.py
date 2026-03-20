"""
Tracing Example with OpenTelemetry.

This example demonstrates how to use distributed tracing with OpenTelemetry
in SecondBrain for observability and performance monitoring.

Benefits of tracing:
- End-to-end request visibility
- Performance bottleneck identification
- Service dependency mapping
- Error tracking and debugging
"""

import time

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def setup_tracing() -> trace.Tracer:
    """Set up OpenTelemetry tracing."""
    # Create tracer provider
    resource = Resource.create(
        {
            "service.name": "secondbrain",
            "service.version": "0.3.0",
        }
    )

    provider = TracerProvider(resource=resource)

    # Add console exporter for demo
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    return trace.get_tracer("secondbrain")


def demonstrate_basic_tracing() -> None:
    """Demonstrate basic tracing functionality."""
    print("=" * 60)
    print("Basic Tracing Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    # Create a trace span
    with tracer.start_as_current_span("document-ingestion") as span:
        span.set_attribute("document.type", "pdf")
        span.set_attribute("document.size", 1024)

        print("  Ingesting document...")
        time.sleep(0.1)  # Simulate work

        span.set_attribute("document.status", "success")
        span.add_event("Document ingested successfully")

    print("  ✓ Trace completed")
    print()


def demonstrate_nested_spans() -> None:
    """Demonstrate nested spans for complex operations."""
    print("=" * 60)
    print("Nested Spans Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    with tracer.start_as_current_span("search-operation") as outer_span:
        outer_span.set_attribute("query.type", "semantic")

        # Simulate embedding generation
        with tracer.start_as_current_span("embedding-generation") as embedding_span:
            embedding_span.set_attribute("model", "all-MiniLM-L6-v2")
            print("  Generating embedding...")
            time.sleep(0.05)
            embedding_span.set_attribute("embedding.dimensions", 384)

        # Simulate database query
        with tracer.start_as_current_span("database-query") as db_span:
            db_span.set_attribute("collection", "documents")
            db_span.set_attribute("index", "embedding_index")
            print("  Querying database...")
            time.sleep(0.05)
            db_span.set_attribute("results.count", 5)

        # Simulate result processing
        with tracer.start_as_current_span("result-processing"):
            print("  Processing results...")
            time.sleep(0.02)

    print("  ✓ Nested trace completed")
    print()


def demonstrate_error_tracing() -> None:
    """Demonstrate error tracking in traces."""
    print("=" * 60)
    print("Error Tracing Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    span: trace.Span | None = None
    try:
        with tracer.start_as_current_span("operation-with-error") as span:
            print("  Attempting operation...")

            # Simulate error
            raise ValueError("Simulated error for demo")

    except Exception as e:
        # Record exception in span
        if span is not None:
            span.record_exception(e)
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            print(f"  ✓ Error recorded in trace: {e}")

    print()


def demonstrate_span_attributes() -> None:
    """Demonstrate useful span attributes."""
    print("=" * 60)
    print("Span Attributes Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    with tracer.start_as_current_span("ingestion-pipeline") as span:
        # Set various attributes
        span.set_attribute("pipeline.stage", "ingestion")
        span.set_attribute("pipeline.batch_size", 10)
        span.set_attribute("pipeline.worker_id", "worker-1")

        # Custom attributes
        span.set_attribute("user.id", "user-123")
        span.set_attribute("request.id", "req-456")
        span.set_attribute("environment", "development")

        print("  Processing batch...")
        time.sleep(0.05)

        # Update attributes
        span.set_attribute("documents.processed", 10)
        span.set_attribute("documents.success", 10)
        span.set_attribute("documents.failed", 0)

    print("  ✓ Span with attributes completed")
    print()


def demonstrate_timing_metrics() -> None:
    """Demonstrate timing and performance metrics."""
    print("=" * 60)
    print("Timing Metrics Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    start_time = time.time()

    with tracer.start_as_current_span("performance-test") as span:
        # Stage 1
        stage1_start = time.time()
        print("  Stage 1: Parsing...")
        time.sleep(0.03)
        stage1_duration = time.time() - stage1_start
        span.set_attribute("stage1.duration_ms", round(stage1_duration * 1000, 2))

        # Stage 2
        stage2_start = time.time()
        print("  Stage 2: Embedding...")
        time.sleep(0.04)
        stage2_duration = time.time() - stage2_start
        span.set_attribute("stage2.duration_ms", round(stage2_duration * 1000, 2))

        # Stage 3
        stage3_start = time.time()
        print("  Stage 3: Storage...")
        time.sleep(0.02)
        stage3_duration = time.time() - stage3_start
        span.set_attribute("stage3.duration_ms", round(stage3_duration * 1000, 2))

    total_duration = time.time() - start_time
    print(f"\n  Total duration: {round(total_duration * 1000, 2)}ms")
    print("  ✓ Timing metrics captured")
    print()


def demonstrate_context_propagation() -> None:
    """Demonstrate context propagation across operations."""
    print("=" * 60)
    print("Context Propagation Example")
    print("=" * 60)
    print()

    tracer = setup_tracing()

    # Parent span
    with tracer.start_as_current_span("parent-operation") as parent_span:
        parent_span.set_attribute("operation.id", "op-123")
        print("  Parent operation started")

        # Child operations (automatically linked via context)
        with tracer.start_as_current_span("child-operation-1"):
            print("    Child 1 executing...")
            time.sleep(0.02)

        with tracer.start_as_current_span("child-operation-2"):
            print("    Child 2 executing...")
            time.sleep(0.02)

    print("  ✓ Context propagated to child spans")
    print()


def demonstrate_production_tracing() -> None:
    """Demonstrate production tracing patterns."""
    print("=" * 60)
    print("Production Tracing Patterns")
    print("=" * 60)
    print()

    print("Pattern 1: Decorator-based tracing")
    print("-" * 40)
    print("""
from functools import wraps
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def traced_function(span_name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("function.name", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_attribute("status", "error")
                    raise
        return wrapper
    return decorator

@traced_function("document-processing")
def process_document(doc):
    # Processing logic
    pass
    """)

    print("\nPattern 2: Middleware-style tracing")
    print("-" * 40)
    print("""
def trace_middleware(request, next_handler):
    \"\"\"Middleware to trace HTTP requests.\"\"\"
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(f"http.{request.method}") as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)

        try:
            response = next_handler(request)
            span.set_attribute("http.status", response.status_code)
            return response
        except Exception as e:
            span.record_exception(e)
            raise
    """)

    print("\nPattern 3: Distributed tracing with OTLP exporter")
    print("-" * 40)
    print("""
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

# Setup OTLP exporter (e.g., Jaeger, Zipkin, Honeycomb)
exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
processor = SimpleSpanProcessor(exporter)
tracer_provider.add_span_processor(processor)
    """)

    print()


def main() -> None:
    """Run all tracing examples."""
    print("\n" + "=" * 60)
    print("SecondBrain OpenTelemetry Tracing Examples")
    print("=" * 60 + "\n")

    try:
        demonstrate_basic_tracing()
        demonstrate_nested_spans()
        demonstrate_error_tracing()
        demonstrate_span_attributes()
        demonstrate_timing_metrics()
        demonstrate_context_propagation()
        demonstrate_production_tracing()

        print("=" * 60)
        print("Key Takeaways")
        print("=" * 60)
        print("""
1. Use spans to trace operations end-to-end
2. Add meaningful attributes for filtering and analysis
3. Record exceptions for error tracking
4. Use nested spans for complex operations
5. Configure OTLP exporter for production use

For more information, see:
- docs/developer-guide/observability.md (complete tracing guide)
- src/secondbrain/utils/tracing.py (tracing implementation)
- https://opentelemetry.io/docs/ (OpenTelemetry documentation)
        """)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
