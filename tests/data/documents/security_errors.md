# Security and Error Handling

## Security Features

### Circuit Breaker Pattern
The circuit breaker protects against cascade failures:

```python
from secondbrain.utils.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=ConnectionError
)

@breaker.call
def risky_operation():
    return connect_to_service()
```

### Rate Limiting
Rate limiting protects downstream services:

```python
from secondbrain.utils.rate_limiter import RateLimiter

limiter = RateLimiter(
    rate=10,  # requests per second
    burst=20  # burst capacity
)

if limiter.acquire():
    make_request()
```

### Security Filter
The security filter validates user input:

```python
from secondbrain.rag.security_filter import SecurityFilter

filter = SecurityFilter()
violations = filter.validate_query(user_query)

if violations:
    raise SecurityError("Query contains injection patterns")
```

## Error Types

### StorageConnectionError
Raised when MongoDB connection fails:

```python
from secondbrain.exceptions import StorageConnectionError

try:
    storage.query_vectors(...)
except StorageConnectionError as e:
    logger.error(f"Database unavailable: {e}")
```

### ValidationError
Raised for invalid input:

```python
from secondbrain.exceptions import ValidationError

try:
    validate_query(query)
except ValidationError as e:
    return {"error": str(e)}
```

### CircuitBreakerOpenError
Raised when circuit breaker is open:

```python
from secondbrain.exceptions import CircuitBreakerOpenError

try:
    result = breaker.call(operation)
except CircuitBreakerOpenError:
    return {"error": "Service temporarily unavailable"}
```

### RateLimitExceededError
Raised when rate limit is exceeded:

```python
from secondbrain.exceptions import RateLimitExceededError

try:
    result = limiter.execute(operation)
except RateLimitExceededError:
    return {"error": "Rate limit exceeded, please retry later"}
```

## Error Handling Best Practices

### 1. Fail Fast
Validate inputs early and raise specific exceptions:

```python
def process_query(query: str) -> dict:
    if not query:
        raise ValidationError("Query cannot be empty")
    
    if len(query) > 10000:
        raise ValidationError("Query too long")
    
    # Process query
```

### 2. Provide Context
Include helpful error messages:

```python
raise StorageConnectionError(
    f"Cannot connect to MongoDB at {uri}. "
    f"Database: {db}, Collection: {collection}. "
    f"Operation: {operation}."
)
```

### 3. Use Specific Exceptions
Avoid generic Exception:

```python
# Good
except FileNotFoundError:
    logger.warning("File not found")
except PermissionError:
    logger.error("Permission denied")

# Avoid
except Exception:
    logger.error("Something went wrong")
```

### 4. Implement Retry Logic
For transient failures:

```python
from secondbrain.utils.connections import ValidatableService

class MyService(ValidatableService):
    def __init__(self):
        super().__init__(cache_ttl=300)
    
    def execute(self):
        if not self.validate_connection():
            raise StorageConnectionError("Service unavailable")
        # Execute operation
```

### 5. Circuit Breaker Recovery
Automatic recovery from failures:

```python
# Circuit breaker automatically attempts recovery
# after reset_timeout seconds
breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60
)

# After 5 failures, circuit opens
# After 60 seconds, half-open state
# Successful call closes circuit
```

## Monitoring and Observability

### Structured Logging
```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Query processed",
    extra={
        "query_length": len(query),
        "results_count": len(results),
        "processing_time_ms": elapsed_ms
    }
)
```

### OpenTelemetry Tracing
```python
from secondbrain.utils.tracing import trace_operation

@trace_operation("query_processing")
def process_query(query):
    # Processing logic
    return results
```

### Health Checks
```python
from secondbrain.utils.connections import ValidatableService

class MyService(ValidatableService):
    def health_check(self) -> dict:
        return {
            "status": "healthy" if self.validate_connection() else "unhealthy",
            "service": self.__class__.__name__
        }
```
