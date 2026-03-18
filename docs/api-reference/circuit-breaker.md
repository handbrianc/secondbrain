# Circuit Breaker Module

Circuit breaker pattern implementation for service resilience.

## Overview

The circuit breaker pattern prevents cascading failures by stopping requests to failing services and allowing periodic recovery attempts.

## Key Components

### CircuitState Enum

Circuit breaker states:
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Service failing, requests blocked  
- **HALF_OPEN**: Testing if service recovered

### CircuitBreakerError Exception

Raised when circuit breaker is open and blocking requests.

### CircuitBreaker Class

Main circuit breaker implementation with configurable:
- `failure_threshold`: Number of failures before opening circuit (default: 5)
- `recovery_timeout`: Seconds to wait before trying recovery (default: 30.0)
- `half_open_max_calls`: Max calls allowed in half-open state (default: 3)

#### Methods

- `__init__(failure_threshold, recovery_timeout, half_open_max_calls)` - Initialize circuit breaker
- `state` - Get current circuit state
- `call(func, *args, **kwargs)` - Execute function with circuit breaker protection
- `reset()` - Reset circuit breaker state
- `get_stats()` - Get circuit breaker statistics

## Example Usage

```python
from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError

cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

try:
    result = cb.call(some_function, arg1, arg2)
except CircuitBreakerError:
    print("Service unavailable, circuit is open")
```

## Related Documentation

- [API Reference](./index.md) - API documentation overview
- [Architecture](../architecture/index.md) - System design
