"""Tests for connections module coverage gaps.

This module provides targeted tests to cover remaining uncovered lines
in the connections utility module.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.utils.circuit_breaker import CircuitBreakerConfig, CircuitBreakerError
from secondbrain.utils.connections import RateLimitedRetry, ValidatableService


class TestRateLimitedRetryEdgeCases:
    """Tests for RateLimitedRetry edge cases."""

    def test_rate_limited_retry_no_retry_on_success(self) -> None:
        """Test RateLimitedRetry doesn't retry on immediate success (line 130)."""
        retry = RateLimitedRetry(max_retries=3, base_delay=0.01)
        call_count = 0

        def succeeds_immediately() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        result = retry.call(succeeds_immediately)

        assert result is True
        assert call_count == 1  # No retries


class TestValidatableServiceWithCircuitBreaker:
    """Tests for ValidatableService with circuit breaker."""

    def test_validatable_service_init_with_cb(self) -> None:
        """Test ValidatableService initialization with circuit breaker (line 194)."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

        assert service._circuit_breaker is not None
        assert service._circuit_breaker_enabled is True

    def test_validatable_service_circuit_breaker_property(self) -> None:
        """Test ValidatableService circuit_breaker property (line 202)."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

        cb = service.circuit_breaker
        assert cb is not None

    def test_validatable_service_is_cb_enabled_property(self) -> None:
        """Test ValidatableService is_circuit_breaker_enabled property (line 207)."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

        assert service.is_circuit_breaker_enabled is True

        # Test without CB
        service_no_cb = TestService(cache_ttl=60.0)
        assert service_no_cb.is_circuit_breaker_enabled is False


class TestValidateConnectionWithCircuitBreaker:
    """Tests for validate_connection_with_circuit_breaker."""

    def test_validate_connection_with_cb_open(self) -> None:
        """Test validate_connection_with_circuit_breaker when CB open (lines 257-279)."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError) as exc_info:
            service.validate_connection_with_circuit_breaker()

        assert "Circuit breaker is open" in str(exc_info.value)

    def test_validate_connection_with_cb_closed_success(self) -> None:
        """Test validate_connection_with_circuit_breaker success path."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

        result = service.validate_connection_with_circuit_breaker()

        assert result is True

    def test_validate_connection_with_cb_closed_failure(self) -> None:
        """Test validate_connection_with_circuit_breaker failure path."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return False  # Always fail

            async def _do_validate_async(self) -> bool:
                return False

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        result = service.validate_connection_with_circuit_breaker()

        assert result is False


class TestAsyncValidationWithCircuitBreaker:
    """Tests for async validation with circuit breaker."""

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_open(self) -> None:
        """Test async validation with CB open (lines 351-373)."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError):
            await service.validate_connection_async_with_circuit_breaker()

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_closed(self) -> None:
        """Test async validation with CB closed."""

        class TestService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService(
            cache_ttl=60.0,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

        result = await service.validate_connection_async_with_circuit_breaker()

        assert result is True
