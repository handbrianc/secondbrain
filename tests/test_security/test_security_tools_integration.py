"""Real-execution tests for the security tooling (SBOM + vulnerability scan).

Unlike the mocked tests in this directory (test_sbom_generation.py /
test_vulnerability_scanning.py, which exercise canned subprocess fixtures),
these tests run the actual tools when they are installed.

They are opt-in: skipped unless ``SECONDBRAIN_RUN_SECURITY_TOOL_TESTS`` is set
(and, additionally, unless the tool is on PATH), because each invocation takes
multiple seconds and queries external vulnerability data.

All output is written under pytest's ``tmp_path``; the committed ``sbom.json``
at the repo root is never touched.
"""

import json
import os
import shutil
import subprocess

import pytest

_TOOLS_ENABLED = bool(os.environ.get("SECONDBRAIN_RUN_SECURITY_TOOL_TESTS"))

_SKIP_REASON = (
    "Set SECONDBRAIN_RUN_SECURITY_TOOL_TESTS=1 and install the tool "
    "to run real security-tooling tests"
)


def _require_cyclonedx() -> None:
    if shutil.which("cyclonedx-py") is None:
        pytest.skip("cyclonedx-py is not installed or not on PATH")


def _require_pip_audit() -> None:
    if shutil.which("pip-audit") is None:
        pytest.skip("pip-audit is not installed or not on PATH")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _TOOLS_ENABLED, reason=_SKIP_REASON),
]


class TestRealCycloneDX:
    """Run cyclonedx-py for real and validate the produced SBOM."""

    def test_venv_mode_outputs_valid_cyclonedx_json(self, tmp_path):
        """cyclonedx-py venv writes a valid CycloneDX JSON SBOM to -o path."""
        _require_cyclonedx()

        output_path = tmp_path / "sbom.json"
        result = subprocess.run(
            ["cyclonedx-py", "venv", "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"cyclonedx-py failed: {result.stderr}"

        sbom = json.loads(output_path.read_text())
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"].startswith("1.")
        assert isinstance(sbom.get("components"), list)
        assert len(sbom["components"]) > 0

    def test_components_have_name_and_version(self, tmp_path):
        """Every SBOM component entry carries name/version metadata."""
        _require_cyclonedx()

        output_path = tmp_path / "sbom.json"
        result = subprocess.run(
            ["cyclonedx-py", "venv", "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"cyclonedx-py failed: {result.stderr}"
        sbom = json.loads(output_path.read_text())
        components = sbom["components"]

        sample = components[0]
        assert isinstance(sample.get("name"), str) and sample["name"]
        assert isinstance(sample.get("version"), str) and sample["version"]

    def test_env_mode_lists_key_project_dependencies(self, tmp_path):
        """cyclonedx-py env inventories the current environment incl. click/httpx."""
        _require_cyclonedx()

        output_path = tmp_path / "sbom-env.json"
        result = subprocess.run(
            ["cyclonedx-py", "env", "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"cyclonedx-py failed: {result.stderr}"
        sbom = json.loads(output_path.read_text())
        component_names = {
            component.get("name", "").lower()
            for component in sbom.get("components", [])
        }

        assert "click" in component_names
        assert "httpx" in component_names

    def test_output_stays_inside_tmp_path(self, tmp_path):
        """The -o flag fully controls the output location (repo sbom.json untouched).

        cyclonedx-py requires the output directory to already exist, so the
        test creates it explicitly.
        """
        _require_cyclonedx()

        nested = tmp_path / "nested" / "dir"
        nested.mkdir(parents=True)
        output_path = nested / "sbom.json"
        result = subprocess.run(
            ["cyclonedx-py", "venv", "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"cyclonedx-py failed: {result.stderr}"
        assert output_path.exists()
        assert str(output_path).startswith(str(tmp_path))


class TestRealPipAudit:
    """Run pip-audit for real against a synthetic requirements file.

    The requirements file contains ``flask==0.5`` — a well-known vulnerable
    pin (multiple PYSEC entries, fixed in 1.0+) — pip-audit must exit
    non-zero and name at least one PYSEC/CVE/GHSA finding.
    """

    @staticmethod
    def _write_vulnerable_requirements(tmp_path) -> str:
        requirements = tmp_path / "requirements-vulnerable.txt"
        requirements.write_text("flask==0.5\n")
        return str(requirements)

    def test_pip_audit_json_mode_flags_vulnerable_pin(self, tmp_path):
        """pip-audit -r <vulnerable pin> exits non-zero with JSON vuln report."""
        _require_pip_audit()
        requirements = self._write_vulnerable_requirements(tmp_path)

        result = subprocess.run(
            ["pip-audit", "-r", requirements, "--format", "json", "--no-deps"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode != 0, (
            "pip-audit should flag flask==0.5 as vulnerable, exit was 0"
        )
        report = json.loads(result.stdout)
        flask = next(
            dep
            for dep in report["dependencies"]
            if dep["name"] == "flask" and dep["version"] == "0.5"
        )
        assert flask["vulns"], "flask==0.5 should have known vulnerabilities"

    def test_pip_audit_reports_pysec_ids_for_vulnerable_pin(self, tmp_path):
        """The vulnerability report contains PYSEC/CVE/GHSA identifiers."""
        _require_pip_audit()
        requirements = self._write_vulnerable_requirements(tmp_path)

        result = subprocess.run(
            ["pip-audit", "-r", requirements, "--format", "json", "--no-deps"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode != 0
        report = json.loads(result.stdout)
        ids = [
            vuln["id"]
            for dep in report["dependencies"]
            for vuln in dep.get("vulns", [])
        ]

        assert ids, "expected at least one vulnerability id"
        assert any(
            vuln_id.startswith(("PYSEC-", "CVE-", "GHSA-")) for vuln_id in ids
        ), f"no recognized advisory id in {ids[:5]}"

    def test_pip_audit_text_mode_reports_vulnerabilities(self, tmp_path):
        """Default (text) output also exits non-zero and names the advisory."""
        _require_pip_audit()
        requirements = self._write_vulnerable_requirements(tmp_path)

        result = subprocess.run(
            ["pip-audit", "-r", requirements, "--no-deps"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "PYSEC-" in combined or "CVE-" in combined, (
            f"no advisory id in pip-audit text output: {combined[:300]!r}"
        )
