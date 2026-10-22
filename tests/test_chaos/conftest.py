"""Pytest fixtures and reporting hooks for chaos tests.

Chaos tests are opt-in via ``@pytest.mark.chaos`` (the default run excludes
them through ``-m 'not chaos'`` in the ``pyproject.toml`` addopts).

Every collected chaos test auto-registers its per-test outcome — pass/fail,
failure types exercised, recovery time, circuit-breaker trips and a snapshot
of the captured system state — into ``config._chaos_session_data``.
``pytest_terminal_summary`` aggregates those records into a
"chaos-resilience-report" terminal section whenever at least one chaos test
ran, merging in records sent back from pytest-xdist workers through the
``workeroutput`` channel (the project addopts run the suite with
``-n auto``, so the summary always renders on the controller). The hook is a
strict no-op — no section at all — when no chaos test registered a result,
e.g. in the default suite.

Under pytest-xdist, tests execute in worker processes while terminal
reporting happens in the controller, so per-process accumulators cannot be
read directly at summary time. Workers therefore publish their accumulated
chaos metrics in ``config.workeroutput`` (forwarded by pytest-xdist with the
"workerfinished" event) and the controller collects them in
``pytest_testnodedown`` before rendering the section.
"""

import os
from collections import Counter
from collections.abc import Generator
from typing import Any

import pytest

from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitState
from secondbrain.utils.failure_injector import FailureConfig, FailureInjector

_CHAOS_DATA_ATTR = "_chaos_session_data"
_WORKEROUTPUT_KEY = "chaos_resilience_metrics"
_NO_FAILURE_TYPE = "NONE"
_UNSET_FAILURE_TYPE = "UNKNOWN"

# Chaos metrics payloads received from xdist workers (controller process only).
_worker_metrics: list[dict[str, Any]] = []


def _upsert_result(results: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    """Insert a per-test chaos record, or update the test's existing record.

    Parameters:
        results: The session's list of per-test chaos records.
        entry: Record to insert; matched against existing records by node id.
    """
    for existing in results:
        if existing["test"] == entry["test"]:
            existing.update(entry)
            return
    results.append(entry)


def pytest_configure(config: pytest.Config) -> None:
    """Seed the session-wide chaos metrics accumulator on the config.

    Runs in every process (controller and xdist workers alike) before any
    test, so the ``chaos_metrics`` fixture and ``pytest_terminal_summary``
    always reach the same accumulator by the same attribute name.
    """
    config._chaos_session_data = {"results": []}


@pytest.fixture
def failure_injector() -> Generator[FailureInjector]:
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
def chaos_metrics(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Session-scoped accumulator of per-test chaos outcomes.

    Returns the dict seeded by :func:`pytest_configure`
    (``config._chaos_session_data``), lazily re-seeding it if this process
    loaded the conftest after config parsing (e.g. a full-suite run where
    ``pytest_configure`` hooks have already fired). Populated by the
    ``chaos_auto_report`` autouse fixture, optionally enriched per test via
    ``register_chaos_result``, and aggregated by ``pytest_terminal_summary``
    into the "chaos-resilience-report" terminal section.

    Parameters:
        request: Pytest fixture request (used to reach the session config).

    Returns:
        dict[str, Any]: Accumulator whose ``"results"`` list holds one record
        per executed chaos experiment.
    """
    data: dict[str, Any] | None = getattr(request.config, _CHAOS_DATA_ATTR, None)
    if data is None:
        data = {"results": []}
        setattr(request.config, _CHAOS_DATA_ATTR, data)
    return data


@pytest.fixture
def register_chaos_result(
    request: pytest.FixtureRequest, chaos_metrics: dict[str, Any]
) -> Any:
    """Register enriched chaos metrics for the current test.

    The ``chaos_auto_report`` autouse fixture already records every chaos
    test's outcome (pass/fail, recovery time, failure types exercised,
    circuit-breaker trips, system-state snapshot). Accept this fixture in
    tests that want to attach richer or more specific context; fields passed
    here win over the auto-derived ones, while the test's pass/fail outcome
    always comes from the actual test report.

    Parameters:
        request: Pytest fixture request (used to default ``test_name`` to the
            current test's node id).
        chaos_metrics: Session-scoped chaos outcome accumulator.

    Returns:
        Callable accepting keyword-only registration fields:
        ``failure_type``, ``circuit_breaker_tripped``, ``recovery_time_ms``
        and ``test_name``.

    Usage::

        def test_partition_recovery(
            failure_injector, register_chaos_result
        ):
            with failure_injector.inject_connection_error():
                ...  # exercise the system under failure
            register_chaos_result(
                failure_type="connection_error",
                circuit_breaker_tripped=True,
            )

    Note:
        Omit ``test_name`` to attach the metrics to this test's own record;
        pass an explicit ``test_name`` only to record a distinct
        sub-experiment within the same test.
    """

    def _register(
        *,
        failure_type: str = _UNSET_FAILURE_TYPE,
        circuit_breaker_tripped: bool = False,
        recovery_time_ms: float | None = None,
        test_name: str | None = None,
    ) -> None:
        """Upsert one chaos outcome record into the session accumulator.

        Parameters:
            failure_type: Type of failure exercised (e.g. ``"timeout"``).
            circuit_breaker_tripped: Whether a circuit breaker tripped.
            recovery_time_ms: Measured recovery time in milliseconds.
            test_name: Owning test's node id (defaults to this test).
        """
        entry: dict[str, Any] = {
            "test": test_name or request.node.nodeid,
            "failure_type": failure_type,
            "circuit_breaker_tripped": circuit_breaker_tripped,
        }
        if recovery_time_ms is not None:
            entry["recovery_time_ms"] = float(recovery_time_ms)
        _upsert_result(chaos_metrics["results"], entry)

    return _register


@pytest.fixture(autouse=True)
def chaos_auto_report(
    request: pytest.FixtureRequest, chaos_metrics: dict[str, Any]
) -> Generator[None]:
    """Auto-register every chaos test's outcome into ``chaos_metrics``.

    Instruments the failure-injection and circuit-breaker entry points for
    the duration of the test so injected failure types and breaker trips are
    observed even when the test itself passes, then registers the outcome at
    teardown (the call-phase report is captured by
    ``pytest_runtest_makereport`` before finalizers reset the injector).

    Non-chaos tests in this directory (e.g. the reporting meta-tests) pass
    through untouched, keeping the aggregated report silent unless actual
    chaos tests ran.
    """
    if request.node.get_closest_marker("chaos") is None:
        yield
        return

    injected_types: list[str] = []
    breaker_trips = 0
    original_config_init = FailureConfig.__init__
    original_record_failure = CircuitBreaker.record_failure

    def _spying_config_init(
        self: FailureConfig, failure_type: Any, *args: Any, **kwargs: Any
    ) -> None:
        injected_types.append(failure_type.value)
        original_config_init(self, failure_type, *args, **kwargs)

    def _spying_record_failure(self: CircuitBreaker, *args: Any, **kwargs: Any) -> None:
        nonlocal breaker_trips
        was_open = self.state == CircuitState.OPEN
        original_record_failure(self, *args, **kwargs)
        if not was_open and self.state == CircuitState.OPEN:
            breaker_trips += 1

    FailureConfig.__init__ = _spying_config_init
    CircuitBreaker.record_failure = _spying_record_failure
    try:
        yield
    finally:
        FailureConfig.__init__ = original_config_init
        CircuitBreaker.record_failure = original_record_failure
        _register_auto_result(
            chaos_metrics,
            request=request,
            injected_types=injected_types,
            breaker_trips=breaker_trips,
        )


def _snapshot_active_injections() -> str:
    """Snapshot the singleton failure injector's still-active injections.

    Returns:
        str: ``"+".join`` of active failure-type names, ``"none"`` when the
        injector is idle, or ``"unknown"`` if the state is unreadable.
    """
    try:
        injector = FailureInjector.get_instance()
        with injector._lock:
            active = sorted(
                {
                    failure_config.failure_type.value
                    for failure_config in injector._active_failures.values()
                }
            )
    except Exception:
        return "unknown"
    return "+".join(active) if active else "none"


def _register_auto_result(
    data: dict[str, Any],
    *,
    request: pytest.FixtureRequest,
    injected_types: list[str],
    breaker_trips: int,
) -> None:
    """Record the current test's outcome in the chaos accumulator.

    Enriches a record previously created by ``register_chaos_result`` when
    present (explicit fields win), otherwise appends a fresh record.

    Parameters:
        data: Session chaos accumulator (``chaos_metrics``).
        request: Fixture request for the finished test.
        injected_types: Failure types observed during the test.
        breaker_trips: Circuit-breaker trips observed during the test.
    """
    test = request.node.nodeid
    call_report: pytest.TestReport | None = getattr(
        request.node, "_chaos_call_report", None
    )
    setup_report: pytest.TestReport | None = getattr(
        request.node, "_chaos_setup_report", None
    )
    active_at_end = getattr(request.node, "_chaos_active_injections", "unknown")

    if call_report is None:
        if setup_report is not None and setup_report.failed:
            _upsert_result(
                data["results"],
                {
                    "test": test,
                    "passed": False,
                    "recovery_time_ms": 0.0,
                    "failure_type": "SETUP",
                    "circuit_breaker_tripped": False,
                    "error": "chaos experiment failed during setup",
                    "state": (
                        "injected=none; "
                        f"active_at_end={active_at_end}; trips={breaker_trips}"
                    ),
                },
            )
        return  # skipped or never reached the call phase: nothing to report

    if call_report.skipped:
        return

    passed = call_report.passed
    error: str | None = None
    if not passed:
        longrepr = getattr(call_report, "longreprtext", "") or ""
        longrepr_lines = [
            line.strip() for line in longrepr.splitlines() if line.strip()
        ]
        # Prefer the traceback's "E <exception>" summary line (the most
        # useful failure context); fall back to the final crash-location line.
        summary_lines = [line for line in longrepr_lines if line.startswith("E ")]
        error = (
            summary_lines[-1]
            if summary_lines
            else (
                longrepr_lines[-1] if longrepr_lines else "test failed without a repr"
            )
        )[:200]

    observed = sorted(set(injected_types))
    if observed:
        failure_type = "+".join(observed)
    elif breaker_trips:
        failure_type = "circuit_breaker"
    else:
        failure_type = _NO_FAILURE_TYPE

    entry: dict[str, Any] = {
        "test": test,
        "passed": passed,
        "recovery_time_ms": round(call_report.duration * 1000.0, 2),
        "failure_type": failure_type,
        "circuit_breaker_tripped": breaker_trips > 0,
        "error": error,
        "state": (
            f"injected={'+'.join(observed) if observed else 'none'}; "
            f"active_at_end={active_at_end}; trips={breaker_trips}"
        ),
    }

    for existing in data["results"]:
        if existing["test"] != test:
            continue
        existing["passed"] = passed
        existing["recovery_time_ms"] = entry["recovery_time_ms"]
        existing["error"] = error
        existing["state"] = entry["state"]
        if existing.get("failure_type") in (None, "", _UNSET_FAILURE_TYPE):
            existing["failure_type"] = failure_type
        if not existing.get("circuit_breaker_tripped"):
            existing["circuit_breaker_tripped"] = breaker_trips > 0
        return
    data["results"].append(entry)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> None:
    """Capture the call-phase report and injector state for auto-reporting.

    The call-phase report is finalized before fixture finalizers run, so the
    failure injector's state is still intact when snapshotted here.

    Parameters:
        item: The test item being reported.
        call: The runtest call phase (setup/call/teardown) being reported.
    """
    outcome = yield
    if item.get_closest_marker("chaos") is None:
        return
    report: pytest.TestReport = outcome.get_result()
    if report.when == "call":
        item._chaos_call_report = report
        item._chaos_active_injections = _snapshot_active_injections()
    elif report.when == "setup" and report.failed:
        item._chaos_setup_report = report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Ship this process's chaos metrics to the xdist controller (workers only).

    pytest-xdist serializes ``config.workeroutput`` back to the controller
    with the "workerfinished" event; non-worker processes (controller, or a
    plain single-process session) are skipped because the summary reads
    ``config._chaos_session_data`` directly there.

    Parameters:
        session: The pytest session that just finished.
        exitstatus: Session exit status (unused; part of the hook contract).
    """
    config = session.config
    data: dict[str, Any] | None = getattr(config, _CHAOS_DATA_ATTR, None)
    if not data or not data.get("results"):
        return
    workeroutput: dict[str, Any] | None = getattr(config, "workeroutput", None)
    if workeroutput is None:
        return
    workeroutput[_WORKEROUTPUT_KEY] = {
        "worker": os.environ.get("PYTEST_XDIST_WORKER", "worker"),
        "results": [dict(entry) for entry in data["results"]],
    }


def pytest_testnodedown(node: Any, error: Any = None) -> None:
    """Collect chaos metrics sent back by a finished xdist worker.

    Runs on the controller when a worker node finishes; pytest-xdist delivers
    the worker's ``workeroutput`` on the node before this hook fires.

    Parameters:
        node: The xdist worker controller that finished.
        error: Error object if the node died unexpectedly (unused).
    """
    payload = (getattr(node, "workeroutput", None) or {}).get(_WORKEROUTPUT_KEY)
    if payload:
        _worker_metrics.append(payload)


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Emit the aggregated "chaos-resilience-report" terminal section.

    Includes failure recovery times (average and max), error rates, circuit
    breaker triggers, failure types exercised, and — for failed experiments —
    per-test context (failure type, recovery time, captured state, error).

    Strict no-op — no section at all — when no chaos test registered a
    result, e.g. the default suite where chaos tests are deselected.

    Parameters:
        terminalreporter: Pytest terminal reporter to write the section to.
        exitstatus: Session exit status (unused; part of the hook contract).
        config: Session config owning the chaos accumulator.
    """
    data: dict[str, Any] = getattr(config, _CHAOS_DATA_ATTR, None) or {}
    results: list[dict[str, Any]] = list(data.get("results", []))
    for payload in _worker_metrics:
        for entry in payload.get("results", []):
            _upsert_result(results, dict(entry))
    if not results:
        return

    total = len(results)
    passed = sum(1 for entry in results if entry["passed"])
    failed = total - passed
    error_rate = (failed / total) * 100.0
    recovery_times = [
        entry["recovery_time_ms"]
        for entry in results
        if entry.get("recovery_time_ms") is not None
    ]
    avg_recovery = sum(recovery_times) / len(recovery_times) if recovery_times else 0.0
    max_recovery = max(recovery_times) if recovery_times else 0.0
    trips = sum(1 for entry in results if entry.get("circuit_breaker_tripped"))
    by_type = Counter(
        entry.get("failure_type") or _NO_FAILURE_TYPE for entry in results
    )
    typed = {
        ftype: count for ftype, count in by_type.items() if ftype != _NO_FAILURE_TYPE
    }

    terminalreporter.section("chaos-resilience-report")
    terminalreporter.write_line("")
    terminalreporter.write_line("=== Chaos Resilience Aggregated Report ===", bold=True)
    terminalreporter.write_line("")
    terminalreporter.write_line(f"  {'Total chaos experiments':<24}: {total}")
    terminalreporter.write_line(f"  {'Passed':<24}: {passed}")
    terminalreporter.write_line(f"  {'Failed':<24}: {failed}")
    terminalreporter.write_line(f"  {'Error rate':<24}: {error_rate:.1f} %")
    terminalreporter.write_line(f"  {'Avg recovery time':<24}: {avg_recovery:.2f} ms")
    terminalreporter.write_line(f"  {'Max recovery time':<24}: {max_recovery:.2f} ms")
    terminalreporter.write_line(f"  {'Circuit breaker trips':<24}: {trips}")
    terminalreporter.write_line("")
    terminalreporter.write_line("  Failure types exercised:")
    if typed:
        for ftype, count in sorted(typed.items()):
            terminalreporter.write_line(f"    {ftype:<24}: {count} experiment(s)")
    else:
        terminalreporter.write_line("    (none observed)")
    if failed:
        terminalreporter.write_line("")
        terminalreporter.write_line("  Failed experiments:", bold=True)
        for entry in results:
            if entry["passed"]:
                continue
            terminalreporter.write_line(
                f"    {entry['test']}"
                f" [type={entry.get('failure_type', _NO_FAILURE_TYPE)}"
                f" recovery={entry.get('recovery_time_ms', 0.0):.2f}ms"
                f" state={entry.get('state', 'n/a')}]"
            )
            if entry.get("error"):
                terminalreporter.write_line(f"      {entry['error']}")
    terminalreporter.write_line("")
    terminalreporter.write_line("=== End Chaos Report ===", bold=True)
