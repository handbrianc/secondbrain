"""Tests for connection utilities."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.connections import (
    RateLimitedRetry,
    ServiceUnavailableError,
    ServiceValidator,
    ensure_service_available,
)


class TestServiceUnavailableError:
    def test_exception_default_message(self) -> None:
        error = ServiceUnavailableError("test-service")
        assert str(error) == "test-service is unavailable"

    def test_exception_custom_message(self) -> None:
        error = ServiceUnavailableError("test-service", "Custom error text")
        assert str(error) == "Custom error text"

    def test_exception_service_name_attribute(self) -> None:
        error = ServiceUnavailableError("my-service")
        assert error.service_name == "my-service"


class TestEnsureServiceAvailable:
    def test_service_available(self) -> None:
        validator = MagicMock(return_value=True)
        ensure_service_available("test-service", validator)
        validator.assert_called_once()

    def test_service_unavailable_raises(self) -> None:
        validator = MagicMock(return_value=False)
        with pytest.raises(ServiceUnavailableError) as exc_info:
            ensure_service_available("test-service", validator)
        assert "test-service" in str(exc_info.value)
        assert "unavailable" in str(exc_info.value)


class TestServiceValidator:
    def test_validator_not_configured(self) -> None:
        validator = ServiceValidator()
        with pytest.raises(RuntimeError, match="Validator not configured"):
            validator.is_available()

    def test_validator_configured_and_available(self) -> None:
        validator = ServiceValidator()
        validator.configure(lambda: True)
        result = validator.is_available()
        assert result is True

    def test_validator_configured_and_unavailable(self) -> None:
        validator = ServiceValidator()
        validator.configure(lambda: False)
        result = validator.is_available()
        assert result is False

    def test_validator_caching(self) -> None:
        validator = ServiceValidator(cache_ttl=60.0)
        call_count = 0

        def incrementing_validator() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        validator.configure(incrementing_validator)
        validator.is_available()
        validator.is_available()
        validator.is_available()
        assert call_count == 1

    def test_validator_force_check(self) -> None:
        validator = ServiceValidator(cache_ttl=60.0)
        call_count = 0

        def incrementing_validator() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        validator.configure(incrementing_validator)
        validator.is_available()
        validator.is_available()
        validator.is_available(force=True)
        assert call_count == 2

    def test_validator_cache_expiration(self) -> None:
        validator = ServiceValidator(cache_ttl=0.1)
        call_count = 0

        def incrementing_validator() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        validator.configure(incrementing_validator)
        validator.is_available()
        time.sleep(0.11)  # Wait for cache to expire (TTL = 0.1s)
        validator.is_available()
        assert call_count == 2

    def test_validator_invalidate(self) -> None:
        validator = ServiceValidator(cache_ttl=60.0)
        call_count = 0

        def incrementing_validator() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        validator.configure(incrementing_validator)
        validator.is_available()
        validator.is_available()
        validator.invalidate()
        validator.is_available()
        assert call_count == 2

    def test_validator_on_recovery(self) -> None:
        validator = ServiceValidator(cache_ttl=60.0)
        call_count = 0
        is_available = True

        def validator_func() -> bool:
            nonlocal call_count, is_available
            call_count += 1
            return is_available

        validator.configure(validator_func)
        validator.is_available()
        validator.is_available()
        is_available = False
        validator.on_recovery()
        result = validator.is_available()
        assert call_count == 2
        assert result is False


class TestServiceValidatorEdgeCases:
    """Additional edge case tests for ServiceValidator."""

    def test_validator_multiple_configures(self) -> None:
        """Test configuring validator multiple times."""
        validator = ServiceValidator()
        validator.configure(lambda: True)
        assert validator.is_available() is True

        validator.configure(lambda: False)
        # Should invalidate cache on configure
        assert validator.is_available() is False

    def test_validator_cache_ttl_zero(self) -> None:
        """Test validator with zero TTL always revalidates."""
        validator = ServiceValidator(cache_ttl=0.0)
        call_count = 0

        def incrementing_validator() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        validator.configure(incrementing_validator)
        validator.is_available()
        validator.is_available()
        validator.is_available()
        # With TTL of 0, should always revalidate
        assert call_count == 3

    def test_validator_validator_callable_changes(self) -> None:
        """Test validator behavior when validator function state changes."""
        validator = ServiceValidator()
        status = [True]

        def status_validator() -> bool:
            return status[0]

        validator.configure(status_validator)
        assert validator.is_available() is True

        status[0] = False
        # Without calling on_recovery, should still return cached True
        assert validator.is_available() is True

        validator.on_recovery()
        assert validator.is_available() is False


class TestRateLimitedRetry:
    def test_retry_on_failure(self) -> None:
        """Test all retries exhausted returns False."""
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
        """Test no retries when first attempt succeeds."""
        retry = RateLimitedRetry(max_retries=3, base_delay=0.01)

        result = retry.call(lambda: True)
        assert result is True

    def test_retry_with_exception(self) -> None:
        """Test retry handles exceptions."""
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
        """Test retry counter resets after a successful call."""
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
        """Test delay calculation includes jitter."""
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
        """Test that can_retry returns False when retries exhausted."""
        retry = RateLimitedRetry(max_retries=2, base_delay=0.01)

        # First call should succeed
        assert retry._can_retry() is True
        # Second call should succeed
        assert retry._can_retry() is True
        # Third call should fail (max_retries=2, so 2 retries after initial)
        assert retry._can_retry() is False

    def test_wait_before_retry_elapsed(self) -> None:
        """Test wait_before_retry when enough time has elapsed."""
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
        """Test that validate_connection uses cache."""

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
        """Test that validate_connection revalidates after TTL expires."""
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
        """Test that validate_connection handles exceptions gracefully."""
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
        """Test that invalidate_connection_cache clears the cache."""
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
        """Test that on_service_recovery clears the cache."""
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
        """Test that validate_connection_async uses cache."""
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
        """Test that validate_connection_async revalidates after TTL expires."""
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
        """Test that validate_connection_async handles exceptions gracefully."""
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
        """Test that _do_validate_async default calls _do_validate in thread."""
        from secondbrain.utils.connections import ValidatableService

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        # Default async implementation should work
        result = await service._do_validate_async()
        assert result is True
