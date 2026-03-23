"""Tests for circuit breaker coverage gaps.

This module provides targeted tests to cover remaining uncovered lines
in the circuit breaker utility module.
"""

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerEnabledService,
    CircuitBreakerError,
    CircuitState,
)
from secondbrain.utils.connections import ValidatableService


class TestCircuitBreakerEdgeCases:
    """Tests for CircuitBreaker edge cases."""

    def test_call_returns_false(self) -> None:
        """Test call() when function returns False (line 265)."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        result = cb.call(lambda: False)

        assert result is False
        # Should record failure and open circuit
        assert cb.state == CircuitState.OPEN

    def test_call_raises_exception(self) -> None:
        """Test call() when function raises exception (lines 267-275)."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        def failing_func() -> bool:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            cb.call(failing_func)

        # Should record failure
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerEnabledService:
    """Tests for CircuitBreakerEnabledService."""

    def test_circuit_breaker_enabled_service_init(self) -> None:
        """Test CircuitBreakerEnabledService initialization (lines 338-342)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()

        assert service._circuit_breaker is not None
        assert service._circuit_breaker_enabled is True

    def test_circuit_breaker_property(self) -> None:
        """Test circuit_breaker property getter (line 350)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()
        cb = service.circuit_breaker

        assert cb is not None
        assert cb.service_name == "test-service"

    def test_is_circuit_breaker_enabled_property(self) -> None:
        """Test is_circuit_breaker_enabled property (line 355)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()

        assert service.is_circuit_breaker_enabled is True


class TestValidateConnectionWithCircuitBreaker:
    """Tests for validate_connection_with_circuit_breaker."""

    def test_validate_connection_with_cb_open(self) -> None:
        """Test validate_connection_with_circuit_breaker when CB is open (lines 369-391)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService()

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError) as exc_info:
            service.validate_connection_with_circuit_breaker()

        assert "Circuit breaker is open" in str(exc_info.value)

    def test_validate_connection_with_cb_closed(self) -> None:
        """Test validate_connection_with_circuit_breaker when CB is closed."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService()

        result = service.validate_connection_with_circuit_breaker()

        assert result is True
        # Should record success
        cb = service.circuit_breaker
        assert cb is not None
        assert cb.state == CircuitState.CLOSED


class TestAsyncValidationWithCircuitBreaker:
    """Tests for async validation with circuit breaker (lines 407-429)."""

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_open(self) -> None:
        """Test async validation when CB is open."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

            async def validate_connection_async(self, force: bool = False) -> bool:
                return True

        service = TestService()

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError):
            await service.validate_connection_async_with_circuit_breaker()

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_closed(self) -> None:
        """Test async validation when CB is closed."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

            async def validate_connection_async(self, force: bool = False) -> bool:
                return True

        service = TestService()

        result = await service.validate_connection_async_with_circuit_breaker()

        assert result is True
        cb = service.circuit_breaker
        assert cb is not None
        assert cb.state == CircuitState.CLOSED
