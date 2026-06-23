"""Tests for connection utilities."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.utils.connections import (
    ServiceUnavailableError,
    ValidatableService,
    ensure_service_available,
)


class TestServiceUnavailableError:
    """Test suite for ServiceUnavailableError exception."""

    def test_exception_default_message(self) -> None:
        """Test that ServiceUnavailableError has default message."""
        error = ServiceUnavailableError("test-service")
        assert str(error) == "test-service is unavailable"

    def test_exception_custom_message(self) -> None:
        """Test that ServiceUnavailableError accepts custom message."""
        error = ServiceUnavailableError("test-service", "Custom error text")
        assert str(error) == "Custom error text"

    def test_exception_service_name_attribute(self) -> None:
        """Test that ServiceUnavailableError has service_name attribute."""
        error = ServiceUnavailableError("my-service")
        assert error.service_name == "my-service"


class TestEnsureServiceAvailable:
    """Test suite for ensure_service_available function."""

    def test_service_available(self) -> None:
        """Test that ensure_service_available succeeds when service is available."""
        validator = MagicMock(return_value=True)
        ensure_service_available("test-service", validator)
        validator.assert_called_once()

    def test_service_unavailable_raises(self) -> None:
        """Test that ensure_service_available raises when service is unavailable."""
        # Create fresh mock per test to avoid xdist worker pollution
        validator = MagicMock(return_value=False)
        validator.side_effect = None  # Clear any residual side-effects from prior tests
        with pytest.raises(ServiceUnavailableError) as exc_info:
            ensure_service_available("test-service", validator)
        assert "test-service" in str(exc_info.value)
        assert "unavailable" in str(exc_info.value)
        # Explicitly reset mock to prevent leakage
        validator.reset_mock()


class TestValidatableService:
    """Tests for ValidatableService base class."""

    def test_validate_connection_cache_hit(self) -> None:
        """Test that ValidatableService validate_connection uses cache."""

        class TestService:
            pass

        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # First call validates
        result1 = service.validate_connection()
        assert result1 is True

        # Second call should use cache
        result2 = service.validate_connection()
        assert result2 is True

    def test_validate_connection_cache_miss(self) -> None:
        """Test that ValidatableService validate_connection revalidates after TTL."""
        from secondbrain.utils.connections import ValidatableService

        call_count = 0

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                nonlocal call_count
                call_count += 1
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=0.1)

        # First call validates
        result1 = service.validate_connection()
        assert result1 is True
        assert call_count == 1

        # Wait for cache to expire
        time.sleep(0.11)

        # Second call should revalidate
        result2 = service.validate_connection()
        assert result2 is True
        assert call_count == 2

    def test_validate_connection_exception_handling(self) -> None:
        """Test that ValidatableService validate_connection handles exceptions."""
        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                raise Exception("Validation failed")

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # Should return False on exception
        result = service.validate_connection()
        assert result is False

    def test_invalidate_connection_cache(self) -> None:
        """Test that ValidatableService invalidate_connection_cache clears cache."""
        from secondbrain.utils.connections import ValidatableService

        call_count = 0

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                nonlocal call_count
                call_count += 1
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # First call validates
        service.validate_connection()
        assert call_count == 1

        # Invalidate cache
        service.invalidate_connection_cache()

        # Second call should revalidate
        service.validate_connection()
        assert call_count == 2

    def test_on_service_recovery(self) -> None:
        """Test that ValidatableService on_service_recovery clears cache."""
        from secondbrain.utils.connections import ValidatableService

        call_count = 0

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                nonlocal call_count
                call_count += 1
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # First call validates
        service.validate_connection()
        assert call_count == 1

        # Simulate recovery
        service.on_service_recovery()

        # Second call should revalidate
        service.validate_connection()
        assert call_count == 2

    def test_circuit_breaker_failure_recording(self) -> None:
        """Test that validation failure is recorded in circuit breaker."""
        import asyncio

        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitState,
        )

        class TestService(ValidatableService):
            def _do_validate_connection(self) -> bool:
                return False

        # Use failure_threshold=1 so single failure opens circuit
        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        # Use async version WITH circuit breaker which records state
        result = asyncio.run(
            service.validate_connection_async_with_circuit_breaker(force=True)
        )
        assert result is False
        assert service.circuit_breaker is not None
        # After one failure with threshold=1, circuit should be OPEN
        assert service.circuit_breaker.state == CircuitState.OPEN


class TestValidatableServiceAsync:
    """Async tests for ValidatableService."""

    @pytest.mark.asyncio
    async def test_validate_connection_async_cache_hit(self) -> None:
        """Test that ValidatableService validate_connection_async uses cache."""
        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # First call validates
        result1 = await service.validate_connection_async()
        assert result1 is True

        # Second call should use cache
        result2 = await service.validate_connection_async()
        assert result2 is True

    @pytest.mark.asyncio
    async def test_validate_connection_async_cache_miss(self) -> None:
        """Test that ValidatableService validate_connection_async revalidates after TTL."""
        from secondbrain.utils.connections import ValidatableService

        call_count = 0

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                nonlocal call_count
                call_count += 1
                return True

        service = ConcreteService(cache_ttl=0.1)

        # First call validates
        result1 = await service.validate_connection_async()
        assert result1 is True
        assert call_count == 1

        # Wait for cache to expire
        await asyncio.sleep(0.11)

        # Second call should revalidate
        result2 = await service.validate_connection_async()
        assert result2 is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_validate_connection_async_exception_handling(self) -> None:
        """Test that ValidatableService validate_connection_async handles exceptions."""
        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                raise Exception("Async validation failed")

        service = ConcreteService(cache_ttl=60.0)

        # Should return False on exception
        result = await service.validate_connection_async()
        assert result is False

    @pytest.mark.asyncio
    async def test_do_validate_async_default_implementation(self) -> None:
        """Test that ValidatableService _do_validate_async default implementation."""
        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # Default async implementation should work
        result = await service._do_validate_async()
        assert result is True



