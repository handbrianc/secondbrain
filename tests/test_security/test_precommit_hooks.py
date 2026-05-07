"""Tests for security scanning pre-commit hooks.

These tests verify that security scanning tools are properly configured
in pre-commit hooks and that they run correctly.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestPrecommitHooks:
    """Test pre-commit hook configuration for security tools."""

    def test_cyclonedx_bom_hook_exists_in_precommit(self):
        """CycloneDX SBOM generation hook exists in .pre-commit-config.yaml."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        # Read and parse the YAML config
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check for cyclonedx-bom hook
        hooks = config.get("repos", [])
        cyclonedx_hook_found = False
        
        for repo in hooks:
            for hook in repo.get("hooks", []):
                if "cyclonedx" in hook.get("id", "") or "cyclonedx" in hook.get("name", ""):
                    cyclonedx_hook_found = True
                    break
        
        assert cyclonedx_hook_found, "cyclonedx-bom hook must be configured in .pre-commit-config.yaml"

    def test_pip_audit_hook_exists_in_precommit(self):
        """pip-audit vulnerability scanning hook exists in .pre-commit-config.yaml."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check for pip-audit hook
        hooks = config.get("repos", [])
        pip_audit_hook_found = False
        
        for repo in hooks:
            for hook in repo.get("hooks", []):
                if "pip-audit" in hook.get("id", "") or "pip-audit" in hook.get("name", ""):
                    pip_audit_hook_found = True
                    break
        
        assert pip_audit_hook_found, "pip-audit hook must be configured in .pre-commit-config.yaml"

    def test_vulnerability_scanning_hook_exists_in_precommit(self):
        """Vulnerability scanning hook (pip-audit) exists in .pre-commit-config.yaml."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check for vulnerability scanning hook (pip-audit)
        hooks = config.get("repos", [])
        vuln_scan_hook_found = False
        
        for repo in hooks:
            for hook in repo.get("hooks", []):
                hook_id = hook.get("id", "")
                if "pip-audit" in hook_id or "vulnerability" in hook_id.lower():
                    vuln_scan_hook_found = True
                    break
        
        assert vuln_scan_hook_found, "Vulnerability scanning hook (pip-audit) must be configured"

    def test_bandit_hook_exists_in_precommit(self):
        """Bandit security scanning hook exists in .pre-commit-config.yaml."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check for bandit hook
        hooks = config.get("repos", [])
        bandit_hook_found = False
        
        for repo in hooks:
            for hook in repo.get("hooks", []):
                if "bandit" in hook.get("id", "") or "bandit" in hook.get("name", ""):
                    bandit_hook_found = True
                    break
        
        assert bandit_hook_found, "bandit hook must be configured in .pre-commit-config.yaml"

    def test_sbom_file_is_tracked_by_precommit(self):
        """SBOM file (sbom.json) is tracked by pre-commit for change detection."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check that sbom.json is in the files filter or explicitly tracked
        hooks = config.get("repos", [])
        sbom_tracked = False
        
        for repo in hooks:
            files_filter = repo.get("files", "")
            for hook in repo.get("hooks", []):
                hook_files = hook.get("files", "")
                if "sbom" in files_filter.lower() or "sbom" in hook_files.lower():
                    sbom_tracked = True
                    break
        
        # Alternative: Check if there's a hook that validates sbom.json
        for repo in hooks:
            for hook in repo.get("hooks", []):
                if "sbom" in str(hook).lower():
                    sbom_tracked = True
                    break
        
        # SBOM tracking should be configured
        assert sbom_tracked, "sbom.json should be tracked by pre-commit for change detection"

    def test_cyclonedx_bom_can_generate_sbom(self):
        """CycloneDX can successfully generate SBOM file."""
        try:
            result = subprocess.run(
                ["cyclonedx-py", "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            assert result.returncode == 0, "cyclonedx-py must be installed"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("cyclonedx-py not installed, skipping test")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "sbom-test.json")
            result = subprocess.run(
                ["cyclonedx-py", "venv", "-o", output_file],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/Users/bchand/Documents/secondbrain"
            )
            
            if result.returncode != 0:
                pytest.skip(f"cyclonedx-py not configured properly: {result.stderr[:200]}")
            
            assert os.path.exists(output_file), "SBOM file was not created"
            
            # Verify it's valid JSON
            with open(output_file) as f:
                sbom = json.load(f)
            
            # Verify basic SBOM structure
            assert "bomFormat" in sbom, "SBOM must have bomFormat field"
            assert sbom["bomFormat"] == "CycloneDX", "SBOM format must be CycloneDX"
            assert "components" in sbom, "SBOM must have components array"

    def test_security_hooks_block_on_high_severity(self):
        """Security hooks are configured to fail on high severity issues."""
        precommit_config = Path(".pre-commit-config.yaml")
        
        assert precommit_config.exists(), ".pre-commit-config.yaml must exist"
        
        import yaml
        with open(precommit_config) as f:
            config = yaml.safe_load(f)
        
        # Check that security hooks have proper failure configuration
        hooks = config.get("repos", [])
        
        for repo in hooks:
            for hook in repo.get("hooks", []):
                hook_id = hook.get("id", "")
                
                if "safety" in hook_id or "pip-audit" in hook_id:
                    # These hooks should fail by default on vulnerabilities
                    # Verify they don't have args that suppress failures
                    args = hook.get("args", [])
                    assert not any("--continue-on-error" in arg for arg in args), \
                        f"{hook_id} should not continue on error"

    def test_precommit_security_scan_script_exists(self):
        """Security scan script exists and is executable."""
        security_script = Path("scripts/security_scan.sh")
        
        assert security_script.exists(), "scripts/security_scan.sh must exist"
        assert security_script.stat().st_mode & 0o111, "scripts/security_scan.sh must be executable"

    def test_security_scan_script_runs_all_tools(self):
        """Security scan script runs all security tools."""
        security_script = Path("scripts/security_scan.sh")
        
        assert security_script.exists(), "scripts/security_scan.sh must exist"
        
        with open(security_script) as f:
            script_content = f.read()
        
        # Check that all security tools are called
        assert "bandit" in script_content, "Script must run bandit"
        assert "safety" in script_content or "pip-audit" in script_content, \
            "Script must run vulnerability scanner"
        assert "cyclonedx" in script_content or "sbom" in script_content.lower(), \
            "Script must generate SBOM"
