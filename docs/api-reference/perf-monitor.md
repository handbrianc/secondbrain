# Performance Monitor Module

Performance monitoring utilities and decorators for tracking operation performance.

## Overview

The performance monitor provides thread-safe metrics collection and timing decorators to track operation performance across the application.

## Key Components

### PerfMetrics Class

Thread-safe performance metrics collector that:
- Records duration measurements for named operations
- Provides statistical summaries (count, total, avg, min, max)
- Supports resetting individual or all metrics

#### Methods

- `__init__()` - Initialize metrics collector
- `record(name, duration)` - Record a duration for a metric
- `get_stats(name)` - Get statistics for a metric (returns dict or None)
- `reset(name)` - Reset metrics for a name or all metrics

### Global Metrics Instance

A global `metrics` instance is available for direct use:

```python
from secondbrain.utils.perf_monitor import metrics

metrics.record("query", 0.045)
stats = metrics.get_stats("query")
print(f"Average: {stats['avg_seconds']:.3f}s")
```

### Timing Decorators

#### @timing(metric_name)

Synchronous decorator to track function execution time:

```python
from secondbrain.utils.perf_monitor import timing

@timing("query_duration")
def search(query):
    return perform_search(query)
```

#### @async_timing(metric_name)

Async decorator for async functions:

```python
@async_timing("async_query_duration")
async def async_search(query):
    return await perform_search(query)
```

## Related Documentation

- [API Reference](./index.md) - API documentation overview
- [Performance Optimization](../developer-guide/development.md#performance-optimization) - Tuning guide
