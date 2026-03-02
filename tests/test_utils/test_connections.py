"""Tests for connection utilities."""

import time
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.connections import (
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
        time.sleep(0.15)
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
