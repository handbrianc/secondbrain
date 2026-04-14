"""Root pytest fixtures for all tests."""

import os
from unittest.mock import patch

import pytest


# Set test environment variables before tests run
def pytest_configure(config: pytest.Config) -> None:
    """Set test environment variables before tests run.

    This ensures all tests use the correct test service URLs
    (ports 27018 and 11435) instead of production ports.
    """
    # Set test MongoDB URI with authentication (authSource=admin for root user)
    if "SECONDBRAIN_MONGO_URI" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_URI"] = (
            "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
        )

    # Set test Ollama host
    if "SECONDBRAIN_OLLAMA_HOST" not in os.environ:
        os.environ["SECONDBRAIN_OLLAMA_HOST"] = "http://localhost:11435"

    # Set test database and collection
    if "SECONDBRAIN_MONGO_DB" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_DB"] = "secondbrain_test"

    if "SECONDBRAIN_MONGO_COLLECTION" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_COLLECTION"] = "test_embeddings"


# Auto-mock DockerManager for all tests to prevent MongoDB startup
# Integration tests that need real MongoDB will patch it back or use real setup
original_patch = patch("secondbrain.utils.docker_manager.DockerManager")
mock_manager = None


@pytest.fixture(autouse=True, scope="function")
def _mock_docker_manager():
    """Automatically mock DockerManager to prevent MongoDB startup."""
    global mock_manager
    if mock_manager is None:
        mock_manager = original_patch.start()
    yield
    # No cleanup needed - patch is persistent
