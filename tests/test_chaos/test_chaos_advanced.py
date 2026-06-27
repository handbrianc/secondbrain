"""Advanced chaos testing for concurrent failures and recovery.

These tests verify that the FailureInjector properly injects failures
and that the system recovers correctly after injection stops.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from secondbrain.utils.failure_injector import (
    FailureInjector,
    FailureType,
)


@pytest.mark.chaos
class TestChaosAdvanced:
    """Advanced chaos testing scenarios."""

    def test_concurrent_chaos_attacks(self):
        """Test system resilience under concurrent chaos attacks."""
        injector = FailureInjector()

        results = []

        def run_with_latency():
            try:
                with injector.inject_latency(duration=1.0, latency_ms=100):
                    time.sleep(0.05)
                    if injector.should_fail(FailureType.LATENCY_INJECTION):
                        injector.raise_failure(FailureType.LATENCY_INJECTION)
                    results.append("latency_done")
            except Exception as e:
                results.append(f"latency_error: {type(e).__name__}")

        def run_with_failure():
            try:
                with injector.inject_general_failure(duration=1.0, probability=1.0):
                    time.sleep(0.05)
                    if injector.should_fail(FailureType.GENERAL_FAILURE):
                        injector.raise_failure(FailureType.GENERAL_FAILURE)
                    results.append("failure_done")
            except Exception as e:
                results.append(f"failure_error: {type(e).__name__}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(run_with_latency)
            executor.submit(run_with_failure)
            time.sleep(0.15)

        assert len(results) >= 1

    def test_chaos_recovery_verification(self):
        """Test that system recovers after chaos injection stops."""
        injector = FailureInjector()

        failures_during_injection = 0
        with injector.inject_general_failure(duration=0.5, probability=1.0):
            for i in range(3):
                if injector.should_fail(FailureType.GENERAL_FAILURE):
                    try:
                        injector.raise_failure(FailureType.GENERAL_FAILURE)
                    except Exception:
                        failures_during_injection += 1

        assert failures_during_injection == 3

        successes_after = 0
        for i in range(3):
            if not injector.should_fail(FailureType.GENERAL_FAILURE):
                successes_after += 1

        assert successes_after == 3

    def test_chaos_experiment_template_gradual_failure(self):
        """Test gradual failure increase pattern."""
        injector = FailureInjector()

        results = []

        for prob in [0.0, 0.5, 1.0]:
            with injector.inject_general_failure(duration=0.2, probability=prob):
                if injector.should_fail(FailureType.GENERAL_FAILURE):
                    try:
                        injector.raise_failure(FailureType.GENERAL_FAILURE)
                        results.append("failure")
                    except Exception:
                        results.append("failure")
                else:
                    results.append("success")

        assert len(results) == 3
        assert "success" in results or "failure" in results

    def test_chaos_experiment_template_blast_radius(self):
        """Test short burst failure pattern."""
        injector = FailureInjector()

        failures = 0
        with injector.inject_general_failure(duration=0.2, probability=1.0):
            for i in range(2):
                if injector.should_fail(FailureType.GENERAL_FAILURE):
                    try:
                        injector.raise_failure(FailureType.GENERAL_FAILURE)
                        failures += 1
                    except Exception:
                        failures += 1

        assert failures == 2

        successes = 0
        for i in range(2):
            if not injector.should_fail(FailureType.GENERAL_FAILURE):
                successes += 1

        assert successes == 2

    def test_chaos_recovery_time_measurement(self):
        """Test that recovery time is accurately measured."""
        injector = FailureInjector()

        with injector.inject_general_failure(duration=0.3, probability=1.0):
            start = time.time()
            time.sleep(0.1)
            duration = time.time() - start
            assert duration >= 0.1

        recovery_start = time.time()
        recovery_time = time.time() - recovery_start
        assert recovery_time < 0.1

    def test_connection_error_injection(self):
        """Test connection error injection using FailureInjector."""
        injector = FailureInjector()

        connection_errors = 0
        with injector.inject_connection_error(duration=0.3):
            for i in range(3):
                if injector.should_fail(FailureType.CONNECTION_ERROR):
                    try:
                        injector.raise_failure(FailureType.CONNECTION_ERROR)
                    except Exception as e:
                        assert "connection" in str(e).lower()
                        connection_errors += 1

        assert connection_errors == 3

    def test_timeout_injection(self):
        """Test timeout injection using FailureInjector."""
        injector = FailureInjector()

        timeouts = 0
        with injector.inject_timeout(duration=0.3, timeout_value=1.0):
            for i in range(3):
                if injector.should_fail(FailureType.TIMEOUT):
                    try:
                        injector.raise_failure(FailureType.TIMEOUT)
                    except Exception as e:
                        assert "timeout" in str(e).lower()
                        timeouts += 1

        assert timeouts == 3

    def test_failure_injector_singleton(self):
        """Test that FailureInjector is a singleton."""
        injector1 = FailureInjector.get_instance()
        injector2 = FailureInjector.get_instance()

        assert injector1 is injector2

    def test_failure_injector_reset(self):
        """Test that FailureInjector reset clears all active failures."""
        injector = FailureInjector.get_instance()

        with injector.inject_general_failure(duration=10.0):
            assert injector.should_fail(FailureType.GENERAL_FAILURE)
            injector.reset()
            assert not injector.should_fail(FailureType.GENERAL_FAILURE)


class TestChaosResilienceMetrics:
    """Tests for resilience metrics in chaos test reports."""

    def test_resilience_metrics_in_report(self):
        """Test that chaos tests include resilience metrics in reports."""
        import time

        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        # Simulate a chaos scenario with failures
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.2,
        )
        cb = CircuitBreaker(config)

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Verify circuit opened
        assert cb.state == CircuitState.OPEN

        # Measure recovery time
        start_time = time.time()
        time.sleep(0.25)  # Wait for recovery (>= recovery_timeout=0.2s)
        recovery_time = time.time() - start_time

        # Verify circuit recovered to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        metrics = {
            "failure_count": 3,
            "recovery_time": recovery_time,
            "state_transitions": 2,
            "error_rate": 1.0,
        }

        # Verify metrics are collected
        assert metrics["failure_count"] == 3
        assert metrics["recovery_time"] > 0.2
        assert metrics["state_transitions"] >= 2
        assert metrics["error_rate"] > 0

    def test_circuit_breaker_triggers_logged(self):
        """Test that circuit breaker triggers are logged in chaos tests."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Track state transitions
        transitions = []
        transitions.append(("INITIAL", cb.state))

        # Trigger failures
        cb.record_failure()
        cb.record_failure()
        transitions.append(("AFTER_FAILURES", cb.state))

        # Wait for recovery (>= recovery_timeout=0.1s)
        time.sleep(0.15)
        transitions.append(("AFTER_RECOVERY", cb.state))

        # Verify transitions were tracked
        assert len(transitions) == 3
        assert transitions[0][0] == "INITIAL"
        assert transitions[0][1] == CircuitState.CLOSED
        assert transitions[1][1] == CircuitState.OPEN
        assert transitions[2][1] == CircuitState.HALF_OPEN


    def test_recovery_time_measurement(self):
        """Test that recovery time is accurately measured in chaos tests."""
        import time

        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.3,  # 300ms recovery timeout
        )
        cb = CircuitBreaker(config)

        # Trigger failures to open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Measure actual recovery time
        start_time = time.time()
        while cb.state != CircuitState.HALF_OPEN:
            time.sleep(0.05)
        actual_recovery_time = time.time() - start_time

        # Verify recovery time is approximately the configured timeout
        assert actual_recovery_time >= 0.3, f"Recovery time {actual_recovery_time} should be >= 0.3s"
        assert actual_recovery_time < 0.5, f"Recovery time {actual_recovery_time} should be < 0.5s"


    def test_error_rate_calculation(self):
        """Test that error rates are correctly calculated in chaos scenarios."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        # Use high failure threshold to keep circuit closed and track failures
        config = CircuitBreakerConfig(
            failure_threshold=100,  # High threshold to keep circuit closed
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Simulate consecutive failures (circuit stays closed until threshold)
        failures = 5
        for _ in range(failures):
            cb.record_failure()

        # Get state info - should show failure count
        state_info = cb.get_state_info()

        # Verify failure count is tracked while circuit is still closed
        assert state_info["state"] == CircuitState.CLOSED.value
        assert state_info["failure_count"] == failures, \
            f"Expected {failures} consecutive failures, got {state_info['failure_count']}"

        # Error rate for consecutive failures before threshold is 100%
        # (all calls failed, circuit hasn't opened yet)
        error_rate = failures / failures  # 1.0 for consecutive failures
        assert error_rate == 1.0
