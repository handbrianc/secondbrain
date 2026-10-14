"""Utility modules for SecondBrain."""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)
from .embedding_cache import EmbeddingCache
from .tracing import get_tracer, is_tracing_enabled, setup_tracing, trace_operation
from .tracing import shutdown_tracing as shutdown_tracing

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitState",
    "EmbeddingCache",
    "get_tracer",
    "is_tracing_enabled",
    "setup_tracing",
    "shutdown_tracing",
    "trace_operation",
]
