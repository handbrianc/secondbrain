"""Unit tests for the pipeline stage-timing instrumentation.

Spec (openspec fix-chat-session-integrity, Audio ingest stage observability):
a completed stage emits exactly one record — INFO naming the stage, context
and elapsed time on success, WARNING instead when the stage exceeds the
slow-stage threshold — and a failing stage logs the stage, elapsed time and
error before re-raising. The threshold defaults to 60 s, is overridable via
``SECONDBRAIN_SLOW_STAGE_SECONDS`` read at call time, and malformed values
fall back to the default.
"""

import logging
import re
import time

import pytest

from secondbrain.logging import timed_stage
from secondbrain.logging.stage_timing import (
    DEFAULT_SLOW_STAGE_SECONDS,
    SLOW_STAGE_SECONDS_ENV,
    _slow_stage_threshold,
)

STAGE_LOGGER = "secondbrain.logging.stage_timing"


def _stage_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == STAGE_LOGGER]


def _elapsed_seconds(message: str) -> float:
    match = re.search(r"elapsed=([0-9.]+)s", message)
    assert match is not None, message
    return float(match.group(1))


@pytest.fixture(autouse=True)
def clean_threshold_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from the documented 60 s default threshold."""
    monkeypatch.delenv(SLOW_STAGE_SECONDS_ENV, raising=False)


class TestSlowStageThreshold:
    def test_default_threshold_when_env_unset(self) -> None:
        assert _slow_stage_threshold() == DEFAULT_SLOW_STAGE_SECONDS == 60.0

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
        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, raw)
        assert _slow_stage_threshold() == expected

    @pytest.mark.parametrize(
        "raw",
        ["abc", "", "   ", "nan", "inf", "-1", "0", "1e-999", "10s"],
    )
    def test_malformed_env_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        """Malformed values (non-numeric, empty, non-finite, non-positive)."""
        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, raw)
        assert _slow_stage_threshold() == DEFAULT_SLOW_STAGE_SECONDS

    def test_env_read_at_call_time(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A threshold change between two stages takes effect immediately."""
        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, "1000")
        with caplog.at_level(logging.INFO):
            with timed_stage("chunk", context="doc.pdf"):
                pass
        assert _stage_records(caplog)[0].levelno == logging.INFO

        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, "0.001")
        with caplog.at_level(logging.INFO):
            with timed_stage("chunk", context="doc.pdf"):
                time.sleep(0.01)
        assert _stage_records(caplog)[-1].levelno == logging.WARNING


class TestTimedStageSuccess:
    def test_success_emits_single_info_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO):
            with timed_stage("audio.transcription", context="/media/clip.wav"):
                pass

        records = _stage_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.INFO
        message = record.getMessage()
        assert "stage=audio.transcription" in message
        assert "context=/media/clip.wav" in message
        assert 0.0 <= _elapsed_seconds(message) < 1.0

    def test_started_at_anchor_measures_from_anchor(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The elapsed time is measured from the given monotonic anchor."""
        anchor = time.monotonic() - 2.0

        with caplog.at_level(logging.INFO):
            with timed_stage("chunk", context="doc.pdf", started_at=anchor):
                pass

        message = _stage_records(caplog)[0].getMessage()
        elapsed = _elapsed_seconds(message)
        assert 1.9 <= elapsed <= 5.0

    def test_over_threshold_warns_with_stage_context_threshold(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, "0.01")

        with caplog.at_level(logging.INFO):
            with timed_stage("audio.transcription", context="clip.wav"):
                time.sleep(0.05)

        records = _stage_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        message = record.getMessage()
        assert "Slow pipeline stage" in message
        assert "stage=audio.transcription" in message
        assert "context=clip.wav" in message
        assert "threshold=0.010s" in message
        assert _elapsed_seconds(message) >= 0.04

    def test_failure_warning_needs_no_slow_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A fast stage whose body raises still logs its failure."""
        with caplog.at_level(logging.INFO):
            with (
                pytest.raises(RuntimeError, match="boom"),
                timed_stage("embed", context="clip.wav"),
            ):
                raise RuntimeError("boom")

        records = _stage_records(caplog)
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert "stage=embed" in records[0].getMessage()


class TestTimedStageFailure:
    def test_exception_logs_stage_elapsed_error_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(SLOW_STAGE_SECONDS_ENV, "0.01")
        error = ValueError("boom")

        with caplog.at_level(logging.INFO):
            with (
                pytest.raises(ValueError, match="boom") as raised,
                timed_stage(
                    "audio.topic_segmentation", context="clip.wav", started_at=None
                ),
            ):
                time.sleep(0.05)
                raise error

        assert raised.value is error
        records = _stage_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        message = record.getMessage()
        assert "Pipeline stage failed" in message
        assert "stage=audio.topic_segmentation" in message
        assert "context=clip.wav" in message
        assert "error=ValueError: boom" in message
        assert _elapsed_seconds(message) >= 0.04

    def test_exception_elapsed_uses_anchor(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        anchor = time.monotonic() - 3.0

        with caplog.at_level(logging.INFO):
            with (
                pytest.raises(RuntimeError, match="boom"),
                timed_stage(
                    "audio.transcription", context="clip.wav", started_at=anchor
                ),
            ):
                raise RuntimeError("boom")

        message = _stage_records(caplog)[0].getMessage()
        assert 2.9 <= _elapsed_seconds(message) <= 6.0
