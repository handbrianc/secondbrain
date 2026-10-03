"""Audio (ASR) converter routing tests for the docling factory.

Covers the third converter singleton introduced with docling WhisperS2T
support:

- audio files (``_AUDIO_SUFFIXES``) route to the ASR converter
  (``get_audio_converter``);
- the audio converter is a lazily-built, lock-guarded singleton and is reset
  by :func:`close_shared_converter`;
- PDF routing (text-layer probe -> text-only/OCR converter) is unaffected;
- ``_build_audio_converter`` rejects an unknown ``audio_asr_model`` preset
  with a clear ValueError naming the config key;
- the float32-on-CPU ``torch_dtype`` coercion helper
  (:func:`docling_factory._coerce_s2t_preset_for_device`).

Real docling is stubbed by the ``tests/test_document/conftest.py`` session
fixture, so the routing tests monkeypatch the ``_build_audio_converter`` /
``_build_text_converter`` / ``_build_converter`` seams with sentinels and
never touch heavy docling imports. The bogus-model test drives the real
``_build_audio_converter`` only up to the preset-resolution guard (it never
constructs an ``AsrPipeline`` or downloads models), and the coercion test
imports the real (cheap, no-network) pydantic preset from the installed
docling.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from secondbrain.document import docling_factory
from secondbrain.document.docling_factory import (
    _AUDIO_SUFFIXES,
    close_shared_converter,
    get_audio_converter,
    get_converter_for_path,
    get_shared_converter,
    get_text_converter,
)


@pytest.fixture(autouse=True)
def _reset_singletons() -> Iterator[None]:
    """Reset the shared converter singletons before and after each test."""
    close_shared_converter()
    yield
    close_shared_converter()


class _FakeCfg:
    """Minimal stand-in for the Config object's fields the factory reads."""

    def __init__(self, asr_model: str = "whisper_tiny_s2t") -> None:
        self.audio_asr_model = asr_model
        self.pdf_ocr_enabled = False


def _patch_audio_builder(monkeypatch: pytest.MonkeyPatch) -> object:
    """Replace the audio builder with a sentinel factory; returns the sentinel."""
    sentinel = object()
    monkeypatch.setattr(docling_factory, "_build_audio_converter", lambda: sentinel)
    return sentinel


# ---------------------------------------------------------------------------
# Resolver routing (stub-driven)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "clip.m4a",
        "song.mp3",
        "voice.wav",
        "tone.aac",
        "stream.ogg",
        "piano.flac",
        "SOUND.WAV",
        "MUSIC.M4A",
    ],
)
def test_audio_files_route_to_audio_converter(
    filename: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every supported audio suffix routes to the ASR converter."""
    monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())
    sentinel = _patch_audio_builder(monkeypatch)
    assert get_converter_for_path(filename) is sentinel


def test_audio_suffixes_constant_covers_new_formats() -> None:
    """_AUDIO_SUFFIXES must include the four newly supported audio formats."""
    assert {".m4a", ".aac", ".ogg", ".flac"} <= set(_AUDIO_SUFFIXES)
    assert {".wav", ".mp3"} <= set(_AUDIO_SUFFIXES)


def test_audio_converter_singleton_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated calls return the same converter without rebuilding."""
    monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())
    sentinel = _patch_audio_builder(monkeypatch)
    assert get_audio_converter() is sentinel
    assert get_audio_converter() is sentinel


def test_close_shared_converter_resets_audio_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close_shared_converter clears the audio singleton so it rebuilds."""
    monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())
    builds: list[object] = []

    def fake_builder() -> object:
        sentinel = object()
        builds.append(sentinel)
        return sentinel

    monkeypatch.setattr(docling_factory, "_build_audio_converter", fake_builder)
    first = get_audio_converter()
    close_shared_converter()
    second = get_audio_converter()
    assert first is not second
    assert builds == [first, second]


def test_pdf_routing_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text-layer PDFs still route to the text-only converter, not ASR."""
    text_sentinel = object()
    ocr_sentinel = object()
    monkeypatch.setattr(docling_factory, "_build_text_converter", lambda: text_sentinel)
    monkeypatch.setattr(docling_factory, "_build_converter", lambda: ocr_sentinel)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", lambda p: True)
    monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())

    assert get_converter_for_path("doc.pdf") is get_text_converter()
    # Non-PDF, non-audio formats still route to the OCR converter.
    assert get_converter_for_path("scan.png") is get_shared_converter()


# ---------------------------------------------------------------------------
# Builder guard: unknown audio_asr_model preset
# ---------------------------------------------------------------------------


def test_build_audio_converter_rejects_bogus_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown audio_asr_model preset -> ValueError naming the config key."""
    monkeypatch.setattr(
        "secondbrain.config.config", lambda: _FakeCfg(asr_model="bogus_model_s2t")
    )
    with pytest.raises(ValueError, match="audio_asr_model") as excinfo:
        docling_factory._build_audio_converter()
    assert "bogus_model_s2t" in str(excinfo.value)


# ---------------------------------------------------------------------------
# float32-on-CPU dtype coercion (real docling pydantic preset; no-network)
# ---------------------------------------------------------------------------


def _import_real_s2t_preset() -> tuple[type, object]:
    """Import the real S2T preset + its class despite the session docling stubs.

    ``tests/test_document/conftest.py`` parks MagicMock stubs over the docling
    names in ``sys.modules``, which blocks importing real docling submodules.
    This helper temporarily removes only the *stub* entries (never real modules
    another test may have imported), imports
    ``docling.datamodel.asr_model_specs`` for real (its import chain brings
    ``pipeline_options_asr_model`` along in the *same* import generation — so
    the returned class and instance are consistent), then restores
    ``sys.modules`` to exactly its prior state (stubs back in place; real
    modules newly imported inside the window are dropped again so no real
    docling state leaks into subsequent tests). Import and API errors propagate
    so this test fails if the required Docling API changes or is unavailable.
    """
    import importlib
    import sys
    from unittest.mock import MagicMock

    before = {k for k in sys.modules if k == "docling" or k.startswith("docling.")}
    stubbed = {
        k: sys.modules[k] for k in before if isinstance(sys.modules[k], MagicMock)
    }
    try:
        for k in stubbed:
            del sys.modules[k]
        specs = importlib.import_module("docling.datamodel.asr_model_specs")
        options_cls = importlib.import_module(
            "docling.datamodel.pipeline_options_asr_model"
        ).InlineAsrWhisperS2TOptions
        instance = specs.WHISPER_TINY_S2T
        assert isinstance(instance, options_cls)
        return options_cls, instance
    finally:
        newly = [
            k
            for k in sys.modules
            if (k == "docling" or k.startswith("docling.")) and k not in before
        ]
        for k in newly:
            sys.modules.pop(k)
        sys.modules.update(stubbed)


class _ExplodingModelCopy:
    """Pydantic-like stand-in whose ``model_copy`` raises (defensive path)."""

    torch_dtype = "float16"

    def model_copy(self, **_kw: object) -> object:
        raise RuntimeError("boom")


def test_coerce_s2t_preset_for_device() -> None:
    """CPU + float16 -> float32 copy; CUDA/float32 passthrough; original kept.

    Uses the real ``InlineAsrWhisperS2TOptions`` pydantic preset imported
    straight from the installed docling — cheap and no-network. Import or API
    changes must fail this test rather than silently skipping its coverage.
    """
    options_cls, original = _import_real_s2t_preset()

    # cpu + float16 (the preset default) -> coerced float32 deep copy
    coerced = docling_factory._coerce_s2t_preset_for_device(original, "cpu")
    assert coerced is not original
    assert coerced.torch_dtype == "float32"
    assert original.torch_dtype == "float16"  # module-level singleton untouched
    # Preset identity/fields preserved by the copy
    assert isinstance(coerced, options_cls)
    assert coerced.repo_id == original.repo_id
    assert coerced.supported_devices == original.supported_devices

    # cuda + float16 -> returned unchanged (same object, still float16)
    assert docling_factory._coerce_s2t_preset_for_device(original, "cuda") is original
    assert original.torch_dtype == "float16"

    # cpu + float32 -> unchanged (no coercion needed)
    f32 = options_cls(repo_id="tiny", torch_dtype="float32")
    assert docling_factory._coerce_s2t_preset_for_device(f32, "cpu") is f32

    # bfloat16 on cpu -> coerced too (CTranslate2 limitation covers both)
    bf16 = options_cls(repo_id="tiny", torch_dtype="bfloat16")
    coerced_bf16 = docling_factory._coerce_s2t_preset_for_device(bf16, "cpu")
    assert coerced_bf16 is not bf16
    assert coerced_bf16.torch_dtype == "float32"

    # Defensive paths: None, a plain non-pydantic object (no torch_dtype), a
    # test-stub MagicMock, and an object whose model_copy blows up are all
    # passed through unmodified — the builder must never crash on coercion.
    assert docling_factory._coerce_s2t_preset_for_device(None, "cpu") is None
    plain = object()
    assert docling_factory._coerce_s2t_preset_for_device(plain, "cpu") is plain
    from unittest.mock import MagicMock

    mock_spec = MagicMock()
    assert docling_factory._coerce_s2t_preset_for_device(mock_spec, "cpu") is mock_spec
    assert docling_factory._coerce_s2t_preset_for_device(_ExplodingModelCopy(), "cpu")


def test_resolve_s2t_device_defensive_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """_resolve_s2t_device never raises: stub/absent docling -> 'cpu'."""
    monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())
    # Under the session stub the decide_device import fails, exercising the
    # except branch; on a real host without accelerators decide_device itself
    # returns 'cpu'. Either way the result must be a plain device string.
    device = docling_factory._resolve_s2t_device(_FakeCfg(), None)
    assert isinstance(device, str)
    assert device in {"cpu", "cuda", "cuda:0", "mps", "xpu"}
