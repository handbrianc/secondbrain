"""Fixtures for the config test directory.

Isolates each test from ambient configuration state:

- removes every ``SECONDBRAIN_*`` environment variable (the repo's committed
  ``.env`` / ``.env.test`` would otherwise leak into the values under test);
- changes the working directory to an empty tmp dir so ``Config`` cannot
  implicitly load the repo's dotenv files (``Config._load_env_file`` scans the
  CWD for ``.env.test`` / ``.env``); tests that exercise dotenv loading write
  their own file into ``tmp_path``;
- restores the full environment afterwards — necessary because the dotenv
  loader **mutates ``os.environ``** with values read from the file;
- clears the ``get_config`` lru_cache before and after (config values are
  cached process-wide and would otherwise leak between tests).
"""

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Run each config test with a clean env, empty cwd, and a fresh cache."""
    from secondbrain.config import get_config

    get_config.cache_clear()

    original = os.environ.copy()
    for key in [k for k in original if k.upper().startswith("SECONDBRAIN_")]:
        del os.environ[key]

    # Empty cwd: no repo .env/.env.test is implicitly loaded.
    monkeypatch.chdir(tmp_path)

    yield

    # The dotenv loader writes values into os.environ; undo everything.
    os.environ.clear()
    os.environ.update(original)
    get_config.cache_clear()
