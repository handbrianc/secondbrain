"""Tests for config module."""

import os

import pytest

from secondbrain.config import Config, get_config


def test_config_default_values() -> None:
    """Test configuration default values."""
    # Set environment variables to test defaults aren't picked up
    env_backup = os.environ.copy()
    try:
        # Clear all SECONDBRAIN env vars
        for key in list(os.environ.keys()):
            if key.startswith("SECONDBRAIN_"):
                del os.environ[key]

        config = Config()
        assert config.mongo_uri == "mongodb://localhost:27017"
        assert config.mongo_db == "secondbrain"
        assert config.mongo_collection == "embeddings"
        assert config.model == "embeddinggemma:latest"
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.default_top_k == 5
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration from environment variables."""
    monkeypatch.setenv("SECONDBRAIN_MONGO_URI", "mongodb://custom:27017")
    monkeypatch.setenv("SECONDBRAIN_MONGO_DB", "custom_db")
    monkeypatch.setenv("SECONDBRAIN_MONGO_COLLECTION", "custom_collection")
    monkeypatch.setenv("SECONDBRAIN_MODEL", "custom-model:latest")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "1024")
    monkeypatch.setenv("SECONDBRAIN_CHUNK_OVERLAP", "100")
    monkeypatch.setenv("SECONDBRAIN_DEFAULT_TOP_K", "10")

    config = Config()
    assert config.mongo_uri == "mongodb://custom:27017"
    assert config.mongo_db == "custom_db"
    assert config.mongo_collection == "custom_collection"
    assert config.model == "custom-model:latest"
    assert config.chunk_size == 1024
    assert config.chunk_overlap == 100
    assert config.default_top_k == 10


def test_get_config_cached() -> None:
    """Test that get_config returns cached instance."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2
