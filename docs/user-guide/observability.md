# Observability Guide

This guide covers SecondBrain's observability features including structured logging, distributed tracing with OpenTelemetry, metrics collection, and OTLP export configuration.

## Quick Start

### Structured Logging

SecondBrain provides unified logging with correlation IDs for request tracing:

```python
from secondbrain.logging import get_logger, set_request_id

# Set request ID for the current context
set_request_id()  # Auto-generates UUID

# Get a logger
logger = get_logger("my_module")

# Log with automatic correlation ID
logger.info("Processing document")
```

### Enable Tracing

Enable OpenTelemetry tracing with environment variables:

```bash
export OTEL_TRACING_ENABLED=true
export OTEL_SERVICE_NAME=secondbrain
```

Then in your code:

```python
from secondbrain.utils.tracing import setup_tracing, trace_operation

# Setup once at startup
setup_tracing(service_name="secondbrain", service_version="0.1.0")

# Use trace context manager
with trace_operation("process_document"):
    # Your code here
    pass
```

## Features

### 1. Structured Logging

#### Correlation IDs

All logs include a correlation ID for tracing requests across services:

```python
from secondbrain.logging import set_request_id, get_logger

set_request_id("my-request-123")
logger = get_logger(__name__)
logger.info("Starting operation")
# Output: [my-request-123] 2024-01-01 12:00:00 INFO [my_module:42] Starting operation
```

#### JSON Format

Enable JSON structured logging:

```python
from secondbrain.logging import setup_logging

setup_logging(verbose=True, json_format=True)
```

JSON output includes:
- `timestamp`: ISO 8601 timestamp
- `level`: Log level
- `logger`: Logger name
- `message`: Log message
- `correlation_id`: Request correlation ID
- `trace_id`: OpenTelemetry trace ID (when available)
- `span_id`: OpenTelemetry span ID (when available)

### 2. OpenTelemetry Tracing

#### Span Hierarchy

SecondBrain uses a standardized span naming convention: `<category>.<component>.<action>`

**Document Ingestion:**
- `ingest.document.parse` - Document parsing
- `ingest.document.embed` - Embedding generation
- `ingest.document.store` - Vector storage

**Search:**
- `search.query.retrieval` - Query retrieval
- `search.query.rerank` - Result reranking

**RAG Pipeline:**
- `rag.pipeline.retrieve` - Context retrieval
- `rag.pipeline.generate` - Answer generation

#### Usage Examples

**Sync functions:**

```python
from secondbrain.utils.tracing import trace_operation, get_span_name

@trace_operation(get_span_name("ingest", "document.parse"))
def parse_document(path: str):
    # Document parsing logic
    pass
```

**Async functions:**

```python
from secondbrain.utils.tracing import async_trace_decorator

@async_trace_decorator(get_span_name("search", "query.retrieval"))
async def search_documents(query: str):
    # Search logic
    pass
```

**Context manager:**

```python
from secondbrain.utils.tracing import trace_operation

with trace_operation(get_span_name("rag", "pipeline.generate")) as span:
    span.set_attribute("query.length", len(query))
    answer = generate_answer(context, query)
```

### 3. Metrics Collection

#### Standard Metrics

SecondBrain defines these standard metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `document.ingested` | Counter | Number of documents ingested |
| `search.query.duration` | Histogram | Duration of search queries (seconds) |
| `embedding.cache.hit_rate` | Gauge | Embedding cache hit rate |

#### Custom Metrics

**Using OpenTelemetry metrics:**

```python
from secondbrain.utils.metrics import otel_metrics_collector

# Increment counter
otel_metrics_collector.increment_counter("document.ingested", 1)

# Record histogram
otel_metrics_collector.record_histogram("search.query.duration", 1.5)
```

**Using custom collector (fallback):**

```python
from secondbrain.utils.observability import metrics

# Record metric
metrics.record("custom.metric", 42.0)

# Increment counter
metrics.increment("custom.counter", 5)

# Set gauge
metrics.set_gauge("custom.gauge", 3.14)

# Get stats
stats = metrics.get_stats("custom.metric")
print(stats)  # {'count': 1, 'min': 42.0, 'max': 42.0, 'mean': 42.0}
```

### 4. OTLP Exporter Configuration

#### Environment Variables

Configure OTLP exporter via environment variables:

```bash
# Enable OTLP export
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Optional: Add headers for authentication
export OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer your-token

# Optional: Set timeout
export OTEL_EXPORTER_OTLP_TIMEOUT=10
```

#### Setup

```python
from secondbrain.utils.tracing import setup_tracing, setup_otlp_exporter

# Configure OTLP exporter
setup_otlp_exporter(
    endpoint="http://localhost:4317",
    headers={"authorization": "Bearer token"},
    timeout=10,
)

# Setup tracing (will use OTLP if configured)
setup_tracing(service_name="secondbrain", use_otlp=True)
```

#### Graceful Fallback

If OTLP is unavailable, SecondBrain automatically falls back to console exporter for development:

```python
from secondbrain.utils.tracing import setup_tracing

# Will use OTLP if configured, otherwise console
setup_tracing(service_name="secondbrain", use_otlp=True)
```

### 5. Async Context Propagation

Trace context automatically propagates across async boundaries:

```python
import asyncio
from secondbrain.utils.tracing import set_trace_context, async_trace_decorator

async def inner_function():
    # Trace context available here
    pass

@async_trace_decorator("outer.operation")
async def outer_function():
    # Context set automatically
    await inner_function()

# Run
asyncio.run(outer_function())
```

### 6. Log-Trace Correlation

Logs include OpenTelemetry trace IDs for end-to-end correlation:

```python
from secondbrain.logging import set_trace_context, get_logger

# Set trace context
set_trace_context(trace_id="abc123", span_id="def456")

logger = get_logger(__name__)
logger.info("Operation completed")
# JSON output includes: {"trace_id": "abc123", "span_id": "def456", ...}
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_TRACING_ENABLED` | Enable tracing | `false` |
| `OTEL_METRICS_ENABLED` | Enable metrics | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://localhost:4317` |
| `OTEL_EXPORTER_OTLP_HEADERS` | OTLP request headers | `` |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | Export timeout (seconds) | `10` |
| `OTEL_SERVICE_NAME` | Service name for traces | `secondbrain` |
| `CORRELATION_ID` | Manual correlation ID | Auto-generated |

### Settings Configuration

Add to `.env` file:

```env
# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=text  # or "json"

# OpenTelemetry
OTEL_TRACING_ENABLED=true
OTEL_METRICS_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_SERVICE_NAME=secondbrain-production
```

## Troubleshooting

### Tracing Not Working

**Problem:** No spans appear in observability platform

**Solutions:**
1. Verify `OTEL_TRACING_ENABLED=true` is set
2. Check OTLP endpoint is reachable
3. Enable debug logging to see setup errors:
   ```bash
   export SECONDBRAIN_LOG_LEVEL=DEBUG
   ```

### Metrics Not Exporting

**Problem:** Metrics not visible in monitoring system

**Solutions:**
1. Ensure `OTEL_METRICS_ENABLED=true`
2. Verify OpenTelemetry SDK is installed:
   ```bash
   pip install opentelemetry-sdk
   ```
3. Check metrics collector initialization logs

### Correlation ID Missing from Logs

**Problem:** Logs don't include correlation ID

**Solutions:**
1. Ensure `CorrelationIdFilter` is added to handlers
2. Call `set_request_id()` at request start
3. Check logging setup order (filters before handlers)

### Async Context Lost

**Problem:** Trace context not propagating in async code

**Solutions:**
1. Use `async_trace_decorator` instead of sync decorator
2. Ensure using `asyncio.to_thread()` for blocking calls
3. Verify contextvars are not being overwritten

## Best Practices

### 1. Setup Order

Always setup observability at application startup:

```python
from secondbrain.utils.tracing import setup_tracing
from secondbrain.utils.metrics import setup_metrics
from secondbrain.logging import setup_logging

def main():
    setup_logging(verbose=True)
    setup_tracing(service_name="secondbrain")
    setup_metrics(service_name="secondbrain")
    
    # Rest of application
```

### 2. Span Naming

Follow the hierarchy convention:

```python
# Good
get_span_name("ingest", "document.parse")  # "ingest.document.parse"

# Avoid
"parse_doc"  # Non-standard
```

### 3. Error Handling

Always record exceptions in spans:

```python
from secondbrain.utils.tracing import trace_operation

try:
    with trace_operation("risky_operation") as span:
        risky_operation()
except Exception as e:
    if span:
        span.set_status("ERROR")
        span.record_exception(e)
    raise
```

### 4. Metrics Collection

Use appropriate metric types:

```python
# Counter for increments (monotonically increasing)
metrics.increment("documents.processed")

# Histogram for durations
metrics.record("query.duration", 1.5)

# Gauge for current values
metrics.set_gauge("cache.size", 1024)
```

## API Reference

### Logging

- `get_logger(name)` - Get logger instance
- `set_request_id(request_id)` - Set correlation ID
- `get_request_id()` - Get current correlation ID
- `set_trace_context(trace_id, span_id)` - Set trace context
- `get_trace_context()` - Get current trace context
- `setup_logging(verbose, json_format)` - Configure logging

### Tracing

- `setup_tracing(service_name, service_version, environment)` - Setup tracing
- `setup_otlp_exporter(endpoint, headers, timeout)` - Configure OTLP
- `get_tracer()` - Get tracer instance
- `trace_operation(operation_name)` - Trace context manager
- `trace_decorator(operation_name)` - Sync function decorator
- `async_trace_decorator(operation_name)` - Async function decorator
- `get_span_name(category, action)` - Get standardized span name
- `shutdown_tracing()` - Shutdown tracing

### Metrics

- `setup_metrics(service_name)` - Setup metrics
- `is_metrics_enabled()` - Check if metrics enabled
- `OTelMetricsCollector` - OTel metrics wrapper
- `MetricsCollector` - Custom metrics collector
- `metrics` - Global metrics instance

## Examples

### Complete Observability Setup

```python
import os
from secondbrain.logging import setup_logging, set_request_id, get_logger
from secondbrain.utils.tracing import setup_tracing, trace_operation, get_span_name
from secondbrain.utils.metrics import setup_metrics, otel_metrics_collector

def process_document(document_path: str):
    # Setup
    setup_logging(verbose=True)
    setup_tracing(service_name="secondbrain")
    setup_metrics(service_name="secondbrain")
    
    # Start request
    set_request_id()
    logger = get_logger(__name__)
    
    # Trace operation
    with trace_operation(get_span_name("ingest", "document.parse")) as span:
        logger.info(f"Parsing {document_path}")
        
        # Record metrics
        otel_metrics_collector.increment_counter("document.ingested")
        
        # Process
        result = parse_document(document_path)
        
        span.set_attribute("document.size", len(result))
    
    logger.info("Document processed successfully")
```

### Async Search with Tracing

```python
import asyncio
from secondbrain.utils.tracing import async_trace_decorator, get_span_name
from secondbrain.utils.metrics import otel_metrics_collector
import time

@async_trace_decorator(get_span_name("search", "query.retrieval"))
async def search(query: str, top_k: int = 5):
    start = time.time()
    
    try:
        results = await perform_search(query, top_k)
        
        # Record duration
        duration = time.time() - start
        otel_metrics_collector.record_histogram("search.query.duration", duration)
        
        return results
    except Exception as e:
        otel_metrics_collector.increment_counter("search.errors")
        raise
```
