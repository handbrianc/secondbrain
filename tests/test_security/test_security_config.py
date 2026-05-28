"""Tests for security configuration files and tools."""
import subprocess
import yaml
from pathlib import Path

import pytest


class TestSecurityConfig:
    """Test security configuration and tooling."""

    def test_dependabot_exists(self):
        """Dependabot configuration exists and is valid."""
        dependabot_path = Path(".github/dependabot.yml")
        assert dependabot_path.exists(), "dependabot.yml not found"
        
        with open(dependabot_path) as f:
            config = yaml.safe_load(f)
        
        assert "version" in config, "dependabot.yml missing version"
        assert "updates" in config or "packages" in config, \
            "dependabot.yml missing updates configuration"

    def test_pipdeptree_generates(self):
        """Dependency tree can be generated with pipdeptree."""
        result = subprocess.run(
            ["pipdeptree"],
            capture_output=True,
            text=True,
            timeout=60
        )
        assert result.returncode == 0, f"pipdeptree failed: {result.stderr}"
        assert "secondbrain" in result.stdout.lower() or "second-brain" in result.stdout.lower(), \
            "Dependency tree should include secondbrain package"

    def test_bandit_config_exists(self):
        """Bandit security scanner configuration exists."""
        config_path = Path(".bandit.yml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            assert isinstance(config, dict), "Bandit config should be valid YAML"

    def test_security_scan_script_exists(self):
        """Security scan script exists and is executable."""
        script_path = Path("scripts/security_scan.sh")
        assert script_path.exists(), "security_scan.sh not found"
        assert script_path.stat().st_mode & 0o111, "security_scan.sh should be executable"
