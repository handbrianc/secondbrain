#!/usr/bin/env python3
"""
Benchmark comparison and baseline management script.

This script provides functionality to:
- Compare benchmark results against stored baselines
- Detect performance regressions (>10% threshold)
- Store new baselines on main branch merges
- Generate regression alerts

Usage:
    # Compare current benchmarks against baseline
    python scripts/benchmark_compare.py compare --baseline benchmarks/baselines/main.json

    # Run benchmarks and save results
    pytest benchmarks/ --benchmark-json=output.json

    # Save current results as new baseline
    python scripts/benchmark_compare.py save-baseline --input output.json --name main

    # Check for regressions with custom threshold
    python scripts/benchmark_compare.py compare --baseline benchmarks/baselines/main.json --threshold 0.15
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def load_benchmark_results(file_path: Path) -> dict[str, Any]:
    """Load benchmark results from JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Benchmark results file not found: {file_path}")

    with file_path.open() as f:
        return json.load(f)


def calculate_regression(current: dict, baseline: dict) -> float:
    """
    Calculate regression percentage between current and baseline.

    Returns positive value for regression (slower), negative for improvement (faster).
    """
    current_time = current.get("stats", {}).get("mean", 0)
    baseline_time = baseline.get("stats", {}).get("mean", 0)

    if baseline_time == 0:
        return 0.0

    return ((current_time - baseline_time) / baseline_time) * 100


def compare_benchmarks(
    current_results: dict, baseline_results: dict, threshold: float = 0.10
) -> dict[str, Any]:
    """
    Compare current benchmark results against baseline.

    Args:
        current_results: Current benchmark results
        baseline_results: Baseline benchmark results
        threshold: Regression threshold (default 10%)

    Returns:
        Dictionary with comparison results and regression alerts
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "threshold_percent": threshold * 100,
        "benchmarks": [],
        "has_regression": False,
        "regressions": [],
        "improvements": [],
        "summary": {},
    }

    current_tests = {t["name"]: t for t in current_results.get("benchmarks", [])}
    baseline_tests = {t["name"]: t for t in baseline_results.get("benchmarks", [])}

    # Compare common benchmarks
    for name in current_tests:
        if name not in baseline_tests:
            continue

        current = current_tests[name]
        baseline = baseline_tests[name]

        regression_pct = calculate_regression(current, baseline)

        benchmark_result = {
            "name": name,
            "current_mean_ms": current.get("stats", {}).get("mean", 0) * 1000,
            "baseline_mean_ms": baseline.get("stats", {}).get("mean", 0) * 1000,
            "regression_percent": regression_pct,
            "status": "regression"
            if regression_pct > threshold * 100
            else "improvement"
            if regression_pct < -threshold * 100
            else "ok",
        }

        results["benchmarks"].append(benchmark_result)

        if regression_pct > threshold * 100:
            results["has_regression"] = True
            results["regressions"].append(benchmark_result)
        elif regression_pct < -threshold * 100:
            results["improvements"].append(benchmark_result)

    # Generate summary
    total = len(results["benchmarks"])
    regressions = len(results["regressions"])
    improvements = len(results["improvements"])

    results["summary"] = {
        "total_benchmarks": total,
        "passed": total - regressions - improvements,
        "regressions": regressions,
        "improvements": improvements,
        "regression_rate": (regressions / total * 100) if total > 0 else 0,
    }

    return results


def save_baseline(results: dict, baseline_name: str, output_dir: Path) -> Path:
    """Save benchmark results as a new baseline."""
    baseline_file = output_dir / f"{baseline_name}.json"

    baseline_data = {
        "name": baseline_name,
        "created_at": datetime.now().isoformat(),
        "benchmarks": results.get("benchmarks", []),
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    with baseline_file.open("w") as f:
        json.dump(baseline_data, f, indent=2)

    return baseline_file


def print_comparison_results(results: dict) -> None:
    """Print formatted comparison results to console."""
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON RESULTS")
    print("=" * 70)
    print(f"Timestamp: {results['timestamp']}")
    print(f"Regression Threshold: {results['threshold_percent']}%")
    print("-" * 70)

    # Summary
    summary = results["summary"]
    print("\nSUMMARY:")
    print(f"  Total Benchmarks: {summary['total_benchmarks']}")
    print(f"  Passed: {summary['passed']}")
    print(f"  Regressions: {summary['regressions']}")
    print(f"  Improvements: {summary['improvements']}")
    print(f"  Regression Rate: {summary['regression_rate']:.1f}%")

    # Regressions
    if results["regressions"]:
        print("\n⚠️  REGRESSIONS DETECTED:")
        for reg in results["regressions"]:
            print(f"  ❌ {reg['name']}")
            print(f"      Current: {reg['current_mean_ms']:.2f}ms")
            print(f"      Baseline: {reg['baseline_mean_ms']:.2f}ms")
            print(f"      Regression: {reg['regression_percent']:.1f}%")

    # Improvements
    if results["improvements"]:
        print("\n✅ IMPROVEMENTS:")
        for imp in results["improvements"]:
            print(f"  🚀 {imp['name']}")
            print(f"      Current: {imp['current_mean_ms']:.2f}ms")
            print(f"      Baseline: {imp['baseline_mean_ms']:.2f}ms")
            print(f"      Improvement: {abs(imp['regression_percent']):.1f}%")

    # All benchmarks table
    print(f"\n{'=' * 70}")
    print("ALL BENCHMARKS:")
    print(f"{'Name':<40} {'Current':>12} {'Baseline':>12} {'Change':>10}")
    print("-" * 70)

    for bench in results["benchmarks"]:
        status_icon = {"regression": "❌", "improvement": "🚀", "ok": "✅"}.get(
            bench["status"], "  "
        )

        change_str = f"{bench['regression_percent']:+.1f}%"
        print(
            f"{status_icon} {bench['name']:<38} "
            f"{bench['current_mean_ms']:>10.2f}ms "
            f"{bench['baseline_mean_ms']:>10.2f}ms "
            f"{change_str:>10}"
        )

    print("=" * 70 + "\n")

    # Exit with error code if regressions detected
    if results["has_regression"]:
        print("❌ PERFORMANCE REGRESSION DETECTED!")
        print(
            f"   {len(results['regressions'])} benchmark(s) exceeded {results['threshold_percent']}% threshold"
        )
        sys.exit(1)
    else:
        print("✅ All benchmarks within acceptable range")
        sys.exit(0)


def main():
    """Run benchmark comparison script."""
    parser = argparse.ArgumentParser(
        description="Compare benchmark results against baseline and detect regressions"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare", help="Compare benchmarks against baseline"
    )
    compare_parser.add_argument(
        "--current",
        "-c",
        type=Path,
        default="benchmark-results.json",
        help="Current benchmark results file",
    )
    compare_parser.add_argument(
        "--baseline",
        "-b",
        type=Path,
        required=True,
        help="Baseline benchmark results file",
    )
    compare_parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.10,
        help="Regression threshold (default: 0.10 = 10%%)",
    )
    compare_parser.add_argument(
        "--output", "-o", type=Path, help="Output JSON file for results"
    )

    # Save baseline command
    save_parser = subparsers.add_parser(
        "save-baseline", help="Save current results as new baseline"
    )
    save_parser.add_argument(
        "--input", "-i", type=Path, required=True, help="Benchmark results file to save"
    )
    save_parser.add_argument(
        "--name", "-n", type=str, default="main", help="Baseline name (default: main)"
    )
    save_parser.add_argument(
        "--output-dir",
        "-d",
        type=Path,
        default=Path("benchmarks/baselines"),
        help="Output directory for baselines",
    )

    args = parser.parse_args()

    if args.command == "compare":
        # Load results
        current = load_benchmark_results(args.current)
        baseline = load_benchmark_results(args.baseline)

        # Compare
        results = compare_benchmarks(current, baseline, args.threshold)

        # Output
        if args.output:
            with Path(args.output).open("w") as f:
                json.dump(results, f, indent=2)
            print(f"Results saved to: {args.output}")

        print_comparison_results(results)

    elif args.command == "save-baseline":
        results = load_benchmark_results(args.input)
        baseline_file = save_baseline(results, args.name, args.output_dir)
        print(f"✅ Baseline saved: {baseline_file}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
