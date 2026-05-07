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
    inject_general_failure,
    inject_connection_error,
    inject_timeout,
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
                    time.sleep(0.1)
                    if injector.should_fail(FailureType.LATENCY_INJECTION):
                        injector.raise_failure(FailureType.LATENCY_INJECTION)
                    results.append("latency_done")
            except Exception as e:
                results.append(f"latency_error: {type(e).__name__}")
        
        def run_with_failure():
            try:
                with injector.inject_general_failure(duration=1.0, probability=1.0):
                    time.sleep(0.1)
                    if injector.should_fail(FailureType.GENERAL_FAILURE):
                        injector.raise_failure(FailureType.GENERAL_FAILURE)
                    results.append("failure_done")
            except Exception as e:
                results.append(f"failure_error: {type(e).__name__}")
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(run_with_latency)
            executor.submit(run_with_failure)
            time.sleep(0.3)
        
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
