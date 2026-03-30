# ADR-007: OpenTelemetry Integration for Observability

**Status**: Accepted  
**Created**: 2026-03-30  
**Authors**: SecondBrain Team  
**Deciders**: Architecture Team

## Context

SecondBrain requires comprehensive observability for:

- Debugging distributed operations (ingestion, search)
- Performance monitoring and optimization
- Correlation IDs across async operations
- Metrics collection (latency, throughput, errors)
- Production deployment support

## Decision

**Integrate OpenTelemetry (OTel)** as the observability standard:

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   SecondBrain App                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   Logging   │  │   Tracing   │  │   Metrics   │ │
│  │  (Structured│  │(OpenTelemetry)│ (OpenTelemetry)│ │
│  │   + Correlation)│            │              │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │                │                │        │
│         └────────────────┴────────────────┘        │
│                          │                         │
└──────────────────────────┼─────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │    OTLP Exporter        │
              │  (Configurable Endpoint)│
              └────────────┬────────────┘
                           │
              ┌────────────┴────────────┐
              │  Observability Backend  │
              │  (Jaeger, Prometheus,   │
              │   Grafana, etc.)        │
              └─────────────────────────┘
```

### Tracing Implementation

```python
from secondbrain.utils.tracing import trace_operation, get_tracer

# Decorator for function tracing
@trace_operation("ingest_document")
async def ingest_document(doc_path: Path):
    # Automatic span creation
    await parse_document(doc_path)
    await generate_embeddings(text)
    await store_in_mongodb(embeddings)

# Manual span creation
tracer = get_tracer()
with tracer.start_as_current_span("search_query") as span:
    span.set_attribute("query", user_query)
    span.set_attribute("collection", "documents")
    results = await retrieve_documents(user_query)
```

### Metrics Implementation

```python
from secondbrain.utils.metrics import otel_metrics_collector

# Create metrics
counter = otel_metrics_collector.create_counter("documents_ingested")
histogram = otel_metrics_collector.create_histogram("query_latency")
gauge = otel_metrics_collector.create_gauge("active_connections")

# Record metrics
counter.add(1, {"source": "cli"})
histogram.record(duration_seconds, {"operation": "search"})
gauge.set(current_connections, {"host": "localhost"})
```

### Logging Integration

```python
from secondbrain.logging import get_logger, set_trace_context

# Correlation ID automatically flows through logs
logger = get_logger(__name__)
logger.info("Processing document", extra={"extra_fields": {"doc_id": "123"}})

# Logs include trace context
# {"level": "INFO", "trace_id": "abc123", "span_id": "def456", ...}
```

### Configuration

```bash
# Enable OTLP exporter
export OTEL_TRACING_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_TIMEOUT=10

# Service identification
export OTEL_SERVICE_NAME=secondbrain
export OTEL_SERVICE_VERSION=0.4.0
export OTEL_ENVIRONMENT=production
```

## Consequences

### Positive

- **Standardization**: OpenTelemetry is CNCF standard
- **Vendor Neutral**: Can switch backends without code changes
- **Comprehensive**: Logs, traces, and metrics in one framework
- **Async Support**: Full async context propagation
- **Production Ready**: Battle-tested by large organizations

### Negative

- **Complexity**: Additional dependencies and configuration
- **Resource Usage**: OTel SDK adds ~50-100MB memory overhead
- **Setup Required**: Need observability backend (Jaeger, etc.)
- **Learning Curve**: Team needs OTel expertise

### Risks

- **Over-Instrumentation**: Too much tracing data can overwhelm
- **Backend Dependency**: Observability depends on backend availability
- **Version Compatibility**: OTel SDK and backend must be compatible

## Span Hierarchy

```
ingest_document
├── document.parse
├── document.embed
└── document.store

search_query
├── query.retrieval
└── query.rerank

rag_pipeline
├── pipeline.retrieve
└── pipeline.generate
```

## Performance Impact

**Tracing Overhead**:

| Configuration | Latency Impact | Memory |
|---------------|----------------|--------|
| Disabled | 0% | 0MB |
| Console Exporter | +2% | +20MB |
| OTLP (async) | +5% | +50MB |
| OTLP (batch) | +3% | +50MB |

## Monitoring Dashboard

Example Grafana dashboard queries:

```promql
# Query latency percentile
histogram_quantile(0.95, rate(query_latency_bucket[5m]))

# Documents ingested per minute
rate(documents_ingested_total[5m])

# Circuit breaker state
circuit_breaker_state{service="mongodb"}
```

## Testing

```python
async def test_trace_propagation():
    """Verify trace context propagates across async boundaries."""
    with tracer.start_as_current_span("parent") as parent_span:
        parent_trace_id = parent_span.get_span_context().trace_id
        
        async def child_operation():
            with tracer.start_as_current_span("child") as child_span:
                child_trace_id = child_span.get_span_context().trace_id
                return child_trace_id
        
        # Child should inherit parent's trace ID
        child_trace_id = await child_operation()
        assert child_trace_id == parent_trace_id
```

## Alternatives Considered

### 1. Custom Observability
**Pros**: Full control, no dependencies  
**Cons**: Reinventing the wheel, no standard format

### 2. Vendor-Specific (Datadog, New Relic)
**Pros**: Turnkey solution, managed  
**Cons**: Vendor lock-in, ongoing costs, closed format

### 3. Logging Only
**Pros**: Simple, low overhead  
**Cons**: No distributed tracing, harder to debug

## References

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- ADR-003: Async Architecture
- `docs/user-guide/observability.md`
