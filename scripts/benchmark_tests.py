#!/usr/bin/env python3
"""Test performance benchmark script."""

import contextlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    """Data class holding test benchmark results."""

    total_time: float
    num_tests: int
    slow_tests: list[tuple[float, str]]


def cleanup_coverage_files() -> None:
    """Remove coverage artifacts from previous test runs."""
    project_root = Path(__file__).parent.parent
    coverage_patterns = [
        project_root / ".coverage",
        project_root / ".coverage.*",
    ]

    for pattern in coverage_patterns:
        for coverage_file in pattern.parent.glob(pattern.name):
            with contextlib.suppress(OSError):
                coverage_file.unlink()

    htmlcov_dir = project_root / "htmlcov"
    if htmlcov_dir.exists():
        shutil.rmtree(htmlcov_dir, ignore_errors=True)


def run_tests(args: list[str]) -> TestResult:
    """Run pytest and parse results for benchmarking."""
    start_time = time.time()

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--durations=10",
        "-v",
        "--tb=no",
        "-q",
        *args,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    total_time = time.time() - start_time

    slow_tests = []
    for line in result.stdout.split("\n"):
        if "s call" in line and "tests/" in line:
            parts = line.split()
            if len(parts) >= 3:
                duration = float(parts[0].rstrip("s"))
                test_name = parts[2]
                if duration > 0.1:
                    slow_tests.append((duration, test_name))

    num_tests = 0
    for line in result.stdout.split("\n"):
        if "passed" in line or "failed" in line:
            with contextlib.suppress(ValueError, IndexError):
                num_tests = int(line.split()[0])

    return TestResult(
        total_time=total_time,
        num_tests=num_tests,
        slow_tests=sorted(slow_tests, reverse=True)[:10],
    )


def print_results(result: TestResult, test_type: str) -> None:
    """Print formatted test performance report to console."""
    print(f"\n{'=' * 60}")
    print(f"Test Performance Report: {test_type}")
    print(f"{'=' * 60}")
    print(f"Total time: {result.total_time:.2f}s")
    print(f"Tests run: {result.num_tests}")
    if result.num_tests > 0:
        print(f"Average per test: {result.total_time / result.num_tests * 1000:.2f}ms")

    if result.slow_tests:
        print("\nTop 10 slowest tests:")
        print("-" * 60)
        for duration, name in result.slow_tests:
            print(f"  {duration:6.2f}s  {name}")

    print(f"{'=' * 60}\n")


def main() -> int:
    """Run test benchmarks with optional test type filtering."""
    args = sys.argv[1:]

    if "--all" in args or not any(a in args for a in ["--unit", "--integration"]):
        test_type = "All Tests"
        pytest_args = []
    elif "--unit" in args:
        test_type = "Unit Tests"
        pytest_args = ["-m", "not integration"]
    else:
        test_type = "Integration Tests"
        pytest_args = ["-m", "integration"]

    print(f"Running {test_type}...")
    result = run_tests(pytest_args)
    print_results(result, test_type)

    return 0 if result.num_tests > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
