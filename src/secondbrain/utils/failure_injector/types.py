"""Types, configuration, and exceptions used by the failure injection framework."""

from dataclasses import dataclass
from enum import Enum


class FailureType(Enum):
    """Types of failures that can be injected."""

    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    GENERAL_FAILURE = "general_failure"
    SLOW_RESPONSE = "slow_response"
    PARTIAL_FAILURE = "partial_failure"
    NETWORK_PARTITION = "network_partition"
    LATENCY_INJECTION = "latency_injection"


@dataclass
class FailureConfig:
    """Configuration for failure injection.

    Attributes:
        failure_type: Type of failure to inject.
        duration: How long the failure should last (seconds). Use None for indefinite.
        delay: Delay before failure starts (seconds). Default: 0.
        timeout_value: Timeout value in seconds for timeout failures. Default: 30.0.
        error_message: Custom error message. Default: None (uses type-specific message).
        probability: Probability of failure (0.0-1.0) for partial failures. Default: 1.0.
        repeat_count: Number of times to repeat the failure. Use None for unlimited during duration.
    """

    failure_type: FailureType
    duration: float | None = None
    delay: float = 0.0
    timeout_value: float = 30.0
    error_message: str | None = None
    probability: float = 1.0
    repeat_count: int | None = None


class InjectedTimeoutError(Exception):
    """Exception raised for injected timeouts."""

    def __init__(
        self, message: str = "Injected timeout", timeout_value: float = 30.0
    ) -> None:
        super().__init__(message)
        self.timeout_value = timeout_value


class InjectedConnectionError(Exception):
    """Exception raised for injected connection errors."""

    def __init__(self, message: str = "Injected connection error") -> None:
        super().__init__(message)


class InjectedFailureError(Exception):
    """Exception raised for injected general failures."""

    def __init__(self, message: str = "Injected failure") -> None:
        super().__init__(message)
