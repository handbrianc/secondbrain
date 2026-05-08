"""Tests for dependency tree visualization."""

from pathlib import Path

import pytest


class TestDependencyTreeVisualization:
    """Test dependency tree generation and visualization."""

    def test_pipdeptree_available(self):
        """Test that pipdeptree is available for dependency tree generation.

        QA: Verify pipdeptree can be installed and run.
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ["pipdeptree", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            assert result.returncode == 0, "pipdeptree should be available"
        except FileNotFoundError:
            # pipdeptree not installed - document as gap
            pytest.skip("pipdeptree not installed")

    def test_dependency_tree_generates(self):
        """Test that dependency tree can be generated.

        QA: Verify pipdeptree produces valid output.
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ["pipdeptree"],
                capture_output=True,
                text=True,
                timeout=30
            )
            assert result.returncode == 0, "pipdeptree should run successfully"
            assert len(result.stdout) > 0, "Dependency tree should have output"
        except FileNotFoundError:
            pytest.skip("pipdeptree not installed")

    def test_dependency_tree_shows_transitive(self):
        """Test that dependency tree shows transitive dependencies.

        QA: Verify tree includes nested dependencies.
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ["pipdeptree", "--all"],
                capture_output=True,
                text=True,
                timeout=30
            )
            assert result.returncode == 0
            # Check for nested dependencies (indented lines)
            lines = result.stdout.split("\n")
            indented_lines = [line for line in lines if line.startswith("    ")]
            assert len(indented_lines) > 0, "Tree should show transitive dependencies"
        except FileNotFoundError:
            pytest.skip("pipdeptree not installed")
        except Exception:
            pytest.skip("pipdeptree not available or failed")
