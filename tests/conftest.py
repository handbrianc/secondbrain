"""Root pytest fixtures for all tests."""

from unittest.mock import patch

import pytest

# Auto-mock DockerManager for all tests to prevent Docker/MongoDB startup
# Integration tests that need real MongoDB will patch it back or use real setup
original_patch = patch("secondbrain.utils.docker_manager.DockerManager")
mock_manager = None


@pytest.fixture(autouse=True, scope="function")
def _mock_docker_manager():
    """Automatically mock DockerManager to prevent MongoDB timeouts."""
    global mock_manager
    if mock_manager is None:
        mock_manager = original_patch.start()
    yield
    # No cleanup needed - patch is persistent
