# ADR-006: Circuit Breaker Pattern for Resilience

**Status**: Accepted  
**Created**: 2026-03-30  
**Authors**: SecondBrain Team  
**Deciders**: Architecture Team

## Context

SecondBrain interacts with external services (MongoDB, embedding models, HTTP APIs) that may fail. The system must:

- Handle transient failures gracefully
- Prevent cascading failures when services are down
- Provide fast failures when circuit is open
- Automatically recover when services return
- Maintain availability during partial outages

## Decision

**Implement the Circuit Breaker pattern** with the following configuration:

### Circuit Breaker States

```
    ┌─────────────┐
    │   CLOSED    │ ← Normal operation, requests allowed
    │             │
    └──────┬──────┘
           │ N failures
           ▼
    ┌─────────────┐
    │    OPEN     │ ← Fail fast, no requests
    │             │
    └──────┬──────┘
           │ Timeout (60s)
           ▼
    ┌─────────────┐
    │  HALF_OPEN  │ ← Test with limited requests
    │             │
    └──────┬──────┘
     Success│ │Fail
      ┌─────┘ └─────┐
      ▼             ▼
   CLOSED        OPEN
```

### Configuration

```python
from secondbrain.utils.circuit_breaker import CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=3,        # Open after 3 consecutive failures
    recovery_timeout=60,        # Wait 60s before trying again
    half_open_max_calls=2,      # Test with 2 calls in half-open
    expected_exceptions=[
        ConnectionError,
        TimeoutError,
        pymongo.errors.ServerSelectionTimeoutError
    ]
)
```

### Implementation

```python
class MongoDBConnection(CircuitBreakerEnabledService):
    def __init__(self):
        self._circuit_breaker = CircuitBreaker(
            service_name="mongodb",
            config=CircuitBreakerConfig(...)
        )
    
    async def connect(self) -> bool:
        # Circuit breaker wraps the connection attempt
        async with self._circuit_breaker:
            return await self._do_connect()
    
    async def query(self, collection: str, query: dict):
        # Automatic fail-fast when circuit is open
        async with self._circuit_breaker:
            return await self._do_query(collection, query)
```

### Error Handling

```python
from secondbrain.utils.circuit_breaker import CircuitBreakerError

try:
    result = await db.query("documents", {"query": "test"})
except CircuitBreakerError as e:
    # Fail fast with clear error
    logger.warning(f"Circuit open: {e}")
    return {"error": "Service temporarily unavailable", "retry_after": 60}
```

## Consequences

### Positive

- **Resilience**: System survives service outages
- **Fast Failures**: Immediate rejection when circuit open
- **Auto-Recovery**: Automatic retry after timeout
- **Monitoring**: Clear visibility into service health
- **User Feedback**: Clear error messages during outages

### Negative

- **Complexity**: Additional state machine to manage
- **Configuration**: Need to tune thresholds per service
- **False Positives**: May open circuit during transient issues
- **Testing**: Need to test all circuit states

### Risks

- **Overly Aggressive**: Circuit opens too easily, reducing availability
- **Overly Lenient**: Circuit doesn't open, allowing cascading failures
- **State Inconsistency**: Circuit state may not reflect actual service health

## Performance Impact

**With Circuit Breaker** (MongoDB down):

| State | Response Time | Behavior |
|-------|---------------|----------|
| CLOSED | 50ms | Normal operation |
| OPEN | <1ms | Immediate failure |
| HALF_OPEN | 50ms | Limited requests |

**Without Circuit Breaker** (MongoDB down):

| Attempt | Response Time | Behavior |
|---------|---------------|----------|
| 1 | 30s | Timeout |
| 2 | 30s | Timeout |
| 3 | 30s | Timeout |

## Monitoring

Circuit breaker state is exposed via metrics:

```python
from secondbrain.utils.metrics import metrics

# Track circuit state
metrics.increment(f"circuit.{service_name}.state.{state.value}")

# Track failures
metrics.increment(f"circuit.{service_name}.failures")

# Track recoveries
metrics.increment(f"circuit.{service_name}.recoveries")
```

## Testing

```python
async def test_circuit_opens_after_failures():
    cb = CircuitBreaker("test", failure_threshold=3)
    
    # Simulate 3 failures
    for _ in range(3):
        try:
            async with cb:
                raise ConnectionError("Simulated failure")
        except CircuitBreakerError:
            pass
    
    # Circuit should be open
    assert cb.state == CircuitState.OPEN
    
    # Next call should fail immediately
    with pytest.raises(CircuitBreakerError):
        async with cb:
            pass
```

## Alternatives Considered

### 1. Retry Only
**Pros**: Simple, eventually succeeds  
**Cons**: No fast failure, can overwhelm failing service

### 2. Bulkhead Pattern
**Pros**: Isolates failures to specific resources  
**Cons**: Doesn't prevent cascading failures, more complex

### 3. Timeout Only
**Pros**: Simple implementation  
**Cons**: Still waits for timeout on every request

## References

- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- ADR-003: Async Architecture
- `src/secondbrain/utils/circuit_breaker.py`
