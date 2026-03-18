"""Tests for connection utilities."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.connections import (
    RateLimitedRetry,
    ServiceUnavailableError,
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
        validator = MagicMock(return_value=False)
        with pytest.raises(ServiceUnavailableError) as exc_info:
            ensure_service_available("test-service", validator)
        assert "test-service" in str(exc_info.value)
        assert "unavailable" in str(exc_info.value)


class TestRateLimitedRetry:
    """Test suite for RateLimitedRetry class."""

    def test_retry_on_failure(self) -> None:
        """Test that RateLimitedRetry exhausts retries on failure."""
        retry = RateLimitedRetry(max_retries=2, base_delay=0.01)

        call_count = 0

        def always_failing() -> bool:
            nonlocal call_count
            call_count += 1
            return False

        result = retry.call(always_failing)
        assert result is False
        assert call_count == 2

    def test_success_on_first_attempt(self) -> None:
        """Test that RateLimitedRetry doesn't retry on first success."""
        retry = RateLimitedRetry(max_retries=3, base_delay=0.01)

        result = retry.call(lambda: True)
        assert result is True

    def test_retry_with_exception(self) -> None:
        """Test that RateLimitedRetry handles exceptions."""
        retry = RateLimitedRetry(max_retries=2, base_delay=0.01)

        call_count = 0

        def failing_with_exception() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return True

        result = retry.call(failing_with_exception)
        assert result is True
        assert call_count == 2

    def test_retry_resets_after_success(self) -> None:
        """Test that RateLimitedRetry resets after success."""
        retry = RateLimitedRetry(max_retries=3, base_delay=0.01)

        call_count = 0

        def failing_then_succeeding() -> bool:
            nonlocal call_count
            call_count += 1
            return not call_count < 3

        # First sequence - succeeds on 3rd attempt
        result1 = retry.call(failing_then_succeeding)
        assert result1 is True

        # Reset and run again
        retry.reset()
        call_count = 0
        result2 = retry.call(failing_then_succeeding)
        assert result2 is True
        assert call_count == 3  # Should be able to retry again


class TestRateLimitedRetryEdgeCases:
    """Additional edge case tests for RateLimitedRetry."""

    def test_calculate_delay_with_jitter(self) -> None:
        """Test that RateLimitedRetry delay calculation includes jitter."""
        retry = RateLimitedRetry(max_retries=3, base_delay=1.0, max_delay=10.0)

        # Calculate delay for attempt 0
        delay = retry._calculate_delay(0)
        # Should be between 0.9 and 1.1 (1.0 * 0.9 to 1.0 * 1.1)
        assert 0.9 <= delay <= 1.1

        # Calculate delay for attempt 1
        delay = retry._calculate_delay(1)
        # Should be between 1.8 and 2.2 (2.0 * 0.9 to 2.0 * 1.1)
        assert 1.8 <= delay <= 2.2

    def test_can_retry_exhausted(self) -> None:
        """Test that RateLimitedRetry can_retry returns False when exhausted."""
        retry = RateLimitedRetry(max_retries=2, base_delay=0.01)

        # First call should succeed
        assert retry._can_retry() is True
        # Second call should succeed
        assert retry._can_retry() is True
        # Third call should fail (max_retries=2, so 2 retries after initial)
        assert retry._can_retry() is False

    def test_wait_before_retry_elapsed(self) -> None:
        """Test that RateLimitedRetry wait_before_retry when elapsed."""
        retry = RateLimitedRetry(max_retries=3, base_delay=0.01)

        # Set last retry time to long ago
        import time

        retry._last_retry_time = time.monotonic() - 1.0

        # Should not need to wait
        # (This tests the path where elapsed >= base_delay)
        retry._wait_before_retry()
        # If we get here without hanging, test passes


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
