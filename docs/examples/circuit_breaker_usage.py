"""
Circuit Breaker Usage Example.

This example demonstrates how the circuit breaker pattern protects against
service failures in SecondBrain.

The circuit breaker automatically:
1. Opens after consecutive failures (default: 5)
2. Blocks requests during open state (prevents cascade failures)
3. Transitions to half-open after recovery timeout (default: 30s)
4. Closes after successful recovery attempts (default: 2 successes)
"""

import time

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)


def demonstrate_circuit_breaker() -> None:
    """Demonstrate circuit breaker state transitions."""
    # Create circuit breaker with custom config for demonstration
    config = CircuitBreakerConfig(
        failure_threshold=3,  # Open after 3 failures
        success_threshold=2,  # Close after 2 successes in half-open
        recovery_timeout=2.0,  # 2 seconds before half-open (short for demo)
        half_open_max_calls=5,  # Max calls allowed in half-open state
    )

    cb = CircuitBreaker(config)

    print("=" * 60)
    print("Circuit Breaker Demonstration")
    print("=" * 60)
    print()

    # Phase 1: Normal operation (CLOSED state)
    print("Phase 1: Normal Operation (CLOSED state)")
    print("-" * 40)
    print(f"Initial state: {cb.state.value}")
    print(f"Is allowed: {cb.is_allowed()}")

    # Simulate successful operations
    for i in range(3):
        cb.record_success()
        print(f"  Operation {i + 1}: success → state: {cb.state.value}")

    print()

    # Phase 2: Service degradation (transitions to OPEN)
    print("Phase 2: Service Degradation (→ OPEN state)")
    print("-" * 40)

    # Simulate failures
    for i in range(3):
        cb.record_failure()
        print(f"  Failure {i + 1}: recorded → state: {cb.state.value}")

    print(f"\nIs allowed: {cb.is_allowed()} (requests blocked!)")
    print()

    # Phase 3: Recovery timeout (transitions to HALF_OPEN)
    print("Phase 3: Recovery Timeout (→ HALF_OPEN state)")
    print("-" * 40)
    print(f"Waiting {config.recovery_timeout}s for recovery timeout...")
    time.sleep(config.recovery_timeout + 0.1)

    # Check if allowed (should transition to half-open)
    is_allowed = cb.is_allowed()
    print(f"After timeout: is_allowed={is_allowed}, state={cb.state.value}")
    print()

    # Phase 4: Recovery attempts (transitions to CLOSED)
    print("Phase 4: Recovery Attempts (→ CLOSED state)")
    print("-" * 40)

    # Simulate successful recovery
    for i in range(2):
        cb.record_success()
        print(f"  Recovery attempt {i + 1}: success → state: {cb.state.value}")

    print()
    print("=" * 60)
    print("Circuit breaker recovered to CLOSED state!")
    print("=" * 60)


def demonstrate_error_handling() -> None:
    """Demonstrate error handling with circuit breaker."""
    print("\n" + "=" * 60)
    print("Error Handling with Circuit Breaker")
    print("=" * 60)
    print()

    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.5))

    # Open the circuit
    print("Opening circuit with failures...")
    for _ in range(2):
        cb.record_failure()

    print(f"Circuit state: {cb.state.value}")
    print()

    # Try to make request when circuit is open
    print("Attempting request when circuit is open...")
    try:
        if not cb.is_allowed():
            raise CircuitBreakerError("MongoDB service unavailable", "mongo")
    except CircuitBreakerError as e:
        print(f"✓ Caught CircuitBreakerError: {e.message}")
        print(f"  Service: {e.service_name}")
        print()
        print("Action: Cache request, retry later, or return cached response")

    print()
    print("=" * 60)


def demonstrate_production_usage() -> None:
    """Demonstrate production usage patterns."""
    print("\n" + "=" * 60)
    print("Production Usage Patterns")
    print("=" * 60)
    print()

    # Pattern 1: Wrapper function with circuit breaker
    print("Pattern 1: Wrapper function with circuit breaker")
    print("-" * 40)
    print("""
def safe_mongo_operation(operation_func, *args, **kwargs):
    \"\"\"Execute MongoDB operation with circuit breaker protection.\"\"\"
    cb = CircuitBreaker()  # Or get from storage instance

    if not cb.is_allowed():
        raise CircuitBreakerError("MongoDB circuit open", "mongo")

    try:
        result = operation_func(*args, **kwargs)
        cb.record_success()
        return result
    except Exception as e:
        cb.record_failure()
        raise
    """)

    # Pattern 2: Fallback strategy
    print("\nPattern 2: Fallback strategy when circuit is open")
    print("-" * 40)
    print("""
def search_with_fallback(query_embedding, top_k=5):
    \"\"\"Search with fallback to cached results.\"\"\"
    try:
        if not storage._circuit_breaker.is_allowed():
            # Circuit is open, use cached results
            return get_cached_search_results(query_embedding)

        return storage.search(query_embedding, top_k)
    except CircuitBreakerError:
        # Fallback to cached or empty results
        return []
    """)

    # Pattern 3: Health check integration
    print("\nPattern 3: Health check integration")
    print("-" * 40)
    print("""
def health_check():
    \"\"\"Check service health including circuit breaker state.\"\"\"
    health = {
        "mongo": {
            "status": "healthy" if storage._circuit_breaker.state == CircuitState.CLOSED
                     else "degraded",
            "circuit_state": storage._circuit_breaker.state.value
        }
    }
    return health
    """)

    print()
    print("=" * 60)


def main() -> None:
    """Run all demonstrations."""
    demonstrate_circuit_breaker()
    demonstrate_error_handling()
    demonstrate_production_usage()

    print("\n" + "=" * 60)
    print("Key Takeaways")
    print("=" * 60)
    print("""
1. Circuit breaker prevents cascade failures during service outages
2. Automatic recovery reduces operational overhead
3. Configure thresholds based on your service reliability requirements
4. Always implement fallback strategies for open circuit state
5. Monitor circuit breaker metrics in production

For more information, see:
- docs/migration.md (circuit breaker configuration)
- docs/getting-started/troubleshooting.md (circuit breaker issues)
- tests/test_chaos/ (chaos testing examples)
    """)


if __name__ == "__main__":
    main()
