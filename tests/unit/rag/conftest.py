"""Shared fixtures for the rag pipeline unit tests.

The structure store (``add-structure-aware-ingestion``) defaults to the
shared conversation database (``cfg.sqlite_path``) — a live file outside the
test environment.  Every test in this directory therefore sees an empty
per-test store unless it injects its own explicit ``StructureStore``, so tree
lookups never touch (or create rows in) the real database and treeless
characterization runs deterministically take the legacy chapter path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from secondbrain.config import config


@pytest.fixture(autouse=True)
def _isolate_structure_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the structure store at an empty, per-test SQLite file.

    Args:
        tmp_path: The per-test temporary directory.
        monkeypatch: pytest helper restoring the config after the test.
    """
    cfg = config()
    monkeypatch.setattr(cfg, "sqlite_path", str(tmp_path / "structures-test.db"))
