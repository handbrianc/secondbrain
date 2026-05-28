"""Tests for SBOM generation using CycloneDX."""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestSBOMGeneration:
    """Test CycloneDX SBOM generation functionality."""

    def test_cyclonedx_bom_generates(self):
        """SBOM can be generated with cyclonedx-bom."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            # Try different cyclonedx command syntax
            result = subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=120
            )
            # cyclonedx may exit with 0 (success) or 1 (vulnerabilities found)
            assert result.returncode in [0, 1], f"SBOM generation failed: {result.stderr}"
            assert output_path.exists(), "SBOM file was not created"
            
            # Verify valid JSON
            with open(output_path) as f:
                sbom = json.load(f)
            assert "bomFormat" in sbom, "SBOM missing bomFormat field"
            assert sbom["bomFormat"] == "CycloneDX", "SBOM format is not CycloneDX"

    def test_sbom_includes_project_dependencies(self):
        """SBOM includes key project dependencies like pymongo, click."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            result = subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                timeout=60
            )
            
            assert result.returncode in [0, 1], f"SBOM generation failed: {result.stderr}"
            assert output_path.exists(), "SBOM file should be created"
            
            with open(output_path) as f:
                sbom = json.load(f)
            
            components = sbom.get("components", [])
            component_names = [c.get("name", "").lower() for c in components]
            
            # Check for key dependencies
            assert any("pymongo" in name for name in component_names), "pymongo should be in SBOM"
            assert any("click" in name for name in component_names), "click should be in SBOM"

    def test_sbom_format_version(self):
        """SBOM uses valid CycloneDX format version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                timeout=60
            )
            
            with open(output_path) as f:
                sbom = json.load(f)
            
            # Should have valid version like "1.4", "1.5", etc.
            version = sbom.get("specVersion", "")
            assert version, "SBOM missing specVersion"
            assert version.startswith("1."), f"Unexpected specVersion format: {version}"
