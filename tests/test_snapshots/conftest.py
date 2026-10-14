"""Fixtures for the golden-file snapshot tests.

``tests/snapshots/`` holds the golden files (sample inputs + expected
outputs) and an orphaned loader conftest whose fixtures never reach a
consuming test subtree (pytest conftest fixtures do not cross sibling
directories), so the loaders are re-declared here for the tests in this
package.
"""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"


@pytest.fixture
def snapshot_dir() -> Path:
    """Return the path to the snapshots directory."""
    return SNAPSHOT_DIR


@pytest.fixture
def sample_chunks() -> list[dict[str, Any]]:
    """Raw retrieval results (Searcher.search() output shape) for the golden run."""
    data: dict[str, Any] = json.loads(
        (SNAPSHOT_DIR / "context_assembly.json").read_text()
    )
    chunks: list[dict[str, Any]] = data["chunks"]
    return chunks


@pytest.fixture
def expected_formatted_context() -> str:
    """Golden output of ``RAGPipeline._format_context()`` over sample_chunks."""
    data: dict[str, Any] = json.loads(
        (SNAPSHOT_DIR / "context_assembly.json").read_text()
    )
    golden: str = data["expected_formatted_context"]
    return golden


@pytest.fixture
def sample_query() -> str:
    """Sample user query driving prompt assembly."""
    data: dict[str, Any] = json.loads((SNAPSHOT_DIR / "sample_query.json").read_text())
    query: str = data["query"]
    return query


@pytest.fixture
def sample_top_k() -> int:
    """Sample top_k parameter for prompt assembly."""
    data: dict[str, Any] = json.loads((SNAPSHOT_DIR / "sample_query.json").read_text())
    top_k: int = data["top_k"]
    return top_k


@pytest.fixture
def expected_assembled_prompt() -> str:
    """Golden output of ``RAGPipeline._build_prompt()`` for the sample inputs."""
    return (SNAPSHOT_DIR / "assembled_prompt.txt").read_text()


@pytest.fixture
def clean_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Yield a defaults-only Config with ambient configuration state excluded.

    Mirrors ``tests/config/conftest.py``: strips every ``SECONDBRAIN_*``
    variable (the repo's committed ``.env`` / ``.env.test`` would otherwise
    leak into the values under test), switches to an empty cwd so
    ``Config._load_env_file`` cannot implicitly load the repo dotenv files,
    and clears the ``get_config`` lru_cache before and after (the dotenv
    loader mutates ``os.environ``, and cached values would otherwise leak
    between tests).
    """
    from secondbrain.config import get_config

    get_config.cache_clear()

    original = dict(os.environ)
    for key in [k for k in original if k.upper().startswith("SECONDBRAIN_")]:
        del os.environ[key]

    # Empty cwd: no repo .env/.env.test is implicitly loaded.
    monkeypatch.chdir(tmp_path)

    yield get_config()

    # The dotenv loader writes values into os.environ; undo everything.
    os.environ.clear()
    os.environ.update(original)
    get_config.cache_clear()


@pytest.fixture
def snapshot_pipeline(clean_config_env: Any, sample_top_k: int) -> Any:
    """RAGPipeline over inert doubles, bound to the isolated defaults-only config.

    The snapshot tests only exercise ``_format_context``/``_build_prompt``,
    so the searcher and LLM provider are MagicMocks (never called); the
    pipeline just needs a real Config for the system prompt and the
    formatting limits. The identity assert pins that the prompt is built
    from the same defaults-only config the golden files were generated with.
    """
    from secondbrain.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline(
        searcher=MagicMock(),
        llm_provider=MagicMock(),
        top_k=sample_top_k,
    )
    assert pipeline._config is clean_config_env
    return pipeline
