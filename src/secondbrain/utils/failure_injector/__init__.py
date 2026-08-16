"""Configurable failure injection framework for chaos testing.

This package provides a centralized, configurable failure injection mechanism
for chaos engineering tests. It supports multiple failure types with configurable
timing and duration, ensuring clean test isolation and automatic cleanup.

Usage:
    # Context manager usage
    with FailureInjector().inject_timeout(delay=1.0):
        # Code that should experience timeout
        pass

    # Manual usage
    injector = FailureInjector()
    injector.inject_connection_error(duration=2.0)
    try:
        # Code that should experience connection error
        pass
    finally:
        injector.reset()
"""

from secondbrain.utils.failure_injector.api import (
    failure_injector,
    inject_connection_error,
    inject_general_failure,
    inject_latency,
    inject_network_partition,
    inject_timeout,
)
from secondbrain.utils.failure_injector.injector import (
    FailureConfig,
    FailureInjector,
    FailureType,
    InjectedConnectionError,
    InjectedFailureError,
    InjectedTimeoutError,
)

__all__ = [
    "FailureConfig",
    "FailureInjector",
    "FailureType",
    "InjectedConnectionError",
    "InjectedFailureError",
    "InjectedTimeoutError",
    "failure_injector",
    "inject_connection_error",
    "inject_general_failure",
    "inject_latency",
    "inject_network_partition",
    "inject_timeout",
]
