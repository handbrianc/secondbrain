"""Ingestor tests for stage timing and the derived transcription wait bound.

Spec (openspec fix-chat-session-integrity, D6/D7): audio ingest leaves a
per-stage timing trail (INFO on completion, WARNING past the slow-stage
threshold, WARNING on stage failure), the sync pool's worker-result wait is
stage-aware — text tasks keep the legacy 300 s bound while audio
transcription derives ``base + per-second * duration * windows`` (floored at
900 s) with an explicit ``SECONDBRAIN_TRANSCRIPTION_WAIT_SECONDS`` override —
and an expired bound logs stage/bound/elapsed at WARNING before the failure
surfaces, with the surfaced error naming the stage.

Hermeticity: the pool loop runs against a scripted executor whose futures
model the worker's stage time — the real ``as_completed`` only yields
already-done futures, so a scripted future whose ``result(timeout)`` blocks
for the scaled stage time (and raises ``TimeoutError`` when the bound is
shorter) is the only way to drive both the consumed and the expired wait
paths deterministically. No Qdrant/LLM/ASR endpoint is contacted and no real
``~/.secondbrain`` is written.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
import wave
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import secondbrain.document.ingestor._sync as ingestor_sync
from secondbrain.document.ingestor._async import AsyncDocumentIngestor
from secondbrain.document.ingestor._sync import (
    AUDIO_TRANSCRIPTION_WAIT_BASE_SECONDS,
    AUDIO_TRANSCRIPTION_WAIT_FLOOR_SECONDS,
    AUDIO_TRANSCRIPTION_WAIT_PER_SECOND_FACTOR,
    TEXT_WORKER_WAIT_SECONDS,
    TRANSCRIPTION_WAIT_SECONDS_ENV,
    DocumentIngestor,
    _audio_stage_cm,
    _probe_audio_duration_seconds,
    _transcription_wait_seconds,
)
from secondbrain.logging.stage_timing import SLOW_STAGE_SECONDS_ENV

STAGE_LOGGER = "secondbrain.logging.stage_timing"
INGESTOR_LOGGER = "secondbrain.document.ingestor._sync"


def _write_wav(path: Path, seconds: float, framerate: int = 8000) -> Path:
    """Write a minimal mono 16-bit WAV of *seconds* duration at *path*."""
    frames = b"\x00\x00" * int(seconds * framerate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        handle.writeframes(frames)
    return path


def _worker_payload() -> dict[str, object]:
    """A successful pool-worker payload (documents already embedded)."""
    return {
        "success": True,
        "documents": [
            {"chunk_id": "c1", "chunk_text": "hello", "embedding": [0.0, 0.0]}
        ],
        "extracted_chunks": 1,
        "skipped": False,
        "structure": None,
        "audio_transcript": [],
    }


def _stage_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == STAGE_LOGGER]


def _elapsed_seconds(message: str) -> float:
    match = re.search(r"elapsed=([0-9.]+)s", message)
    assert match is not None, message
    return float(match.group(1))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from the documented default bounds/thresholds."""
    monkeypatch.delenv(TRANSCRIPTION_WAIT_SECONDS_ENV, raising=False)
    monkeypatch.delenv(SLOW_STAGE_SECONDS_ENV, raising=False)


class TestDerivedWaitBound:
    def test_documented_default_constants(self) -> None:
        """The pinned D6 defaults: 300 s base + 2 s/audio-second, 900 s floor."""
        assert TEXT_WORKER_WAIT_SECONDS == 300.0
        assert AUDIO_TRANSCRIPTION_WAIT_BASE_SECONDS == 300.0
        assert AUDIO_TRANSCRIPTION_WAIT_PER_SECOND_FACTOR == 2.0
        assert AUDIO_TRANSCRIPTION_WAIT_FLOOR_SECONDS == 900.0

    def test_derived_bound_formula(self) -> None:
        assert _transcription_wait_seconds(0.0) == 900.0  # floored
        assert _transcription_wait_seconds(100.0) == 900.0  # floored (< 900)
        assert _transcription_wait_seconds(1000.0, 2) == 300.0 + 2.0 * 1000.0 * 2

    def test_observed_short_clip_is_covered_by_floor(self) -> None:
        """The 9.9 s clip derives 319.8 s and is floored to 900 s (> 408 s)."""
        bound = _transcription_wait_seconds(9.9)
        assert bound == 900.0
        assert bound > 408.0

    def test_negative_duration_is_clamped(self) -> None:
        assert _transcription_wait_seconds(-5.0) == 900.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1234.5", 1234.5),
            ("120", 120.0),  # explicit override wins even below the floor
            ("  700  ", 700.0),
        ],
    )
    def test_override_env_wins(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
    ) -> None:
        monkeypatch.setenv(TRANSCRIPTION_WAIT_SECONDS_ENV, raw)
        assert _transcription_wait_seconds(9.9) == expected

    @pytest.mark.parametrize("raw", ["abc", "", "   ", "nan", "inf", "-1", "0"])
    def test_malformed_override_falls_back_to_derived(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv(TRANSCRIPTION_WAIT_SECONDS_ENV, raw)
        assert _transcription_wait_seconds(1000.0) == 300.0 + 2.0 * 1000.0


class TestAudioDurationProbe:
    def test_wav_duration_read(self, tmp_path: Path) -> None:
        wav = _write_wav(tmp_path / "clip.wav", 0.5)
        assert _probe_audio_duration_seconds(wav) == pytest.approx(0.5)

    @pytest.mark.parametrize("suffix", [".wav", ".mp3"])
    def test_unreadable_file_returns_zero(self, tmp_path: Path, suffix: str) -> None:
        noise = tmp_path / f"noise{suffix}"
        noise.write_bytes(b"definitely not audio")
        assert _probe_audio_duration_seconds(noise) == 0.0


class TestStageGate:
    def test_audio_files_get_timed_stage(self) -> None:
        stage_cm = _audio_stage_cm("chunk", Path("clip.wav"))
        assert not isinstance(stage_cm, nullcontext)

    def test_non_audio_files_get_noop(self) -> None:
        assert isinstance(_audio_stage_cm("chunk", Path("doc.txt")), nullcontext)


class _ScriptedFuture:
    """Future stand-in whose ``result()`` models the worker's stage time.

    ``result(timeout)`` blocks for the scripted (scaled) stage duration and
    returns the payload; a timeout shorter than the stage blocks for the
    timeout and raises ``TimeoutError`` — exactly the expiry the wait loop
    must handle. The blocking also makes the submission-anchored stage record
    report the scripted stage time rather than ~0.
    """

    def __init__(self, payload: dict[str, object], stage_seconds: float) -> None:
        self._payload = payload
        self._stage_seconds = stage_seconds

    def done(self) -> bool:
        return True

    def add_done_callback(self, fn: object) -> None:
        fn(self)

    def cancel(self) -> bool:
        return False

    def result(self, timeout: float | None = None) -> dict[str, object]:
        if timeout is not None and timeout < self._stage_seconds:
            time.sleep(timeout)
            raise TimeoutError("simulated worker stage exceeding its wait bound")
        time.sleep(self._stage_seconds)
        return self._payload


def _scripted_executor(
    plan: dict[str, tuple[dict[str, object], float]],
    submitted: list[_ScriptedFuture],
) -> type:
    """Build an executor class whose ``submit`` returns scripted futures."""

    class _ScriptedExecutor:
        def __init__(
            self, max_workers: int = 1, *args: object, **kwargs: object
        ) -> None:
            self.max_workers = max_workers

        def __enter__(self) -> _ScriptedExecutor:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def submit(
            self, fn: object, *args: object, **kwargs: object
        ) -> _ScriptedFuture:
            future = _ScriptedFuture(*plan[str(args[0])])
            submitted.append(future)
            return future

    return _ScriptedExecutor


def _patch_pool_transport(
    monkeypatch: pytest.MonkeyPatch,
    plan: dict[str, tuple[dict[str, object], float]],
    submitted: list[_ScriptedFuture],
) -> None:
    """Swap the pool loop's executor and as_completed for scripted ones.

    The method imports both lazily at call time, so patching the module
    attributes takes effect.
    """
    monkeypatch.setattr(
        concurrent.futures,
        "as_completed",
        lambda fs, timeout=None: iter(list(fs)),
    )
    monkeypatch.setattr(
        ingestor_sync,
        "ThreadPoolExecutor",
        _scripted_executor(plan, submitted),
    )


@pytest.fixture
def scaled_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scale every wait-bound constant into the sub-second test range.

    Preserves the documented relationships: the legacy text bound (0.2 s) sits
    below the scripted audio stage (0.3 s), which sits below the derived audio
    floor (0.6 s) — so a would-expire-at-legacy stage is still covered by the
    derived bound, mirroring 300 s / 408 s / 900 s.
    """
    monkeypatch.setattr(ingestor_sync, "TEXT_WORKER_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(ingestor_sync, "AUDIO_TRANSCRIPTION_WAIT_BASE_SECONDS", 0.05)
    monkeypatch.setattr(ingestor_sync, "AUDIO_TRANSCRIPTION_WAIT_FLOOR_SECONDS", 0.6)
    monkeypatch.setattr(
        ingestor_sync, "AUDIO_TRANSCRIPTION_WAIT_PER_SECOND_FACTOR", 2.0
    )


def _run_pool(
    ingestor: DocumentIngestor, files: list[Path]
) -> tuple[int, int, list[tuple[str, str]], int]:
    storage = MagicMock()
    embedding_gen = MagicMock()
    return ingestor._process_parallel_with_progress(
        files, embedding_gen, storage, 1, pool="thread", skip_existing=False
    )


class TestPoolWaitBound:
    def test_derived_bound_consumes_result_past_legacy_bound(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        scaled_bounds: None,
    ) -> None:
        """Scenario: bound covers model init plus a short clip.

        The scripted stage (0.3 s, scaled) exceeds the legacy text bound
        (0.2 s) but is within the derived audio bound (floor 0.6 s), so the
        result is consumed and no timeout is reported.
        """
        wav = _write_wav(tmp_path / "clip.wav", 0.1)  # floor-driven bound
        plan = {str(wav): (_worker_payload(), 0.3)}
        submitted: list[_ScriptedFuture] = []
        _patch_pool_transport(monkeypatch, plan, submitted)
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            successful, failed, reasons, skipped = _run_pool(ingestor, [wav])

        assert (successful, failed, skipped) == (1, 0, 0)
        assert reasons == []

        # The stage trail: one INFO completion naming the stage and file,
        # with the submission-anchored elapsed ≈ the scripted stage time.
        records = [
            record
            for record in _stage_records(caplog)
            if record.levelno == logging.INFO
            and "stage=audio.transcription" in record.getMessage()
        ]
        assert len(records) == 1
        message = records[0].getMessage()
        assert f"context={wav}" in message
        assert 0.25 <= _elapsed_seconds(message) <= 2.5

        # And no expiry trail anywhere.
        assert not [
            record
            for record in caplog.records
            if "wait bound expired" in record.getMessage()
        ]

    def test_override_bound_expiry_names_stage_bound_elapsed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        scaled_bounds: None,
    ) -> None:
        """Scenario: genuine timeout is attributable.

        The override (0.2 s) is below the scripted stage (0.3 s): the surfaced
        failure names the stage, the bound and the elapsed time, and a
        WARNING naming stage/bound/elapsed preceded it.
        """
        wav = _write_wav(tmp_path / "clip.wav", 1.0)
        monkeypatch.setenv(TRANSCRIPTION_WAIT_SECONDS_ENV, "0.2")
        plan = {str(wav): (_worker_payload(), 0.3)}
        submitted: list[_ScriptedFuture] = []
        _patch_pool_transport(monkeypatch, plan, submitted)
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            successful, failed, reasons, _skipped = _run_pool(ingestor, [wav])

        assert (successful, failed) == (0, 1)
        path_str, reason = reasons[0]
        assert path_str == str(wav)
        assert "audio.transcription stage exceeded its 0.2s worker wait bound" in reason
        surfaced_elapsed = float(
            re.search(r"elapsed ([0-9.]+)s", reason).group(1)  # type: ignore[union-attr]
        )
        assert 0.18 <= surfaced_elapsed <= 0.45

        ingestor_records = [
            record for record in caplog.records if record.name == INGESTOR_LOGGER
        ]
        warning_index = next(
            index
            for index, record in enumerate(ingestor_records)
            if record.levelno == logging.WARNING
            and "wait bound expired" in record.getMessage()
        )
        error_index = max(
            index
            for index, record in enumerate(ingestor_records)
            if record.levelno == logging.ERROR
        )
        assert warning_index < error_index
        expiry = ingestor_records[warning_index].getMessage()
        assert "stage=audio.transcription" in expiry
        assert "bound=0.200s" in expiry
        assert 0.18 <= _elapsed_seconds(expiry) <= 0.45

        # The timing helper also logged the stage failure (with the error)
        # before the timeout propagated to the handler.
        stage_failures = [
            record
            for record in _stage_records(caplog)
            if "Pipeline stage failed" in record.getMessage()
        ]
        assert len(stage_failures) == 1
        assert "error=TimeoutError" in stage_failures[0].getMessage()

    def test_text_task_uses_legacy_bound_ignoring_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        scaled_bounds: None,
    ) -> None:
        """A text task keeps the legacy bound; the audio override is ignored."""
        txt = tmp_path / "doc.txt"
        txt.write_text("hello", encoding="utf-8")
        # Override (0.1 s) below the stage (0.15 s): if the text path wrongly
        # honored the audio override it would expire; the legacy bound (0.2 s)
        # consumes it.
        monkeypatch.setenv(TRANSCRIPTION_WAIT_SECONDS_ENV, "0.1")
        plan = {str(txt): (_worker_payload(), 0.15)}
        submitted: list[_ScriptedFuture] = []
        _patch_pool_transport(monkeypatch, plan, submitted)
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            successful, failed, reasons, skipped = _run_pool(ingestor, [txt])

        assert (successful, failed, skipped) == (1, 0, 0)
        assert reasons == []
        # Stage timing is audio-scoped: a text file leaves no stage records.
        assert _stage_records(caplog) == []

    def test_text_task_expiring_legacy_bound_names_extraction(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        scaled_bounds: None,
    ) -> None:
        """A text stage longer than the legacy bound fails naming extraction.

        The scripted stage (0.45 s) sits between the legacy bound (0.2 s) and
        the derived audio floor (0.6 s): using the legacy bound for text
        expires, using the derived bound would not — the expiry proves the
        text path used the legacy bound.
        """
        txt = tmp_path / "doc.txt"
        txt.write_text("hello", encoding="utf-8")
        plan = {str(txt): (_worker_payload(), 0.45)}
        submitted: list[_ScriptedFuture] = []
        _patch_pool_transport(monkeypatch, plan, submitted)
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            successful, failed, reasons, _skipped = _run_pool(ingestor, [txt])

        assert (successful, failed) == (0, 1)
        _path_str, reason = reasons[0]
        assert "extraction stage exceeded its 0.2s worker wait bound" in reason
        ingestor_records = [
            record for record in caplog.records if record.name == INGESTOR_LOGGER
        ]
        expiry = next(
            record.getMessage()
            for record in ingestor_records
            if "wait bound expired" in record.getMessage()
        )
        assert "stage=extraction" in expiry
        assert "bound=0.200s" in expiry


class TestExtractTextStage:
    @pytest.fixture
    def stubbed_docling(self, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
        """Stub the conversion chain so _extract_text runs hermetically."""
        from secondbrain.document import docling_factory, fast_text, processor

        conversions: list[Path] = []

        class _FakeConverter:
            def convert(self, path: object, page_range: object = None) -> object:
                conversions.append(Path(str(path)))
                return SimpleNamespace(document=SimpleNamespace(pages=[]))

        monkeypatch.setattr(
            docling_factory, "get_converter_for_path", lambda path: _FakeConverter()
        )

        def _fake_extend(
            document: object,
            segments: list[dict[str, object]],
            file_path: object = None,
        ) -> None:
            segments.append({"text": "hello", "page": 1})

        monkeypatch.setattr(processor, "_extend_segments_from_document", _fake_extend)
        monkeypatch.setattr(
            fast_text, "try_fast_pdf_extraction", lambda path, **kwargs: None
        )
        return conversions

    def test_audio_transcription_stage_logged(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        stubbed_docling: list[Path],
    ) -> None:
        wav = _write_wav(tmp_path / "clip.wav", 0.1)
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            segments = ingestor._extract_text(wav)

        assert segments == [{"text": "hello", "page": 1}]
        assert stubbed_docling == [wav]
        records = _stage_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "stage=audio.transcription" in message
        assert f"context={wav}" in message

    def test_text_file_has_no_audio_stage(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
        stubbed_docling: list[Path],
    ) -> None:
        txt = tmp_path / "doc.txt"
        txt.write_text("hello", encoding="utf-8")
        ingestor = DocumentIngestor()

        with caplog.at_level(logging.INFO):
            ingestor._extract_text(txt)

        assert _stage_records(caplog) == []


class TestAsyncStageTrail:
    async def test_async_audio_stages_logged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """The async mirror leaves the chunk/embed/topic-segmentation trail.

        The transcription stage itself is timed inside the shared
        ``_extract_text`` (covered by ``TestExtractTextStage``); here the
        extraction is stubbed, so the trail asserted is chunk, embed and
        audio.topic_segmentation.
        """
        import secondbrain.document.ingestor._async as ingestor_async

        wav = _write_wav(tmp_path / "clip.wav", 0.1)
        ingestor = AsyncDocumentIngestor()

        monkeypatch.setattr(
            ingestor,
            "_extract_text",
            lambda file_path, structure_sink=None: [{"text": "hello", "page": 1}],
        )
        # No real structure capture/store: keep the test off SQLite entirely.
        monkeypatch.setattr(
            ingestor_async, "capture_structure", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            ingestor_async,
            "config",
            lambda: SimpleNamespace(
                streaming_enabled=False,
                skip_existing_on_reingest=False,
                embedding_batch_size=8,
                audio_topic_segmentation_enabled=True,
            ),
        )

        async def _fake_batch(texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0, 0.0] for _ in texts]

        embedding_gen = SimpleNamespace(generate_batch_async=_fake_batch)
        storage = SimpleNamespace(store_batch_async=AsyncMock())

        with caplog.at_level(logging.INFO):
            ok = await ingestor.process_file_async(wav, embedding_gen, storage)

        assert ok is True
        assert storage.store_batch_async.await_count == 1
        messages = [record.getMessage() for record in _stage_records(caplog)]
        assert any("stage=chunk" in m and f"context={wav}" in m for m in messages)
        assert any("stage=embed" in m and f"context={wav}" in m for m in messages)
        assert any(
            "stage=audio.topic_segmentation" in m and f"context={wav}" in m
            for m in messages
        )
