"""Tests for the default rotating file log in ``setup_logging``.

Spec (service-observability, Default rotating file log): a CLI run without
environment configuration attaches a size-rotating file log under the user's
application data directory; ``SECONDBRAIN_LOG_FILE`` overrides the
destination, ``SECONDBRAIN_LOG_DISABLE_FILE`` suppresses file logging
entirely, and console behavior is unchanged. Tests run with HOME redirected
into tmp_path (conftest fixture) so the real ``~/.secondbrain`` is never
touched.
"""

import json
import logging
import logging.handlers
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from rich.logging import RichHandler

from secondbrain.logging import get_logger, setup_logging

DEFAULT_LOG_RELATIVE = Path(".secondbrain") / "logs" / "secondbrain.log"


@pytest.fixture(autouse=True)
def restore_root_handlers() -> Iterator[None]:
    """Restore root handlers so tmp-path file handlers don't survive the test."""
    root_logger = logging.getLogger()
    snapshot = list(root_logger.handlers)
    yield
    root_logger.handlers = snapshot


def _fresh_root() -> logging.Logger:
    """Clear root handlers inside the test body.

    Pytest's logging plugin re-attaches capture handlers between fixture
    setup and the test, and ``setup_logging`` defers to pre-configured root
    handlers, so the clear must happen in the body (same pattern as the
    neighboring ``TestFileLogging`` tests).
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    return root_logger


def _file_handler() -> logging.handlers.RotatingFileHandler:
    file_handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    return file_handlers[0]


class TestDefaultFileLog:
    def test_default_on_creates_and_writes_file(self, isolated_home: Path) -> None:
        """Default (no env config): handler attaches at the default path."""
        _fresh_root()
        setup_logging(verbose=True)

        handler = _file_handler()
        expected = isolated_home / DEFAULT_LOG_RELATIVE
        assert Path(handler.baseFilename) == expected
        assert expected.parent.is_dir()

        get_logger("default_log_test").info("hello default log")
        assert "hello default log" in expected.read_text()

    def test_default_on_keeps_console_handler(self, isolated_home: Path) -> None:
        """Console behavior unchanged: rich handler + file handler, nothing else."""
        root_logger = _fresh_root()
        setup_logging(verbose=True)

        assert len(root_logger.handlers) == 2
        assert any(isinstance(h, RichHandler) for h in root_logger.handlers)

    def test_default_rotation_parameters(self, isolated_home: Path) -> None:
        """10 MB per file, 5 backups retained."""
        _fresh_root()
        setup_logging(verbose=True)

        handler = _file_handler()
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5

    def test_default_on_json_format_writes_json(self, isolated_home: Path) -> None:
        _fresh_root()
        setup_logging(verbose=True, json_format=True)

        handler = _file_handler()
        get_logger("default_log_json").info("json default message")
        content = Path(handler.baseFilename).read_text().strip()
        assert json.loads(content)["message"] == "json default message"

    def test_default_log_dir_created_when_missing(self, isolated_home: Path) -> None:
        """A fresh environment (no log directory yet) gets one on first run."""
        assert not (isolated_home / ".secondbrain").exists()
        _fresh_root()
        setup_logging(verbose=True)
        assert (isolated_home / DEFAULT_LOG_RELATIVE).parent.is_dir()


class TestDefaultFileLogCarriesSlowCallWarning:
    def test_slow_call_warning_lands_in_default_file_log(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec scenario: the default file log carries the slow-call WARNING."""
        from secondbrain.logging import timed_external_call

        monkeypatch.setenv("SECONDBRAIN_SLOW_CALL_SECONDS", "0.01")
        _fresh_root()
        setup_logging(verbose=False)

        with timed_external_call("llm.generate", "gpt-4o-mini"):
            time.sleep(0.05)

        content = (isolated_home / DEFAULT_LOG_RELATIVE).read_text()
        assert "Slow external call" in content
        assert "operation=llm.generate" in content
        assert "target=gpt-4o-mini" in content


class TestFileDestinationOverride:
    def test_env_var_overrides_destination(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        override = isolated_home / "override.log"
        monkeypatch.setenv("SECONDBRAIN_LOG_FILE", str(override))

        _fresh_root()
        setup_logging(verbose=True)

        handler = _file_handler()
        assert Path(handler.baseFilename) == override
        assert override.exists()
        assert not (isolated_home / DEFAULT_LOG_RELATIVE).exists()

    def test_explicit_argument_still_wins(
        self, isolated_home: Path, tmp_path: Path
    ) -> None:
        explicit = tmp_path / "explicit.log"

        _fresh_root()
        setup_logging(verbose=True, log_file=str(explicit))

        assert Path(_file_handler().baseFilename) == explicit
        assert not (isolated_home / DEFAULT_LOG_RELATIVE).exists()


class TestDisableSwitch:
    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_disable_env_suppresses_file_logging(
        self,
        isolated_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_LOG_DISABLE_FILE", value)

        root_logger = _fresh_root()
        setup_logging(verbose=True)

        assert not any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root_logger.handlers
        )
        assert not (isolated_home / DEFAULT_LOG_RELATIVE).exists()

    def test_disable_env_wins_over_log_file_env(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_LOG_FILE", str(isolated_home / "env.log"))
        monkeypatch.setenv("SECONDBRAIN_LOG_DISABLE_FILE", "1")

        root_logger = _fresh_root()
        setup_logging(verbose=True)

        assert not any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root_logger.handlers
        )
        assert not (isolated_home / "env.log").exists()

    def test_disable_env_wins_over_log_file_argument(
        self, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        explicit = tmp_path / "explicit.log"
        monkeypatch.setenv("SECONDBRAIN_LOG_DISABLE_FILE", "1")

        root_logger = _fresh_root()
        setup_logging(verbose=True, log_file=str(explicit))

        assert not explicit.exists()
        assert not any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root_logger.handlers
        )

    def test_non_truthy_disable_values_do_not_disable(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_LOG_DISABLE_FILE", "0")

        _fresh_root()
        setup_logging(verbose=True)

        assert Path(_file_handler().baseFilename) == (
            isolated_home / DEFAULT_LOG_RELATIVE
        )


class TestRotationEnvStillHonored:
    def test_max_bytes_env_override(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_LOG_MAX_BYTES", "2048")

        _fresh_root()
        setup_logging(verbose=True)

        assert _file_handler().maxBytes == 2048

    def test_backup_count_env_override(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_LOG_BACKUP_COUNT", "2")

        _fresh_root()
        setup_logging(verbose=True)

        assert _file_handler().backupCount == 2
