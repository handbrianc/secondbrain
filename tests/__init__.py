"""Tests for config module."""

import os
from pathlib import Path

import pytest

from secondbrain.config import Config, get_config


def test_config_default_values(tmp_path: Path) -> None:
    """Test configuration default values.

    Isolates ambient configuration state the same way
    ``tests/config/conftest.py`` does (pattern replicated locally, not
    imported): strips every ``SECONDBRAIN_*`` variable — the repo's committed
    ``.env`` / ``.env.test`` would otherwise leak into the values under test
    (e.g. ``SECONDBRAIN_QDRANT_URL=http://localhost:6334``) — moves to an
    empty cwd so ``Config._load_env_file`` cannot implicitly load the repo
    dotenv files, and clears the ``get_config`` lru_cache before and after
    (config values are cached process-wide and would otherwise leak between
    tests).
    """
    original = os.environ.copy()
    try:
        for key in [k for k in original if k.upper().startswith("SECONDBRAIN_")]:
            del os.environ[key]

        # Empty cwd: no repo .env/.env.test is implicitly loaded.
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            get_config.cache_clear()
            config = Config()
            assert config.qdrant_url == "http://localhost:6333"
            assert config.qdrant_collection == "embeddings"
            assert config.storage_backend == "qdrant"
            assert config.chunk_size == 4096
            assert config.chunk_overlap == 50
            assert config.default_top_k == 50
        finally:
            os.chdir(old_cwd)
    finally:
        # The dotenv loader mutates os.environ; undo everything.
        os.environ.clear()
        os.environ.update(original)
        get_config.cache_clear()


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
