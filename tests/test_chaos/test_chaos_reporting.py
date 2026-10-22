"""End-to-end tests for the chaos-resilience-report terminal section.

These are meta-tests: each one runs a miniature chaos scenario through a
child pytest session (pytest's ``Pytester`` harness) built around the real
``tests/test_chaos/conftest.py`` reporting machinery, and asserts what
``pytest_terminal_summary`` emits. They are NOT chaos tests — they test the
reporting hook itself — so they deliberately carry no ``@pytest.mark.chaos``
and run in the default suite (including under the project addopts'
``-m 'not chaos'``).
"""

from pathlib import Path
from typing import Any

import pytest

_CONFTTEST_PATH = Path(__file__).with_name("conftest.py")
_SRC_PATH = Path(__file__).resolve().parents[2] / "src"

_MINI_CHAOS_TEST = '''
import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from secondbrain.utils.failure_injector import FailureType


@pytest.mark.chaos
def test_injected_connection_errors_trip_circuit(
    failure_injector, register_chaos_result
):
    """Chaos experiment: injected connection errors open the circuit."""
    circuit_breaker = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01)
    )

    with failure_injector.inject_connection_error():
        for _ in range(2):
            if failure_injector.should_fail(FailureType.CONNECTION_ERROR):
                try:
                    failure_injector.raise_failure(FailureType.CONNECTION_ERROR)
                except Exception:
                    circuit_breaker.record_failure()

    assert circuit_breaker.state == CircuitState.OPEN
    register_chaos_result(
        failure_type="connection_error",
        circuit_breaker_tripped=True,
    )
'''

_MINI_FAILING_CHAOS_TEST = '''
import pytest


@pytest.mark.chaos
def test_injected_failure_never_recovers():
    """Chaos experiment that fails: the report must log it with context."""
    raise RuntimeError("injected system did not recover")
'''


def _report_line(label: str, value: str) -> str:
    """Build the exact terminal line the report writes for a metric."""
    return f"*  {label:<24}: {value}*"


@pytest.fixture
def pytester(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Provide pytest's ``Pytester`` harness for these meta-tests.

    The ``pytester`` plugin cannot be enabled from this directory: declaring
    ``pytest_plugins`` in a non-root conftest breaks full-suite collection
    runs, and the root conftest is outside this change's scope. So the same
    ``Pytester`` object the plugin's fixture builds is constructed here
    directly, after wiring up the ``--runpytest`` option the constructor
    reads (only when the plugin is not already active).
    """
    config = request.config
    if not hasattr(config.option, "runpytest"):
        monkeypatch.setattr(config.option, "runpytest", "inprocess", raising=False)
        monkeypatch.setitem(config._parser._opt2dest, "--runpytest", "runpytest")
    return pytest.Pytester(request, tmp_path_factory, monkeypatch, _ispytest=True)


def _make_chaos_project(pytester: Any) -> None:
    """Populate a pytester project with the real conftest and src path.

    Parameters:
        pytester: The Pytester harness to populate.
    """
    pytester.syspathinsert(str(_SRC_PATH))
    pytester.makeconftest(_CONFTTEST_PATH.read_text(encoding="utf-8"))


def test_chaos_report_emitted_for_chaos_session(pytester: Any) -> None:
    """A chaos session emits the chaos-resilience-report with its metrics."""
    _make_chaos_project(pytester)
    pytester.makepyfile(test_mini_chaos=_MINI_CHAOS_TEST)

    result = pytester.runpytest("-m", "chaos")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "*chaos-resilience-report*",
            "=== Chaos Resilience Aggregated Report ===*",
            _report_line("Total chaos experiments", "1"),
            _report_line("Passed", "1"),
            _report_line("Failed", "0"),
            _report_line("Error rate", "0.0 %"),
            _report_line("Circuit breaker trips", "1"),
            "*Failure types exercised:*",
            "*connection_error*1 experiment(s)*",
            "=== End Chaos Report ===*",
        ]
    )


def test_no_chaos_report_without_chaos_tests(pytester: Any) -> None:
    """A session without chaos tests emits no chaos-resilience-report."""
    _make_chaos_project(pytester)
    pytester.makepyfile(
        test_mini_plain=(
            "def test_plain():\n"
            '    """A non-chaos test must not produce a chaos report."""\n'
            "    assert True\n"
        )
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert "chaos-resilience-report" not in result.stdout.str()


def test_chaos_report_logs_failed_experiments(pytester: Any) -> None:
    """A failed chaos experiment is reported with full context."""
    _make_chaos_project(pytester)
    pytester.makepyfile(test_mini_chaos_failure=_MINI_FAILING_CHAOS_TEST)

    result = pytester.runpytest("-m", "chaos")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*chaos-resilience-report*",
            "=== Chaos Resilience Aggregated Report ===*",
            _report_line("Total chaos experiments", "1"),
            _report_line("Passed", "0"),
            _report_line("Failed", "1"),
            _report_line("Error rate", "100.0 %"),
            "*Failed experiments:*",
            "*test_injected_failure_never_recovers*type=NONE*",
            "*RuntimeError: injected system did not recover*",
        ]
    )
