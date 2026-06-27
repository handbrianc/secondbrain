#!/usr/bin/env python3
"""Coverage dashboard helper script for SecondBrain test suite.

This script opens the HTML coverage report in your default browser
and provides quick access to coverage statistics.

Usage:
    python scripts/open-coverage-dashboard.py
    python scripts/open-coverage-dashboard.py --module secondbrain.rag
"""

import sys
import webbrowser
from pathlib import Path


def main():
    """Open coverage dashboard in browser."""
    # Find the coverage HTML report
    coverage_dir = Path(__file__).parent.parent / "htmlcov"
    index_html = coverage_dir / "index.html"

    if not index_html.exists():
        print("❌ Coverage report not found. Run tests with coverage first:")
        print("   pytest --cov=secondbrain --cov-report=html")
        sys.exit(1)

    # Open in browser
    url = f"file://{index_html.absolute()}"
    print(f"📊 Opening coverage dashboard: {index_html}")
    webbrowser.open(url)

    # Print summary stats
    print("\n📈 Quick Stats:")
    print("   - Overall coverage report: index.html")
    print("   - Module breakdown: class_index.html")
    print("   - Function breakdown: function_index.html")
    print("\n💡 Tip: Run 'pytest --cov=secondbrain' to regenerate report")


if __name__ == "__main__":
    main()
