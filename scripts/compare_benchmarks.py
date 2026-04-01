#!/usr/bin/env python3
"""Compare benchmark results and detect performance regressions.

Usage:
    python compare_benchmarks.py --baseline baseline.json --current current.json
    python compare_benchmarks.py --baseline baseline.json --current current.json --threshold 10
"""

import argparse
import json
import sys
from pathlib import Path


def load_benchmark_data(filepath: str) -> dict:
    """Load benchmark data from JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {filepath}")

    with path.open() as f:
        return json.load(f)


def compare_benchmarks(
    baseline: dict, current: dict, threshold_percent: float = 10.0
) -> tuple[bool, list[dict]]:
    """Compare current benchmarks against baseline.

    Args:
        baseline: Baseline benchmark data
        current: Current benchmark data
        threshold_percent: Percentage change considered a regression

    Returns:
        Tuple of (has_regressions, list of regressions)
    """
    regressions = []

    baseline_benchmarks = {b["name"]: b for b in baseline.get("benchmarks", [])}
    current_benchmarks = {b["name"]: b for b in current.get("benchmarks", [])}

    for name, current_bench in current_benchmarks.items():
        if name not in baseline_benchmarks:
            # New benchmark, skip comparison
            continue

        baseline_bench = baseline_benchmarks[name]

        # Get mean execution times
        baseline_mean = baseline_bench.get("stats", {}).get("mean", 0)
        current_mean = current_bench.get("stats", {}).get("mean", 0)

        if baseline_mean == 0:
            continue

        # Calculate percentage change
        change_percent = ((current_mean - baseline_mean) / baseline_mean) * 100

        if change_percent > threshold_percent:
            regressions.append(
                {
                    "name": name,
                    "baseline_ms": baseline_mean * 1000,
                    "current_ms": current_mean * 1000,
                    "change_percent": change_percent,
                    "severity": "HIGH"
                    if change_percent > 50
                    else "MEDIUM"
                    if change_percent > 20
                    else "LOW",
                }
            )

    return len(regressions) > 0, regressions


def main() -> None:
    """Run benchmark comparison."""
    parser = argparse.ArgumentParser(description="Compare benchmark results")
    parser.add_argument(
        "--baseline", required=True, help="Baseline benchmark JSON file"
    )
    parser.add_argument("--current", required=True, help="Current benchmark JSON file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Regression threshold in percent (default: 10.0)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    try:
        # Load benchmark data
        print(f"Loading baseline: {args.baseline}")
        baseline = load_benchmark_data(args.baseline)

        print(f"Loading current: {args.current}")
        current = load_benchmark_data(args.current)

        # Compare benchmarks
        has_regressions, regressions = compare_benchmarks(
            baseline, current, args.threshold
        )

        # Report results
        if has_regressions:
            print(f"\n⚠️  PERFORMANCE REGRESSIONS DETECTED ({len(regressions)} found)")
            print("=" * 60)

            for reg in sorted(
                regressions, key=lambda x: x["change_percent"], reverse=True
            ):
                severity_marker = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                    reg["severity"], "⚪"
                )
                print(f"\n{severity_marker} {reg['name']}")
                print(f"   Baseline: {reg['baseline_ms']:.2f}ms")
                print(f"   Current:  {reg['current_ms']:.2f}ms")
                print(f"   Change:   +{reg['change_percent']:.1f}%")
                print(f"   Severity: {reg['severity']}")

            if args.verbose:
                print("\n" + "=" * 60)
                print("Recommendations:")
                print("  - Review recent code changes for the affected benchmarks")
                print("  - Check for algorithmic complexity changes")
                print("  - Verify system resources (CPU, memory, disk I/O)")

            sys.exit(1)
        else:
            print(
                f"\n✅ No performance regressions detected (threshold: {args.threshold}%)"
            )

            # Show improvements if verbose
            if args.verbose:
                baseline_benchmarks = {
                    b["name"]: b for b in baseline.get("benchmarks", [])
                }
                current_benchmarks = {
                    b["name"]: b for b in current.get("benchmarks", [])
                }

                improvements = []
                for name, current_bench in current_benchmarks.items():
                    if name not in baseline_benchmarks:
                        continue

                    baseline_bench = baseline_benchmarks[name]
                    baseline_mean = baseline_bench.get("stats", {}).get("mean", 0)
                    current_mean = current_bench.get("stats", {}).get("mean", 0)

                    if baseline_mean == 0:
                        continue

                    change_percent = (
                        (current_mean - baseline_mean) / baseline_mean
                    ) * 100

                    if change_percent < -args.threshold:
                        improvements.append(
                            {"name": name, "change_percent": change_percent}
                        )

                if improvements:
                    print(f"\n🚀 Performance improvements ({len(improvements)} found):")
                    for imp in sorted(improvements, key=lambda x: x["change_percent"]):
                        print(f"   {imp['name']}: {imp['change_percent']:.1f}% faster")

            sys.exit(0)

    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
