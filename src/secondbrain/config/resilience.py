"""Circuit-breaker resilience settings fragment for :class:`secondbrain.config.Config`.

Governs the circuit breakers wired into the connection-validation paths of the
production services (Qdrant vector storage, the embedding provider, and the
SQLite conversation storage). Enabled by default in production; the test
environment (``Config._load_env_file``) forces it off unless explicitly set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, field_validator

from secondbrain.utils.circuit_breaker import CircuitBreakerConfig

if TYPE_CHECKING:
    from secondbrain.config import Config

__all__ = ["ResilienceMixin", "circuit_breaker_config_from_config"]


class ResilienceMixin:
    """Circuit-breaker resilience settings for service connection paths."""

    circuit_breaker_enabled: bool = Field(
        default=True,
        description=(
            "Enable circuit breakers on the connection-validation paths of "
            "Qdrant storage, the embedding provider, and conversation storage "
            "(override via SECONDBRAIN_CIRCUIT_BREAKER_ENABLED env var)"
        ),
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description=(
            "Consecutive failed connection probes before a circuit opens "
            "(override via SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD env var)"
        ),
    )
    circuit_breaker_success_threshold: int = Field(
        default=2,
        description=(
            "Consecutive successful probes in half-open before a circuit "
            "closes (override via SECONDBRAIN_CIRCUIT_BREAKER_SUCCESS_THRESHOLD "
            "env var)"
        ),
    )
    circuit_breaker_recovery_timeout: float = Field(
        default=30.0,
        description=(
            "Seconds to wait before an open circuit tries half-open recovery "
            "(override via SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT env var)"
        ),
    )

    @field_validator(
        "circuit_breaker_failure_threshold", "circuit_breaker_success_threshold"
    )
    @classmethod
    def validate_circuit_breaker_thresholds(cls, v: int) -> int:
        """Validate circuit breaker thresholds are positive."""
        if v <= 0:
            raise ValueError("circuit breaker thresholds must be positive")
        return v

    @field_validator("circuit_breaker_recovery_timeout")
    @classmethod
    def validate_circuit_breaker_recovery_timeout(cls, v: float) -> float:
        """Validate circuit breaker recovery timeout is positive."""
        if v <= 0:
            raise ValueError("circuit_breaker_recovery_timeout must be positive")
        return v


def circuit_breaker_config_from_config(cfg: Config) -> CircuitBreakerConfig | None:
    """Build a :class:`CircuitBreakerConfig` from application settings.

    Mirrors the defensive ``getattr`` style of
    ``EmbeddingProviderFactory._rate_limiter_from_config`` so test stubs that
    set only the flags they exercise keep working; the fallbacks match the
    :class:`ResilienceMixin` field defaults.

    Args:
        cfg: Application configuration.

    Returns
    -------
        A :class:`CircuitBreakerConfig` when circuit breakers are enabled,
        otherwise ``None`` (services then run with the circuit breaker
        disabled).
    """
    if not getattr(cfg, "circuit_breaker_enabled", True):
        return None
    return CircuitBreakerConfig(
        failure_threshold=getattr(cfg, "circuit_breaker_failure_threshold", 5),
        success_threshold=getattr(cfg, "circuit_breaker_success_threshold", 2),
        recovery_timeout=getattr(cfg, "circuit_breaker_recovery_timeout", 30.0),
    )
