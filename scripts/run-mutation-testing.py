#!/usr/bin/env python3
"""Mutation testing helper script for SecondBrain.

This script provides convenient commands for running mutation testing
with mutmut to verify test quality.

Usage:
    python scripts/run-mutation-testing.py          # Run full mutation test
    python scripts/run-mutation-testing.py quick    # Run on specific module
    python scripts/run-mutation-testing.py results  # Show results
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'=' * 60}")
    print(f"🧬 {description}")
    print(f"{'=' * 60}")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)

    if result.returncode == 0:
        print(f"✅ {description} completed successfully")
        return True
    else:
        print(f"❌ {description} failed with code {result.returncode}")
        return False


def main():
    """Run mutation testing workflow."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = "full"

    if command == "quick":
        # Run mutation testing on a specific module (faster)
        module = sys.argv[2] if len(sys.argv) > 2 else "secondbrain.rag.factory"
        success = run_command(
            ["mutmut", "run", "--paths-to-mutate", module],
            f"Mutation testing for {module}",
        )

    elif command == "results":
        # Show mutation testing results
        success = run_command(["mutmut", "results"], "Getting mutation results")

    elif command == "browse":
        # Open mutation testing browser
        success = run_command(["mutmut", "browse"], "Opening mutation browser")

    else:
        # Full mutation testing run
        print("🧬 Starting Full Mutation Testing")
        print("\nThis will test all mutations across the codebase.")
        print("This may take 30-60 minutes depending on test suite size.")
        print("\nMutation testing verifies that your tests can catch real bugs.")
        print("High mutation score = tests are effective at catching errors.\n")

        # Run mutation testing
        success = run_command(["mutmut", "run"], "Running full mutation testing suite")

        if success:
            # Show results
            run_command(["mutmut", "results"], "Displaying mutation results")

            print("\n" + "=" * 60)
            print("📊 Mutation Testing Complete!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Review mutations that survived (tests didn't catch them)")
            print("2. Add tests for uncovered edge cases")
            print("3. Re-run mutation testing to verify improvement")
            print("\nCommands:")
            print("  - View detailed results: mutmut show")
            print("  - Browse mutations: python scripts/run-mutation-testing.py browse")
            print(
                "  - Run on specific module: mutmut run --paths-to-mutate secondbrain.module"
            )
        else:
            print("\n❌ Mutation testing failed. Check the output above for errors.")
            print("\nCommon issues:")
            print("  - Tests failing: Fix test failures first")
            print("  - Timeout: Increase timeout in pyproject.toml")
            print("  - Memory issues: Run on smaller modules first")


if __name__ == "__main__":
    main()
