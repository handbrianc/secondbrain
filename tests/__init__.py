"""Tests for config module."""

import os
from unittest.mock import patch

import pytest

from secondbrain.config import Config, get_config


def test_config_default_values() -> None:
    """Test configuration default values."""
    env_backup = os.environ.copy()
    try:
        for key in list(os.environ.keys()):
            if key.startswith("SECONDBRAIN_"):
                del os.environ[key]

        pytest_current_test = os.environ.get("PYTEST_CURRENT_TEST")
        with patch.dict(os.environ, {}, clear=True):
            if pytest_current_test:
                os.environ["PYTEST_CURRENT_TEST"] = pytest_current_test
            get_config.cache_clear()
            config = Config()
            assert config.qdrant_url == "http://localhost:6333"
            assert config.qdrant_collection == "embeddings"
            assert config.storage_backend == "qdrant"
            assert config.chunk_size == 4096
            assert config.chunk_overlap == 50
            assert config.default_top_k == 20
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration from environment variables."""
    monkeypatch.setenv("SECONDBRAIN_QDRANT_URL", "http://localhost:27019")
    monkeypatch.setenv("SECONDBRAIN_QDRANT_COLLECTION", "custom_collection")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "1024")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_OVERLAP", "100")
    monkeypatch.setenv("SECONDBRAIN_DEFAULT_TOP_K", "10")

    # Clear cache to pick up new env vars
    get_config.cache_clear()
    config = Config()
    assert config.qdrant_url == "http://localhost:27019"
    assert config.qdrant_collection == "custom_collection"
    assert config.chunk_size == 1024
    assert config.chunk_overlap == 100
    assert config.default_top_k == 10


def test_get_config_cached() -> None:
    """Test that get_config returns cached instance."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2
