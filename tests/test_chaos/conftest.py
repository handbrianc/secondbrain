"""Pytest fixtures for chaos tests."""

from collections import defaultdict
from typing import Any

import pytest

from secondbrain.utils.failure_injector import FailureInjector


@pytest.fixture
def failure_injector() -> FailureInjector:
    """Provide a FailureInjector instance for chaos tests.

    Yields:
        FailureInjector: Configured failure injector instance.

    Note:
        The fixture automatically cleans up after each test by resetting
        all active failures.
    """
    injector = FailureInjector.get_instance()
    try:
        yield injector
    finally:
        injector.reset()
        FailureInjector.reset_instance()


@pytest.fixture(scope="session")
def chaos_metrics(config: pytest.Config) -> dict[str, Any]:
    """Session-scoped fixture accumulating resilience metrics across all chaos tests.

    Populated by `register_chaos_result` after each test, consumed by
    `pytest_terminal_summary` at end of session.
    """
    return config._chaos_session_data


@pytest.fixture
def register_chaos_result(
    request: pytest.FixtureRequest, chaos_metrics: dict[str, Any]
) -> Any:
    """Function-scoped fixture allowing chaos tests to deposit per-test metrics.

    Usage in a chaos test::

        def test_my_chaos_scenario(failure_injector, register_chaos_result):
            result = {"passed": False, "recovery_time_ms": 0, "failure_type": None}

            start = time.monotonic()
            try:
                # ... test body ...
                result["passed"] = True
            except Exception:
                result["passed"] = False
            finally:
                recovery_time = (time.monotonic() - start) * 1000
                result["recovery_time_ms"] = recovery_time
                result["failure_type"] = (
                    failure_injector.active_failures[-1].failure_type.name
                    if failure_injector.active_failures
                    else "NONE"
                )
                register_chaos_result(
                    test_name=request.node.name,
                    passed=result["passed"],
                    recovery_time_ms=recovery_time,
                    failure_type=result["failure_type"],
                )

    The fixture also interrogates the CircuitBreaker registry (if present) to
    count trips across the test run.
    """

    def _register(
        *,
        test_name: str,
        passed: bool,
        recovery_time_ms: float = 0.0,
        failure_type: str = "UNKNOWN",
        circuit_breaker_tripped: bool = False,
    ) -> None:
        chaos_metrics["results"].append(
            {
                "test": test_name,
                "passed": passed,
                "recovery_time_ms": recovery_time_ms,
                "failure_type": failure_type,
                "circuit_breaker_tripped": circuit_breaker_tripped,
            }
        )
        chaos_metrics["recovery_times"].append(recovery_time_ms)
        chaos_metrics["error_counts"][failure_type] += 1
        chaos_metrics["failure_types"][failure_type] += 1
        if circuit_breaker_tripped:
            chaos_metrics["circuit_breaker_trips"] += 1

    return _register


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Add a chaos resilience summary section to pytest's terminal output.

    Fires at the end of the test session only when at least one @pytest.mark.chaos
    test was executed.
    """
    # Locate the chaos_metrics dict from the session fixtures
    chaos_metrics_dict: dict[str, Any] | None = getattr(
        config.cache, "_chaos_metrics", None
    )
    if chaos_metrics_dict is None:
        # Try accessing via request.node if cache not set
        try:
            chaos_metrics_dict = config._chaos_metrics  # type: ignore[attr-defined]
        except AttributeError:
            return

    assert chaos_metrics_dict is not None
    results = chaos_metrics_dict.get("results", [])
    if not results:
        return  # No chaos tests were registered this session

    terminalreporter.section("chaos-resilience-report")
    terminalreporter.write_line("")
    terminalreporter.write_line("=== Chaos Resilience Aggregated Report ===", bold=True)
    terminalreporter.write_line("")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    terminalreporter.write_line(f"  Total chaos experiments : {total}")
    terminalreporter.write_line(f"  Passed                  : {passed}")
    terminalreporter.write_line(f"  Failed                  : {failed}")

    recovery_times = chaos_metrics_dict.get("recovery_times", [])
    if recovery_times:
        avg_rt = sum(recovery_times) / len(recovery_times)
        terminalreporter.write_line(f"  Avg recovery time        : {avg_rt:.2f} ms")

    cb_trips = chaos_metrics_dict.get("circuit_breaker_trips", 0)
    terminalreporter.write_line(f"  Circuit breaker trips    : {cb_trips}")

    terminalreporter.write_line("")
    terminalreporter.write_line("  Failures by type:", bold=False)
    failure_types = chaos_metrics_dict.get("failure_types", {})
    for ftype, count in sorted(failure_types.items()):
        terminalreporter.write_line(f"    {ftype:<20}: {count} occurrence(s)")

    terminalreporter.write_line("")
    terminalreporter.write_line("=== End Chaos Report ===", bold=True)


def pytest_configure(config: pytest.Config) -> None:
    """Bootstrap hook to make chaos_metrics reachable from pytest_terminal_summary.

    This fires before session fixtures are created, so we attach a mutable
    placeholder onto config._chaos_session that terminal_summary populates
    during the session.
    """
    config._chaos_session_data = {
        "results": [],
        "recovery_times": [],
        "error_counts": defaultdict(int),
        "failure_types": defaultdict(int),
        "circuit_breaker_trips": 0,
    }
