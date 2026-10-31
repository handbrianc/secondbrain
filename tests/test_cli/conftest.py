"""Shared fixtures for the CLI tests.

Every CLI invocation runs the group callback, which calls ``setup_logging``.
Since the default rotating file log writes under the user's application data
directory, all CLI tests run with HOME redirected into tmp_path — no test may
ever write the real ``~/.secondbrain``.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect HOME into tmp_path for the duration of each CLI test."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("SECONDBRAIN_LOG_FILE", raising=False)
    monkeypatch.delenv("SECONDBRAIN_LOG_DISABLE_FILE", raising=False)
