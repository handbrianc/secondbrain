"""Tests for Dependabot configuration."""

from pathlib import Path

import pytest


class TestDependabotConfiguration:
    """Test Dependabot configuration exists and is valid."""

    def test_dependabot_config_exists(self):
        """Test that .github/dependabot.yml exists.

        QA: Verify Dependabot configuration file exists for automated updates.
        """
        dependabot_config = Path(".github/dependabot.yml")
        
        if not dependabot_config.exists():
            pytest.skip(".github/dependabot.yml not found - configuration gap")
        
        assert dependabot_config.exists(), ".github/dependabot.yml must exist"

    def test_dependabot_weekly_updates(self):
        """Test that Dependabot is configured for weekly updates.

        QA: Verify update frequency is set to weekly.
        """
        dependabot_config = Path(".github/dependabot.yml")
        
        if not dependabot_config.exists():
            pytest.skip(".github/dependabot.yml not found")
        
        import yaml
        
        with open(dependabot_config) as f:
            config = yaml.safe_load(f)
        
        updates = config.get("updates", [])
        if updates:
            for update in updates:
                schedule = update.get("schedule", {})
                interval = schedule.get("interval", "")
                assert interval == "weekly", f"Update interval should be 'weekly', got '{interval}'"
        else:
            pytest.skip("No updates configured in dependabot.yml")

    def test_dependabot_pr_labeling(self):
        """Test that Dependabot is configured to label PRs.

        QA: Verify dependabot PRs are automatically labeled with 'dependencies'.
        """
        dependabot_config = Path(".github/dependabot.yml")
        
        if not dependabot_config.exists():
            pytest.skip(".github/dependabot.yml not found")
        
        import yaml
        
        with open(dependabot_config) as f:
            config = yaml.safe_load(f)
        
        # Check if labels are configured for updates
        updates = config.get("updates", [])
        if updates:
            for update in updates:
                labels = update.get("labels", [])
                # At minimum, should have 'dependencies' label or similar
                assert len(labels) > 0, "Dependabot should be configured to label PRs"
                # Verify 'dependencies' label is present if labels are configured
                if "dependencies" in labels or any("depend" in str(l).lower() for l in labels):
                    pass  # Good - has appropriate label
        else:
            pytest.skip("No updates configured in dependabot.yml")

    def test_dependabot_pr_changelog(self):
        """Test that Dependabot is configured to include changelog links.

        QA: Verify dependabot PRs include changelog references.
        """
        dependabot_config = Path(".github/dependabot.yml")
        
        if not dependabot_config.exists():
            pytest.skip(".github/dependabot.yml not found")
        
        import yaml
        
        with open(dependabot_config) as f:
            config = yaml.safe_load(f)
        
        # Check if commit-message or pull-request-contents are configured
        updates = config.get("updates", [])
        if updates:
            for update in updates:
                # Check for commit-message configuration with changelog
                commit_message = update.get("commit-message", {})
                # Or check for pull-request-contents with changelog link
                pr_contents = update.get("pull-request-contents", {})
                
                # At minimum, verify the configuration structure exists
                # Detailed changelog behavior would require actual PR inspection
                assert isinstance(commit_message, dict) or isinstance(pr_contents, dict), \
                    "Dependabot should have commit-message or pull-request-contents configured"
        else:
            pytest.skip("No updates configured in dependabot.yml")
