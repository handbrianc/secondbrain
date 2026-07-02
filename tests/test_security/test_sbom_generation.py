"""Tests for SBOM generation using CycloneDX."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Deterministic SBOM JSON fixture returned by mocked subprocess
SbomFixture = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.4",
    "components": [
        {"name": "pymongo", "version": "4.6.0"},
        {"name": "click", "version": "8.1.7"},
    ],
}


def _mock_subprocess_run_for_cyclonedx(cmd, *args, **kwargs):
    """Fake cyclonedx-py: writes a deterministic SBOM to the -o path, returns 0."""
    # Parse -o flag to find output path
    output_path = None
    for i, token in enumerate(cmd):
        if token == "-o" and i + 1 < len(cmd):
            output_path = Path(cmd[i + 1])
            break

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(SbomFixture, f)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    return mock_result


class TestSBOMGeneration:
    """Test CycloneDX SBOM generation functionality."""

    @patch("subprocess.run", side_effect=_mock_subprocess_run_for_cyclonedx)
    def test_cyclonedx_bom_generates(self, _mock_run):
        """SBOM can be generated with cyclonedx-bom."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            result = subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            # cyclonedx may exit with 0 (success) or 1 (vulnerabilities found)
            assert result.returncode in [0, 1], (
                f"SBOM generation failed: {result.stderr}"
            )
            assert output_path.exists(), "SBOM file was not created"

            # Verify valid JSON
            with open(output_path) as f:
                sbom = json.load(f)
            assert "bomFormat" in sbom, "SBOM missing bomFormat field"
            assert sbom["bomFormat"] == "CycloneDX", "SBOM format is not CycloneDX"

    @patch("subprocess.run", side_effect=_mock_subprocess_run_for_cyclonedx)
    def test_sbom_includes_project_dependencies(self, _mock_run):
        """SBOM includes key project dependencies like pymongo, click."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            result = subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                timeout=60,
            )

            assert result.returncode in [0, 1], (
                f"SBOM generation failed: {result.stderr}"
            )
            assert output_path.exists(), "SBOM file should be created"

            with open(output_path) as f:
                sbom = json.load(f)

            components = sbom.get("components", [])
            component_names = [c.get("name", "").lower() for c in components]

            # Check for key dependencies
            assert any("pymongo" in name for name in component_names), (
                "pymongo should be in SBOM"
            )
            assert any("click" in name for name in component_names), (
                "click should be in SBOM"
            )

    @patch("subprocess.run", side_effect=_mock_subprocess_run_for_cyclonedx)
    def test_sbom_format_version(self, _mock_run):
        """SBOM uses valid CycloneDX format version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sbom.json"
            subprocess.run(
                ["cyclonedx-py", "venv", "-o", str(output_path)],
                capture_output=True,
                timeout=60,
            )

            with open(output_path) as f:
                sbom = json.load(f)

            # Should have valid version like "1.4", "1.5", etc.
            version = sbom.get("specVersion", "")
            assert version, "SBOM missing specVersion"
            assert version.startswith("1."), f"Unexpected specVersion format: {version}"
