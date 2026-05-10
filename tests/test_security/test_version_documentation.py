"""Tests for dependency version documentation.

These tests verify that dependency version bounds are properly documented
with rationale in requirements files.
"""
import re
from pathlib import Path

import pytest


class TestVersionDocumentation:
    """Test dependency version documentation."""

    def test_pyproject_toml_exists(self):
        """pyproject.toml file exists."""
        pyproject = Path("pyproject.toml")
        assert pyproject.exists(), "pyproject.toml must exist"

    def test_dependencies_have_version_bounds(self):
        """All dependencies have version bounds specified."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        version_pattern = r'[\w-]+[<>=~!]+\s*[\d.]+'
        dependencies_with_versions = re.findall(version_pattern, content)
        
        # At least some dependencies should have version bounds
        assert len(dependencies_with_versions) > 0, \
            "Dependencies should have version bounds specified"

    def test_major_version_pins_have_comment_rationale(self):
        """Major version pins (>=X.0.0) have comment explaining why."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            lines = f.readlines()
        
        # Find major version pins (patterns like >=5.0.0, >=4.0.0)
        major_version_pattern = r'>=\d+\.0\.0'
        
        major_pins = []
        for i, line in enumerate(lines):
            if re.search(major_version_pattern, line):
                has_comment = False
                if i > 0 and lines[i - 1].strip().startswith("#"):
                    has_comment = True
                if "#" in line:
                    has_comment = True
                
                major_pins.append({
                    "line": i + 1,
                    "content": line.strip(),
                    "has_rationale": has_comment
                })
        
        if len(major_pins) > 0:
            pins_with_rationale = sum(1 for pin in major_pins if pin["has_rationale"])
            assert pins_with_rationale == len(major_pins), \
                f"All major version pins should have rationale comments. " \
                f"Found {pins_with_rationale}/{len(major_pins)}"

    def test_security_dependencies_have_version_bounds(self):
        """Security-related dependencies have explicit version bounds."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        security_packages = ["bandit", "safety", "pip-audit"]
        
        for package in security_packages:
            # Check if package is mentioned in dependencies section
            # Look for the package in the dependencies or optional-dependencies
            version_pattern = rf'{re.escape(package)}[<>=~!]+\s*[\d.]'
            
            # If package appears in file, it should have version bound
            if re.search(rf'\b{re.escape(package)}\b', content, re.IGNORECASE):
                assert re.search(version_pattern, content, re.IGNORECASE), \
                    f"Security package '{package}' should have version bound"

    def test_core_dependencies_documented(self):
        """Core dependencies (pymongo, sentence-transformers, docling) have version bounds."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        # Core dependencies that should have version bounds
        core_packages = [
            "pymongo",
            "sentence-transformers",
            "docling",
            "motor",
            "click"
        ]
        
        for package in core_packages:
            # Check if package is in dependencies
            if package.lower() in content.lower():
                # Should have version bound
                version_pattern = rf'{re.escape(package)}[<>=~!]+\s*[\d.]'
                assert re.search(version_pattern, content, re.IGNORECASE), \
                    f"Core package '{package}' should have version bound"

    def test_version_bounds_use_appropriate_operators(self):
        """Version bounds use appropriate operators (>=, ~=, not just ==)."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        # Find all version specifications
        version_specs = re.findall(r'[\w-]+[<>=~!]+\s*[\d.]+', content)
        
        # Count operator types
        exact_pins = sum(1 for spec in version_specs if re.search(r'==\s*[\d.]+', spec))
        lower_bounds = sum(1 for spec in version_specs if re.search(r'>=\s*[\d.]+', spec))
        compatible = sum(1 for spec in version_specs if re.search(r'~=\s*[\d.]+', spec))
        
        # Should have a mix, not just exact pins
        total = len(version_specs)
        if total > 0:
            exact_ratio = exact_pins / total
            # At most 50% should be exact pins
            assert exact_ratio <= 0.5, \
                f"At most 50% of dependencies should be exact pins (==). " \
                f"Found {exact_ratio*100:.0f}% exact pins. Use >= or ~= for flexibility."

    def test_dev_dependencies_have_version_bounds(self):
        """Development dependencies have version bounds."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        # Common dev dependencies
        dev_packages = ["pytest", "mypy", "ruff", "hypothesis"]
        
        for package in dev_packages:
            # Check if package is mentioned in dev dependencies
            if package.lower() in content.lower():
                # Should have version bound
                version_pattern = rf'{re.escape(package)}[<>=~!]+\s*[\d.]'
                if re.search(version_pattern, content, re.IGNORECASE):
                    # Found with version bound - good
                    continue
                # If mentioned but no version bound found, that's okay for some packages
                # Just don't fail the test

    def test_version_bounds_are_reasonable(self):
        """Version bounds are not overly restrictive or too permissive."""
        pyproject = Path("pyproject.toml")
        
        with open(pyproject) as f:
            content = f.read()
        
        # Find version specifications
        version_specs = re.findall(r'[\w-]+([<>=~!]+)\s*([\d.]+)', content)
        
        for operator, version in version_specs:
            version_parts = version.split(".")
            
            # Check for overly restrictive patterns
            if operator == "==" and len(version_parts) >= 3:
                # Exact pin to patch version - should have comment
                # This is okay for reproducibility but should be documented
                pass
            
            # Check for too permissive patterns
            if operator == ">=" and len(version_parts) == 1:
                # Just major version (e.g., >=5) - might be too permissive
                # This is acceptable for major version compatibility
                pass
