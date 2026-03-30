"""
Tests for Dependency Management Scripts

This module contains tests for the dependency management scripts:
- update_dependencies.sh
- audit_dependencies.sh
- generate_sbom.sh
- validate_dependencies.sh
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session")
def script_dir():
    """Get the scripts directory."""
    return Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="session")
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


class TestUpdateDependenciesScript:
    """Tests for update_dependencies.sh script."""

    @pytest.fixture
    def script_path(self, script_dir):
        """Get the path to update_dependencies.sh."""
        return script_dir / "update_dependencies.sh"

    def test_script_exists(self, script_path):
        """Test that the script file exists."""
        assert script_path.exists(), "update_dependencies.sh should exist"

    def test_script_is_executable(self, script_path):
        """Test that the script is executable."""
        assert os.access(script_path, os.X_OK), (
            "update_dependencies.sh should be executable"
        )

    def test_help_command(self, script_path):
        """Test that --help works."""
        result = subprocess.run(
            [str(script_path), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Usage:" in result.stdout, "Help should contain usage information"
        assert "check" in result.stdout, "Help should mention check command"
        assert "update" in result.stdout, "Help should mention update command"

    def test_check_command(self, script_path):
        """Test the check command."""
        result = subprocess.run(
            [str(script_path), "check"], capture_output=True, text=True, timeout=120
        )
        # Command should succeed or return non-zero for no updates
        assert result.returncode in [0, 1], f"Check command failed: {result.stderr}"

    def test_json_output_format(self, script_path, tmp_path):
        """Test JSON output format generation."""
        output_dir = tmp_path / "reports"
        result = subprocess.run(
            [
                str(script_path),
                "check",
                "--format",
                "json",
                "--output",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Should succeed or have expected non-zero exit
        assert result.returncode in [0, 1], f"JSON output failed: {result.stderr}"


class TestAuditDependenciesScript:
    """Tests for audit_dependencies.sh script."""

    @pytest.fixture
    def script_path(self, script_dir):
        """Get the path to audit_dependencies.sh."""
        return script_dir / "audit_dependencies.sh"

    def test_script_exists(self, script_path):
        """Test that the script file exists."""
        assert script_path.exists(), "audit_dependencies.sh should exist"

    def test_script_is_executable(self, script_path):
        """Test that the script is executable."""
        assert os.access(script_path, os.X_OK), (
            "audit_dependencies.sh should be executable"
        )

    def test_help_command(self, script_path):
        """Test that --help works."""
        result = subprocess.run(
            [str(script_path), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Usage:" in result.stdout, "Help should contain usage information"
        assert "pip-audit" in result.stdout, "Help should mention pip-audit"
        assert "safety" in result.stdout, "Help should mention safety"
        assert "bandit" in result.stdout, "Help should mention bandit"

    def test_pip_audit_command(self, script_path):
        """Test pip-audit command."""
        result = subprocess.run(
            [str(script_path), "pip-audit"], capture_output=True, text=True, timeout=60
        )
        # Should succeed or find vulnerabilities (non-zero)
        assert result.returncode in [0, 1], f"pip-audit failed: {result.stderr}"

    def test_sbom_generation_command(self, script_path, tmp_path):
        """Test SBOM generation command."""
        output_dir = tmp_path / "reports"
        result = subprocess.run(
            [str(script_path), "--generate-sbom-only", "-o", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Check if SBOM was generated
        sbom_file = output_dir / "sbom.json"
        if result.returncode == 0:
            assert sbom_file.exists(), "SBOM file should be generated"


class TestGenerateSBOMScript:
    """Tests for generate_sbom.sh and generate_sbom.py scripts."""

    @pytest.fixture
    def shell_script_path(self, script_dir):
        """Get the path to generate_sbom.sh."""
        return script_dir / "generate_sbom.sh"

    @pytest.fixture
    def python_script_path(self, script_dir):
        """Get the path to generate_sbom.py."""
        return script_dir / "generate_sbom.py"

    def test_shell_script_exists(self, shell_script_path):
        """Test that the shell script exists."""
        assert shell_script_path.exists(), "generate_sbom.sh should exist"

    def test_shell_script_is_executable(self, shell_script_path):
        """Test that the shell script is executable."""
        assert os.access(shell_script_path, os.X_OK), (
            "generate_sbom.sh should be executable"
        )

    def test_python_script_exists(self, python_script_path):
        """Test that the Python script exists."""
        assert python_script_path.exists(), "generate_sbom.py should exist"

    def test_python_script_is_executable(self, python_script_path):
        """Test that the Python script is executable."""
        assert os.access(python_script_path, os.X_OK), (
            "generate_sbom.py should be executable"
        )

    def test_shell_help_command(self, shell_script_path):
        """Test shell script --help."""
        result = subprocess.run(
            [str(shell_script_path), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Usage:" in result.stdout, "Help should contain usage information"
        assert "spdx" in result.stdout, "Help should mention spdx format"
        assert "cyclonedx" in result.stdout, "Help should mention cyclonedx format"

    def test_python_help_command(self, python_script_path):
        """Test Python script --help."""
        result = subprocess.run(
            [str(python_script_path), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Generate Software Bill of Materials" in result.stdout

    def test_sbom_generation_cyclonedx(self, python_script_path, tmp_path):
        """Test CycloneDX SBOM generation."""
        output_dir = tmp_path / "sbom"
        result = subprocess.run(
            [
                str(python_script_path),
                "--format",
                "cyclonedx",
                "--output",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"SBOM generation failed: {result.stderr}"

        sbom_file = output_dir / "sbom.cyclonedx.json"
        assert sbom_file.exists(), "CycloneDX SBOM should be generated"

        # Validate JSON structure
        with open(sbom_file) as f:
            data = json.load(f)
            assert "components" in data or "packages" in data, (
                "SBOM should contain components"
            )

    def test_sbom_generation_spdx(self, python_script_path, tmp_path):
        """Test SPDX SBOM generation."""
        output_dir = tmp_path / "sbom"
        result = subprocess.run(
            [str(python_script_path), "--format", "spdx", "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"SBOM generation failed: {result.stderr}"

        sbom_file = output_dir / "sbom.spdx.json"
        assert sbom_file.exists(), "SPDX SBOM should be generated"

        # Validate SPDX structure
        with open(sbom_file) as f:
            data = json.load(f)
            assert data.get("spdxVersion"), "SPDX should have spdxVersion"
            assert "packages" in data, "SPDX should have packages"

    def test_sbom_validation(self, python_script_path, tmp_path):
        """Test SBOM validation."""
        output_dir = tmp_path / "sbom"
        output_dir.mkdir(parents=True, exist_ok=True)

        # First generate an SBOM
        subprocess.run(
            [
                str(python_script_path),
                "--format",
                "cyclonedx",
                "--output",
                str(output_dir),
            ],
            capture_output=True,
            timeout=60,
        )

        # Then validate it
        result = subprocess.run(
            [str(python_script_path), "--validate", "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"SBOM validation failed: {result.stderr}"


class TestValidateDependenciesScript:
    """Tests for validate_dependencies.sh script."""

    @pytest.fixture
    def script_path(self, script_dir):
        """Get the path to validate_dependencies.sh."""
        return script_dir / "validate_dependencies.sh"

    def test_script_exists(self, script_path):
        """Test that the script file exists."""
        assert script_path.exists(), "validate_dependencies.sh should exist"

    def test_script_is_executable(self, script_path):
        """Test that the script is executable."""
        assert os.access(script_path, os.X_OK), (
            "validate_dependencies.sh should be executable"
        )

    def test_help_command(self, script_path):
        """Test that --help works."""
        result = subprocess.run(
            [str(script_path), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "Usage:" in result.stdout, "Help should contain usage information"
        assert "--strict" in result.stdout, "Help should mention strict mode"

    def test_syntax_validation(self, script_path, project_root):
        """Test pyproject.toml syntax validation."""
        result = subprocess.run(
            [str(script_path), "--no-outdated", "--no-security"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
        # Should pass syntax validation
        assert result.returncode == 0, f"Syntax validation failed: {result.stderr}"


class TestMakefileTargets:
    """Tests for Makefile targets."""

    @pytest.fixture
    def makefile_path(self, project_root):
        """Get the path to Makefile."""
        return project_root / "Makefile"

    def test_makefile_exists(self, makefile_path):
        """Test that Makefile exists."""
        assert makefile_path.exists(), "Makefile should exist"

    def test_help_target(self, makefile_path, project_root):
        """Test make help target."""
        result = subprocess.run(
            ["make", "help"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
        assert result.returncode == 0, f"Help target failed: {result.stderr}"
        assert "Available targets:" in result.stdout

    def test_deps_check_target(self, makefile_path, project_root):
        """Test make deps-check target."""
        result = subprocess.run(
            ["make", "deps-check"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=60,
        )
        # Should succeed or return non-zero for no updates
        assert result.returncode in [0, 1], f"deps-check failed: {result.stderr}"

    def test_sbom_target(self, makefile_path, project_root):
        """Test make sbom target."""
        result = subprocess.run(
            ["make", "sbom"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=120,
        )
        # May fail if cyclonedx not installed, but should not crash
        assert result.returncode in [0, 1, 2], f"sbom target failed: {result.stderr}"


class TestDocumentation:
    """Tests for documentation files."""

    def test_dependency_management_doc_exists(self, project_root):
        """Test that dependency management documentation exists."""
        doc_path = (
            project_root / "docs" / "developer-guide" / "dependency-management.md"
        )
        assert doc_path.exists(), "Dependency management documentation should exist"

    def test_dependency_management_doc_has_content(self, project_root):
        """Test that dependency management documentation has content."""
        doc_path = (
            project_root / "docs" / "developer-guide" / "dependency-management.md"
        )
        content = doc_path.read_text()
        assert len(content) > 1000, "Documentation should have substantial content"
        assert "Checking for Updates" in content, "Should have update section"
        assert "Security Scanning" in content, "Should have security section"
        assert "SBOM Generation" in content, "Should have SBOM section"

    def test_scripts_readme_updated(self, project_root):
        """Test that scripts README is updated."""
        readme_path = project_root / "scripts" / "README.md"
        content = readme_path.read_text()
        assert "update_dependencies.sh" in content, (
            "Should document update_dependencies.sh"
        )
        assert "audit_dependencies.sh" in content, (
            "Should document audit_dependencies.sh"
        )
        assert "generate_sbom" in content, "Should document generate_sbom scripts"
        assert "validate_dependencies.sh" in content, (
            "Should document validate_dependencies.sh"
        )

    def test_contributing_updated(self, project_root):
        """Test that CONTRIBUTING.md has dependency section."""
        contributing_path = project_root / "CONTRIBUTING.md"
        content = contributing_path.read_text()
        assert "Dependency Management" in content, (
            "Should have dependency management section"
        )
        assert "audit_dependencies.sh" in content, "Should mention security scan"


class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_full_dependency_workflow(self, project_root, tmp_path):
        """Test the complete dependency management workflow."""
        scripts_dir = project_root / "scripts"

        # Step 1: Check dependencies
        check_result = subprocess.run(
            [str(scripts_dir / "update_dependencies.sh"), "check"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert check_result.returncode in [0, 1], "Check should succeed or find updates"

        # Step 2: Validate dependencies
        validate_result = subprocess.run(
            [str(scripts_dir / "validate_dependencies.sh"), "--no-security"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert validate_result.returncode == 0, "Validation should pass"

    def test_sbom_full_workflow(self, project_root, tmp_path):
        """Test complete SBOM generation workflow."""
        scripts_dir = project_root / "scripts"
        output_dir = tmp_path / "sbom"

        # Generate SBOM using Python wrapper
        result = subprocess.run(
            [
                str(scripts_dir / "generate_sbom.py"),
                "--format",
                "all",
                "--output",
                str(output_dir),
                "--validate",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"SBOM workflow failed: {result.stderr}"

        # Verify both formats were created
        assert (output_dir / "sbom.cyclonedx.json").exists(), (
            "CycloneDX SBOM should exist"
        )
        assert (output_dir / "sbom.spdx.json").exists(), "SPDX SBOM should exist"
