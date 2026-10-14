"""Tests for environment-variable and dotenv precedence in Config.

The real mechanism (src/secondbrain/config/__init__.py):

- ``Config`` is a pydantic-settings ``BaseSettings`` with
  ``env_prefix="SECONDBRAIN_"`` and ``case_sensitive=False``.
- A ``mode="before"`` model validator loads ``.env.test`` (when pytest is
  running) or ``.env`` **from the current working directory**, injecting
  values into ``os.environ`` when neither an explicit kwarg nor a real
  environment variable provides the key.
- Effective precedence: explicit kwargs > real env vars > dotenv file > field
  defaults. Unknown ``SECONDBRAIN_*`` keys are ignored (``extra="ignore"``).

Tests run inside the ``isolate_config_env`` fixture (tests/config/conftest.py):
no ``SECONDBRAIN_*`` env vars, empty cwd, fresh ``get_config`` cache.
"""

import os
from pathlib import Path

import pytest

from secondbrain.config import Config, get_config


class TestDefaultsWithoutDotenv:
    """Pure field defaults: no env vars and no dotenv file in cwd."""

    def test_defaults_when_no_env_and_no_dotenv(self):
        config = Config()

        assert config.chunk_size == 4096
        assert config.chunk_overlap == 50
        assert config.default_top_k == 50
        assert config.qdrant_url == "http://localhost:6333"
        assert config.qdrant_collection == "embeddings"
        assert config.storage_backend == "qdrant"
        assert config.sqlite_path == str(
            Path("~/.secondbrain/secondbrain.db").expanduser()
        )

    def test_defaults_survive_cwd_without_dotenv(self, tmp_path, monkeypatch):
        """A cwd without .env/.env.test must not inject any values."""
        empty_dir = tmp_path / "nowhere"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        config = Config()

        assert config.qdrant_url == "http://localhost:6333"
        assert config.chunk_size == 4096


class TestEnvVarPrecedence:
    """SECONDBRAIN_* environment variables override field defaults."""

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "1024")

        config = Config()

        assert config.chunk_size == 1024

    def test_multiple_env_vars_override_defaults(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_QDRANT_URL", "http://localhost:27019")
        monkeypatch.setenv("SECONDBRAIN_QDRANT_COLLECTION", "custom_collection")
        monkeypatch.setenv("SECONDBRAIN_CHUNK_OVERLAP", "100")
        monkeypatch.setenv("SECONDBRAIN_DEFAULT_TOP_K", "10")

        config = Config()

        assert config.qdrant_url == "http://localhost:27019"
        assert config.qdrant_collection == "custom_collection"
        assert config.chunk_overlap == 100
        assert config.default_top_k == 10

    def test_env_var_names_are_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("secondbrain_chunk_size", "555")

        config = Config()

        assert config.chunk_size == 555

    def test_unknown_env_vars_are_ignored(self, monkeypatch):
        """extra='ignore': unknown SECONDBRAIN_* keys must not raise."""
        monkeypatch.setenv("SECONDBRAIN_NOT_A_REAL_FIELD", "whatever")

        config = Config()  # must not raise

        assert config.chunk_size == 4096

    def test_bool_env_var_parsing(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_RATE_LIMIT_ENABLED", "true")
        assert Config().rate_limit_enabled is True

        monkeypatch.setenv("SECONDBRAIN_RATE_LIMIT_ENABLED", "false")
        assert Config().rate_limit_enabled is False

    def test_get_config_reads_current_env(self, monkeypatch):
        """get_config() reflects env vars set since the last cache clear."""
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "2048")

        config = get_config()

        assert config.chunk_size == 2048


class TestKwargsBeatEnv:
    """Explicit constructor kwargs have the highest priority."""

    def test_kwarg_beats_env_var(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "999")

        config = Config(chunk_size=123)

        assert config.chunk_size == 123

    def test_env_var_fills_fields_without_kwargs(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "999")

        config = Config(chunk_overlap=10)

        assert config.chunk_size == 999  # from env
        assert config.chunk_overlap == 10  # from kwarg


class TestDotenvLoading:
    """.env / .env.test loading from the current working directory."""

    def test_env_file_loaded_when_no_env_var(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("SECONDBRAIN_CHUNK_SIZE=777\n")
        monkeypatch.chdir(tmp_path)

        config = Config()

        assert config.chunk_size == 777

    def test_real_env_var_beats_dotenv(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("SECONDBRAIN_CHUNK_SIZE=777\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "999")

        config = Config()

        assert config.chunk_size == 999

    def test_explicit_kwarg_beats_dotenv(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("SECONDBRAIN_CHUNK_SIZE=777\n")
        monkeypatch.chdir(tmp_path)

        config = Config(chunk_size=123)

        assert config.chunk_size == 123

    def test_dotenv_strips_quotes(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text(
            'SECONDBRAIN_QDRANT_COLLECTION="my collection"\n'
            "SECONDBRAIN_STORAGE_BACKEND='mock'\n"
        )
        monkeypatch.chdir(tmp_path)

        config = Config()

        assert config.qdrant_collection == "my collection"
        assert config.storage_backend == "mock"

    def test_dotenv_skips_comments_and_blank_lines(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text(
            "# a comment line\n\nSECONDBRAIN_CHUNK_SIZE=321\n"
        )
        monkeypatch.chdir(tmp_path)

        config = Config()

        assert config.chunk_size == 321

    def test_dotenv_test_preferred_over_dotenv_under_pytest(
        self, tmp_path, monkeypatch
    ):
        """With PYTEST_CURRENT_TEST set, .env.test wins over .env."""
        assert os.environ.get("PYTEST_CURRENT_TEST") is not None

        (tmp_path / ".env").write_text("SECONDBRAIN_CHUNK_SIZE=111\n")
        (tmp_path / ".env.test").write_text("SECONDBRAIN_CHUNK_SIZE=222\n")
        monkeypatch.chdir(tmp_path)

        config = Config()

        assert config.chunk_size == 222

    def test_dotenv_loader_injects_into_os_environ(self, tmp_path, monkeypatch):
        """The loader writes file values into os.environ for downstream readers."""
        (tmp_path / ".env").write_text("SECONDBRAIN_CHUNK_SIZE=777\n")
        monkeypatch.chdir(tmp_path)

        Config()

        assert os.environ.get("SECONDBRAIN_CHUNK_SIZE") == "777"

    def test_missing_dotenv_files_load_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no .env / .env.test here

        config = Config()

        assert config.chunk_size == 4096  # field default

    def test_dotenv_with_unparseable_lines_is_tolerated(self, tmp_path, monkeypatch):
        """Lines without '=' and empty lines are skipped, not fatal."""
        (tmp_path / ".env").write_text(
            "this line has no equals sign\n\nSECONDBRAIN_CHUNK_SIZE=64\n"
        )
        monkeypatch.chdir(tmp_path)

        config = Config()

        assert config.chunk_size == 64

    def test_dotenv_line_with_empty_key_is_fatal(self, tmp_path, monkeypatch):
        """A '=value' line crashes the loader (os.environ[''] is invalid).

        Documents the current behavior: the loader partitions on '=' without
        validating that the key is non-empty.
        """
        (tmp_path / ".env").write_text("=novalue\n")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(OSError):
            Config()


class TestTestEnvDefaults:
    """Under pytest, Config injects test-specific defaults for unset keys."""

    def test_rate_limit_disabled_by_default_under_pytest(self):
        config = Config()

        assert config.rate_limit_enabled is False

    def test_explicit_rate_limit_beats_test_default(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_RATE_LIMIT_ENABLED", "true")

        config = Config()

        assert config.rate_limit_enabled is True


class TestGetConfigCaching:
    """get_config() is an lru_cache singleton keyed on nothing."""

    def test_get_config_returns_cached_instance(self):
        first = get_config()
        second = get_config()

        assert first is second

    def test_cache_clear_picks_up_new_env(self, monkeypatch):
        first = get_config()
        assert first.chunk_size == 4096

        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "2048")
        get_config.cache_clear()
        second = get_config()

        assert second is not first
        assert second.chunk_size == 2048
