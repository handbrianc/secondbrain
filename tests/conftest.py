"""Pytest fixtures for secondbrain tests."""

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test data."""
    return tmp_path / "test_data"


@pytest.fixture
def mock_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock configuration for testing."""
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
        "SECONDBRAIN_MODEL": "embeddinggemma:latest",
        "SECONDBRAIN_CHUNK_SIZE": 512,
        "SECONDBRAIN_CHUNK_OVERLAP": 50,
        "SECONDBRAIN_DEFAULT_TOP_K": 5,
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))
    return test_config


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "This is a sample document. It contains multiple sentences. " * 10


@pytest.fixture
def sample_embedding() -> list[float]:
    """Sample embedding vector (384 dimensions)."""
    import random

    random.seed(42)
    return [random.random() for _ in range(384)]
