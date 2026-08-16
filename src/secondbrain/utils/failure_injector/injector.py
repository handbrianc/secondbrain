"""The ``FailureInjector`` class composing core state with context managers."""

from secondbrain.utils.failure_injector.contexts import FailureContextMixin
from secondbrain.utils.failure_injector.types import (
    FailureConfig,
    FailureType,
    InjectedConnectionError,
    InjectedFailureError,
    InjectedTimeoutError,
)


class FailureInjector(FailureContextMixin):
    """Configurable failure injection framework for chaos testing.

    This class provides centralized failure injection with support for multiple
    failure types, configurable timing, and automatic cleanup. It is designed
    for test-only usage and should not affect production code.

    Features:
        - Multiple failure types: timeout, connection error, general failure, slow response
        - Configurable duration and delay
        - Context manager support for automatic cleanup
        - Thread-safe operation
        - Probability-based partial failures
        - Automatic cleanup on exit

    Usage:
        # Simple timeout injection
        injector = FailureInjector()
        injector.inject_timeout(duration=2.0)

        # Context manager
        with FailureInjector().inject_connection_error(duration=1.0):
            # Code that should fail
            pass

        # Async support
        async with FailureInjector().inject_timeout(duration=1.0):
            # Async code that should timeout
            pass
    """


__all__ = [
    "FailureConfig",
    "FailureInjector",
    "FailureType",
    "InjectedConnectionError",
    "InjectedFailureError",
    "InjectedTimeoutError",
]
