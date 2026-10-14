"""Tests for connection utilities."""

from unittest.mock import MagicMock

import pytest

from secondbrain.config import get_config
from secondbrain.conversation.storage_sqlite import ConversationStorage
from secondbrain.utils.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)
from secondbrain.utils.connections import (
    ServiceUnavailableError,
    ValidatableService,
    ensure_service_available,
)


class FakeClock:
    """Deterministic monotonic clock; tests advance it instead of sleeping."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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

    def test_validate_connection_cache_miss(self, monkeypatch) -> None:
        """Test that ValidatableService validate_connection revalidates after TTL."""
        from secondbrain.utils import connections as connections_module
        from secondbrain.utils.connections import ValidatableService

        clock = FakeClock()
        monkeypatch.setattr(connections_module, "monotonic", clock)
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

        # Advance past the cache TTL
        clock.advance(0.11)

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

    def test_on_service_recovery_resets_open_circuit_to_closed(self) -> None:
        """Test that on_service_recovery resets an OPEN circuit breaker to CLOSED.

        Circuit-breaker spec scenario "Service recovery clears circuit":
        WHEN on_service_recovery() is called THEN circuit breaker state SHALL
        reset to CLOSED.
        """

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        # A failed validation with threshold=1 opens the circuit
        assert service.validate_connection_with_circuit_breaker(force=True) is False
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

        # Simulate the service coming back online
        service.on_service_recovery()

        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.CLOSED
        assert service.circuit_breaker.failure_count == 0

    def test_on_service_recovery_clears_backoff_and_counters(self) -> None:
        """Test that on_service_recovery clears backoff and half-open counters."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=30.0,
        )
        service = ConcreteService(circuit_breaker_config=config)

        # Open the circuit and escalate backoff via a half-open failure
        assert service.validate_connection_with_circuit_breaker(force=True) is False
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

        service.circuit_breaker._backoff_multiplier = 4
        service.circuit_breaker._current_recovery_timeout = 120.0

        # Simulate the service coming back online
        service.on_service_recovery()

        state_info = service.circuit_breaker.get_state_info()
        assert state_info["state"] == "closed"
        assert state_info["failure_count"] == 0
        assert state_info["backoff_multiplier"] == 1
        assert state_info["current_recovery_timeout"] == config.recovery_timeout

    def test_on_service_recovery_is_noop_when_circuit_breaker_disabled(self) -> None:
        """Test that on_service_recovery is a no-op for the circuit when disabled."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(cache_ttl=60.0)

        assert service.is_circuit_breaker_enabled is False
        assert service.circuit_breaker is None

        # Recovery clears the connection cache without touching any circuit
        service.on_service_recovery()

        assert service.is_circuit_breaker_enabled is False
        assert service.circuit_breaker is None

        # Cache was still invalidated: next validation re-runs the validator
        service.validate_connection()
        assert service.validate_connection() is True

    def test_on_service_recovery_allows_immediate_circuit_breaker_validation(
        self,
    ) -> None:
        """Test that recovery makes the previously-failing service validate again.

        After an OPEN circuit blocked calls, on_service_recovery() must restore
        CLOSED so validate_connection_with_circuit_breaker() succeeds instead of
        raising CircuitBreakerError.
        """

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        # Open the circuit
        assert service.validate_connection_with_circuit_breaker(force=True) is False
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

        # Recovery resets to CLOSED and clears cached connection state, so a
        # subsequent validation re-runs instead of serving the failed cache
        service.on_service_recovery()

        # After recovery the service is back: flip the validator and validate
        service._do_validate = lambda: True  # type: ignore[method-assign]
        result = service.validate_connection_with_circuit_breaker(force=True)

        assert result is True
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.CLOSED

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
    async def test_validate_connection_async_cache_miss(self, monkeypatch) -> None:
        """Test that ValidatableService validate_connection_async revalidates after TTL."""
        from secondbrain.utils import connections as connections_module
        from secondbrain.utils.connections import ValidatableService

        clock = FakeClock()
        monkeypatch.setattr(connections_module, "monotonic", clock)
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

        # Advance past the cache TTL
        clock.advance(0.11)

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


class TestCircuitBreakerBypassFlag:
    """Startup-probe bypass: the breaker is neither consulted nor updated.

    ``bypass_circuit_breaker=True`` is used by startup-wait probes (e.g.
    docker_manager's Qdrant readiness loop) so transient startup failures
    cannot open the circuit and starve later polls. Successes and failures
    are both unrecorded, and the probe runs even while the circuit is OPEN.
    """

    def test_bypass_failure_is_not_recorded(self) -> None:
        """A bypassed failed probe returns False without touching the breaker."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        result = service.validate_connection_with_circuit_breaker(
            force=True, bypass_circuit_breaker=True
        )

        assert result is False
        assert service.circuit_breaker is not None
        # A recorded failure (threshold=1) would have opened the circuit.
        assert service.circuit_breaker.state is CircuitState.CLOSED
        assert service.circuit_breaker.get_failure_count() == 0

    def test_bypass_success_is_not_recorded(self) -> None:
        """A bypassed successful probe leaves the breaker state untouched."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=1,
                success_threshold=2,
            ),
        )
        breaker = service.circuit_breaker
        assert breaker is not None

        # Force HALF_OPEN (as after the recovery timeout elapses) so a
        # recorded success would be observable: it would count toward
        # closing the circuit.
        breaker.record_failure()
        breaker._state = CircuitState.HALF_OPEN

        result = service.validate_connection_with_circuit_breaker(
            force=True, bypass_circuit_breaker=True
        )

        assert result is True
        assert breaker.state is CircuitState.HALF_OPEN
        assert breaker.success_count == 0

    def test_bypass_probe_runs_while_circuit_open(self) -> None:
        """A bypassed probe runs (and returns the real result) while OPEN."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        assert service.circuit_breaker is not None
        service.circuit_breaker.record_failure()
        assert service.circuit_breaker.state is CircuitState.OPEN

        # Without bypass the OPEN circuit raises; with bypass the probe runs.
        with pytest.raises(CircuitBreakerError):
            service.validate_connection_with_circuit_breaker(force=True)

        result = service.validate_connection_with_circuit_breaker(
            force=True, bypass_circuit_breaker=True
        )

        assert result is False
        assert service.circuit_breaker.state is CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_bypass_failure_is_not_recorded_async(self) -> None:
        """Async bypass: failed probe unrecorded, breaker stays closed."""

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        result = await service.validate_connection_async_with_circuit_breaker(
            force=True, bypass_circuit_breaker=True
        )

        assert result is False
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state is CircuitState.CLOSED
        assert service.circuit_breaker.get_failure_count() == 0

    def test_base_validate_connection_accepts_bypass_flag(self) -> None:
        """The base validate_connection accepts the flag for uniform callers.

        The base validation never consults the breaker, so the probe result
        is returned and nothing is recorded either way.
        """

        class ConcreteService(ValidatableService):
            def _do_validate(self) -> bool:
                return False

            async def _do_validate_async(self) -> bool:
                return False

        service = ConcreteService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )

        assert (
            service.validate_connection(force=True, bypass_circuit_breaker=True)
            is False
        )
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state is CircuitState.CLOSED
        assert service.circuit_breaker.get_failure_count() == 0


class TestConversationStorageCircuitBreakerRouting:
    """F2: ConversationStorage.validate_connection() traverses the wired breaker.

    The circuit-breaker spec scenario "Validation calls are wrapped" requires
    that WHEN ``ValidatableService.validate_connection()`` is called THEN the
    call SHALL go through the circuit breaker AND failures SHALL be tracked.
    ConversationStorage is the one production ``ValidatableService`` subclass;
    its ``validate_connection`` (and its async twin) route through the CB
    helper so the breaker wired at construction is actually fed.
    """

    def _make_storage(self, monkeypatch, tmp_path, threshold: int):
        """Build a ConversationStorage with a config-wired enabled breaker."""
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "true")
        monkeypatch.setenv(
            "SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD", str(threshold)
        )
        get_config.cache_clear()
        return ConversationStorage(db_path=str(tmp_path / "conversations.db"))

    def test_validate_connection_skips_probe_while_circuit_open(
        self, monkeypatch, tmp_path
    ) -> None:
        """With the breaker OPEN, validate_connection degrades to False."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=1)
        probe_calls: list[int] = []

        def failing_probe() -> bool:
            probe_calls.append(1)
            return False

        storage._do_validate = failing_probe  # type: ignore[method-assign]

        # First call probes, fails, and opens the circuit (threshold=1).
        assert storage.validate_connection(force=True) is False
        assert storage.circuit_breaker is not None
        assert storage.circuit_breaker.state is CircuitState.OPEN
        assert probe_calls == [1]

        # Second call is skipped entirely: no probe, no storage access.
        assert storage.validate_connection(force=True) is False
        assert probe_calls == [1]

    def test_validate_connection_records_success_after_recovery(
        self, monkeypatch, tmp_path
    ) -> None:
        """Successes feed the breaker: recovery probe closes the circuit."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=1)
        storage._do_validate = lambda: False  # type: ignore[method-assign]

        assert storage.validate_connection(force=True) is False
        assert storage.circuit_breaker is not None
        assert storage.circuit_breaker.state is CircuitState.OPEN

        # The service comes back online: recovery resets the circuit and the
        # succeeding probe records success, closing it again.
        storage.on_service_recovery()
        storage._do_validate = lambda: True  # type: ignore[method-assign]
        assert storage.validate_connection(force=True) is True
        assert storage.circuit_breaker.state is CircuitState.CLOSED
        assert storage.circuit_breaker.get_failure_count() == 0

    def test_validate_connection_tracks_failures_in_circuit_breaker(
        self, monkeypatch, tmp_path
    ) -> None:
        """Failures are tracked per the spec: count accrues, circuit opens."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=2)
        storage._do_validate = lambda: False  # type: ignore[method-assign]
        assert storage.circuit_breaker is not None

        assert storage.validate_connection(force=True) is False
        assert storage.circuit_breaker.state is CircuitState.CLOSED
        assert storage.circuit_breaker.get_failure_count() == 1

        assert storage.validate_connection(force=True) is False
        assert storage.circuit_breaker.state is CircuitState.OPEN
        assert storage.circuit_breaker.get_failure_count() == 2

    @pytest.mark.asyncio
    async def test_validate_connection_async_routes_through_circuit_breaker(
        self, monkeypatch, tmp_path
    ) -> None:
        """The async twin feeds the same breaker and degrades to False."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=1)
        probe_calls: list[int] = []

        def failing_probe() -> bool:
            probe_calls.append(1)
            return False

        storage._do_validate = failing_probe  # type: ignore[method-assign]

        assert await storage.validate_connection_async(force=True) is False
        assert storage.circuit_breaker is not None
        assert storage.circuit_breaker.state is CircuitState.OPEN

        # OPEN circuit: the async twin also skips the probe.
        assert await storage.validate_connection_async(force=True) is False
        assert probe_calls == [1]

    def test_bypass_leaves_circuit_breaker_untouched(
        self, monkeypatch, tmp_path
    ) -> None:
        """Bypassed probes (startup-wait) record neither failure nor success."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=1)
        storage._do_validate = lambda: False  # type: ignore[method-assign]
        breaker = storage.circuit_breaker
        assert breaker is not None

        # Bypassed failure: unrecorded (a recorded failure would open it).
        assert (
            storage.validate_connection(force=True, bypass_circuit_breaker=True)
            is False
        )
        assert breaker.state is CircuitState.CLOSED
        assert breaker.get_failure_count() == 0

        # Bypassed success: also unrecorded — observable in HALF_OPEN, where
        # a recorded success would count toward closing the circuit.
        breaker.record_failure()
        breaker._state = CircuitState.HALF_OPEN
        storage._do_validate = lambda: True  # type: ignore[method-assign]
        assert (
            storage.validate_connection(force=True, bypass_circuit_breaker=True) is True
        )
        assert breaker.state is CircuitState.HALF_OPEN
        assert breaker.success_count == 0

    def test_non_bypass_path_still_feeds_circuit_breaker(
        self, monkeypatch, tmp_path
    ) -> None:
        """Post-startup validation (no bypass) still records failures."""
        storage = self._make_storage(monkeypatch, tmp_path, threshold=1)
        storage._do_validate = lambda: False  # type: ignore[method-assign]

        # Bypassed polls (startup probes) leave the breaker closed...
        assert (
            storage.validate_connection(force=True, bypass_circuit_breaker=True)
            is False
        )
        assert storage.circuit_breaker is not None
        assert storage.circuit_breaker.state is CircuitState.CLOSED

        # ...while the post-startup path (no bypass) still records failures.
        assert storage.validate_connection(force=True) is False
        assert storage.circuit_breaker.state is CircuitState.OPEN

    def test_validate_connection_unchanged_when_breaker_disabled(
        self, monkeypatch, tmp_path
    ) -> None:
        """With the breaker disabled (None), validation stays a plain probe."""
        monkeypatch.setenv("SECONDBRAIN_CIRCUIT_BREAKER_ENABLED", "false")
        get_config.cache_clear()
        storage = ConversationStorage(db_path=str(tmp_path / "conversations.db"))

        assert storage.circuit_breaker is None
        assert storage.validate_connection(force=True) is True
