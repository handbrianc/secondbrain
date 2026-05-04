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
            expected_uri = "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
            assert config.mongo_uri == expected_uri
            assert config.mongo_db == "secondbrain_test"
            assert config.mongo_collection == "embeddings_test"
            assert config.local_embedding_model == "all-MiniLM-L6-v2"
            assert config.chunk_size == 4096
            assert config.chunk_overlap == 50
            assert config.default_top_k == 20
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration from environment variables."""
    monkeypatch.setenv("SECONDBRAIN_MONGO_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("SECONDBRAIN_MONGO_DB", "custom_db")
    monkeypatch.setenv("SECONDBRAIN_MONGO_COLLECTION", "custom_collection")
    monkeypatch.setenv("SECONDBRAIN_LOCAL_EMBEDDING_MODEL", "custom-model:latest")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "1024")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_OVERLAP", "100")
    monkeypatch.setenv("SECONDBRAIN_DEFAULT_TOP_K", "10")

    # Clear cache to pick up new env vars
    get_config.cache_clear()
    config = Config()
    assert config.mongo_uri == "mongodb://localhost:27017"
    assert config.mongo_db == "custom_db"
    assert config.mongo_collection == "custom_collection"
    assert config.local_embedding_model == "custom-model:latest"
    assert config.chunk_size == 1024
    assert config.chunk_overlap == 100
    assert config.default_top_k == 10


def test_get_config_cached() -> None:
    """Test that get_config returns cached instance."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2
