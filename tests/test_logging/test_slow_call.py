"""Unit tests for the slow external-call instrumentation.

Spec (service-observability, Slow-call WARNING logging): a call exceeding the
slow-call threshold emits exactly one WARNING naming the operation, target
and elapsed time; a call within the threshold emits nothing. The threshold
defaults to 10 s, is overridable via SECONDBRAIN_SLOW_CALL_SECONDS read at
call time, and malformed values fall back to the default.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from secondbrain.logging import timed_external_call
from secondbrain.logging.slow_call import (
    DEFAULT_SLOW_CALL_SECONDS,
    SLOW_CALL_SECONDS_ENV,
    _slow_call_threshold,
)

SLOW_CALL_LOGGER = "secondbrain.logging.slow_call"


@pytest.fixture(autouse=True)
def clean_threshold_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from the documented 10 s default threshold."""
    monkeypatch.delenv(SLOW_CALL_SECONDS_ENV, raising=False)


class TestSlowCallThreshold:
    def test_default_threshold_when_env_unset(self) -> None:
        assert _slow_call_threshold() == DEFAULT_SLOW_CALL_SECONDS == 10.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.5", 0.5),
            ("2", 2.0),
            ("  1.5  ", 1.5),
        ],
    )
    def test_env_override_parsed(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
    ) -> None:
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, raw)
        assert _slow_call_threshold() == expected

    @pytest.mark.parametrize(
        "raw",
        ["abc", "", "   ", "nan", "inf", "-1", "0", "1e-999", "10s"],
    )
    def test_malformed_env_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        """Malformed values (non-numeric, empty, non-finite, non-positive)."""
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, raw)
        assert _slow_call_threshold() == DEFAULT_SLOW_CALL_SECONDS

    def test_env_read_at_call_time(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A threshold change between two calls takes effect immediately."""
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "1000")
        with caplog.at_level(logging.WARNING):
            with timed_external_call("op", "target"):
                pass
        assert not caplog.records

        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "0.001")
        with caplog.at_level(logging.WARNING):
            with timed_external_call("op", "target"):
                time.sleep(0.01)
        assert len(caplog.records) == 1


class TestSlowCallBehavior:
    def test_within_threshold_emits_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            with timed_external_call("llm.generate", "gpt-4o-mini"):
                pass
        assert not caplog.records

    def test_over_threshold_emits_one_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "0.01")

        with caplog.at_level(logging.WARNING):
            with timed_external_call("llm.generate", "gpt-4o-mini"):
                time.sleep(0.05)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.WARNING
        assert record.name == SLOW_CALL_LOGGER
        message = record.getMessage()
        assert "operation=llm.generate" in message
        assert "target=gpt-4o-mini" in message
        assert "elapsed=" in message
        assert "threshold=0.010s" in message

    def test_slow_call_that_raises_still_warns_and_propagates(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "0.01")

        with caplog.at_level(logging.WARNING):
            with (
                pytest.raises(ValueError, match="boom"),
                timed_external_call("embedding.generate", "m"),
            ):
                time.sleep(0.05)
                raise ValueError("boom")

        assert len(caplog.records) == 1
        assert "operation=embedding.generate" in caplog.records[0].getMessage()

    def test_fast_failure_within_threshold_is_silent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "1000")

        with caplog.at_level(logging.WARNING):
            with (
                pytest.raises(ValueError, match="boom"),
                timed_external_call("embedding.generate", "m"),
            ):
                raise ValueError("boom")

        assert not caplog.records

    def test_emits_when_root_is_configured_to_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The logger gate never suppresses the record (level-independent).

        The slow-call logger carries its own WARNING level, so a quiet root
        (ERROR) does not gate the record out. (Per-transport handler levels
        remain authoritative for what each transport prints.)
        """
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "0.001")
        root_logger = logging.getLogger()
        previous = root_logger.level
        root_logger.setLevel(logging.ERROR)
        try:
            with caplog.at_level(logging.WARNING, logger=SLOW_CALL_LOGGER):
                with timed_external_call("llm.generate", "m"):
                    time.sleep(0.01)
        finally:
            root_logger.setLevel(previous)

        records = [r for r in caplog.records if r.name == SLOW_CALL_LOGGER]
        assert len(records) == 1

    def test_thread_safety_all_calls_reported(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Concurrent slow calls each emit their own warning; none is lost."""
        monkeypatch.setenv(SLOW_CALL_SECONDS_ENV, "0.001")

        def one_call(index: int) -> None:
            with timed_external_call("qdrant.search", f"collection-{index}"):
                time.sleep(0.01)

        with caplog.at_level(logging.WARNING):
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(one_call, range(8)))

        records = [r for r in caplog.records if r.name == SLOW_CALL_LOGGER]
        assert len(records) == 8
        for i in range(8):
            assert any(f"target=collection-{i}" in r.getMessage() for r in records)
