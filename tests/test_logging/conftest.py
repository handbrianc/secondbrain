"""Shared fixtures for the logging tests.

The default rotating file log writes under the user's application data
directory, so every test here runs with HOME redirected into tmp_path — no
test may ever touch the real ``~/.secondbrain``.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect HOME into tmp_path and clear the log-destination env vars.

    Returns
    -------
        The isolated home directory the test's default log lands in.
    """
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SECONDBRAIN_LOG_FILE", raising=False)
    monkeypatch.delenv("SECONDBRAIN_LOG_DISABLE_FILE", raising=False)
    return home
