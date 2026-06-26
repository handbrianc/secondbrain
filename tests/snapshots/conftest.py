"""Fixtures for loading RAG pipeline snapshot fixtures."""

from pathlib import Path
from typing import Any

import pytest

SNAPSHOT_DIR = Path(__file__).parent


@pytest.fixture
def snapshot_dir() -> Path:
    """Return the path to the snapshots directory."""
    return SNAPSHOT_DIR


@pytest.fixture
def sample_chunks() -> list[dict[str, Any]]:
    """Load sample chunks from context_assembly snapshot.

    These represent the raw检索 results from Searcher.search().
    """
    import json

    with open(SNAPSHOT_DIR / "context_assembly.json") as f:
        data = json.load(f)
    return data["chunks"]


@pytest.fixture
def expected_formatted_context() -> str:
    """Load expected formatted context string.

    This is what _format_context() should produce from sample_chunks.
    """
    import json

    with open(SNAPSHOT_DIR / "context_assembly.json") as f:
        data = json.load(f)
    return data["expected_formatted_context"]


@pytest.fixture
def sample_query() -> str:
    """Load the sample user query for prompt assembly."""
    import json

    with open(SNAPSHOT_DIR / "sample_query.json") as f:
        data = json.load(f)
    return data["query"]


@pytest.fixture
def expected_assembled_prompt() -> str:
    """Load the expected golden prompt string.

    This is the full prompt that should be passed to the LLM,
    as produced by _build_prompt() with the sample inputs.
    """
    with open(SNAPSHOT_DIR / "assembled_prompt.txt") as f:
        return f.read()


@pytest.fixture
def sample_top_k() -> int:
    """Load the sample top_k parameter."""
    import json

    with open(SNAPSHOT_DIR / "sample_query.json") as f:
        data = json.load(f)
    return data["top_k"]
