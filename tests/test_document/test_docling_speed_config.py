"""Tests for the docling speed-lever config surface.

Covers the config knobs introduced for the docling speed-up:

- ``pdf_accelerator_device`` + ``pdf_num_threads`` (inference device/threads)
- ``max_ingest_processes`` (cap on AUTO-detected process-pool workers)
- ``pdf_threaded_pipeline`` + ``pdf_layout_batch_size`` (threaded/batched pipeline)
- ``pdf_generate_page_images`` / ``pdf_generate_picture_images`` /
  ``pdf_images_scale`` (image rendering levers)

and how :func:`_build_pdf_format_option` translates them into docling's options:
``AcceleratorOptions(device=..., num_threads=...)``, the threaded vs default
pipeline class, and the image/backend kwargs.

The docling pipeline classes are mocked so the wiring assertions hold whether
or not real docling is installed (the ``tests/test_document/conftest.py``
session fixture stubs docling under ``sys.modules``). The config layer is
driven through the ``SECONDBRAIN_PDF_*`` environment variables plus a
``get_config.cache_clear()`` so the knobs vary in a self-contained way.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pydantic
import pytest

from secondbrain.document import docling_factory

# Sentinels stand in for the docling ``AcceleratorDevice`` enum members so the
# wiring assertions are readable and independent of the (possibly stubbed) enum.
DEV_AUTO = object()
DEV_CPU = object()
DEV_MPS = object()
DEV_CUDA = object()


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Iterator[None]:
    """Rebuild the cached Config before and after each test so env picks up."""
    from secondbrain.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set SECONDBRAIN_PDF_* env vars (defaults except overridden) and reset cache."""
    from secondbrain.config import get_config

    defaults = {
        "SECONDBRAIN_PDF_ACCELERATOR_DEVICE": "auto",
        "SECONDBRAIN_PDF_NUM_THREADS": "4",
        "SECONDBRAIN_PDF_THREADED_PIPELINE": "false",
        "SECONDBRAIN_PDF_LAYOUT_BATCH_SIZE": "4",
        "SECONDBRAIN_PDF_GENERATE_PAGE_IMAGES": "false",
        "SECONDBRAIN_PDF_GENERATE_PICTURE_IMAGES": "false",
        "SECONDBRAIN_PDF_IMAGES_SCALE": "1.0",
    }
    if "SECONDBRAIN_MAX_INGEST_PROCESSES" in overrides:
        defaults["SECONDBRAIN_MAX_INGEST_PROCESSES"] = "0"
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    get_config.cache_clear()


def _capture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Replace the docling modules the factory imports with capture mocks.

    Returns ``(pdf_options_mock, threaded_mock, accelerator_options_mock)``:
    ``PdfPipelineOptions`` and ``ThreadedPdfPipelineOptions`` capture mocks plus
    the ``AcceleratorOptions`` capture mock. ``PdfFormatOption`` is patched to
    echo the ``pipeline_options`` it was built with.
    """
    import docling.datamodel.pipeline_options as po_import

    po: Any = po_import
    pdf_options_mock = MagicMock()
    threaded_mock = MagicMock()

    po.PdfPipelineOptions = pdf_options_mock
    po.ThreadedPdfPipelineOptions = threaded_mock
    po.RapidOcrOptions = MagicMock()
    po.TableFormerMode = SimpleNamespace(FAST=object(), ACCURATE=object())

    ao: Any = ModuleType("docling.datamodel.accelerator_options")
    ao.AcceleratorDevice = SimpleNamespace(
        AUTO=DEV_AUTO, CPU=DEV_CPU, MPS=DEV_MPS, CUDA=DEV_CUDA
    )
    accelerator_options_mock = MagicMock()
    ao.AcceleratorOptions = accelerator_options_mock

    dc: Any = ModuleType("docling.document_converter")

    def _fake_format_option(
        pipeline_options: object = None, **kwargs: object
    ) -> MagicMock:
        obj = MagicMock()
        obj.pipeline_options = pipeline_options
        return obj

    dc.PdfFormatOption = _fake_format_option

    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", po)
    monkeypatch.setitem(sys.modules, "docling.datamodel.accelerator_options", ao)
    monkeypatch.setitem(sys.modules, "docling.document_converter", dc)

    return pdf_options_mock, threaded_mock, accelerator_options_mock


# ---------------------------------------------------------------------------
# Config defaults (real config layer)
# ---------------------------------------------------------------------------


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """All speed levers default OFF / preserve current behavior."""
    from secondbrain.config import config

    _set_env(monkeypatch)
    c = config()
    assert c.pdf_accelerator_device == "auto"
    assert c.pdf_num_threads == 4
    assert c.max_ingest_processes == 0
    assert c.pdf_threaded_pipeline is False
    assert c.pdf_layout_batch_size == 4
    assert c.pdf_generate_page_images is False
    assert c.pdf_generate_picture_images is False
    assert c.pdf_images_scale == 1.0


def test_config_reads_env_toggles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SECONDBRAIN_PDF_* env vars drive the config fields."""
    from secondbrain.config import config

    _set_env(
        monkeypatch,
        SECONDBRAIN_PDF_ACCELERATOR_DEVICE="cuda",
        SECONDBRAIN_PDF_NUM_THREADS="8",
        SECONDBRAIN_MAX_INGEST_PROCESSES="4",
        SECONDBRAIN_PDF_THREADED_PIPELINE="true",
        SECONDBRAIN_PDF_LAYOUT_BATCH_SIZE="16",
        SECONDBRAIN_PDF_GENERATE_PAGE_IMAGES="true",
        SECONDBRAIN_PDF_GENERATE_PICTURE_IMAGES="true",
        SECONDBRAIN_PDF_IMAGES_SCALE="2.0",
    )
    c = config()
    assert c.pdf_accelerator_device == "cuda"
    assert c.pdf_num_threads == 8
    assert c.max_ingest_processes == 4
    assert c.pdf_threaded_pipeline is True
    assert c.pdf_layout_batch_size == 16
    assert c.pdf_generate_page_images is True
    assert c.pdf_generate_picture_images is True
    assert c.pdf_images_scale == 2.0


# ---------------------------------------------------------------------------
# Config validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("device", ["gpu", "xpu", ""])
def test_config_rejects_invalid_device(
    monkeypatch: pytest.MonkeyPatch, device: str
) -> None:
    """Only auto/cpu/mps/cuda are allowed for the accelerator device."""
    from secondbrain.config import config

    _set_env(monkeypatch, SECONDBRAIN_PDF_ACCELERATOR_DEVICE=device)
    with pytest.raises(pydantic.ValidationError):
        config()


def test_config_rejects_num_threads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """num_threads must be >= 1."""
    from secondbrain.config import config

    _set_env(monkeypatch, SECONDBRAIN_PDF_NUM_THREADS="0")
    with pytest.raises(pydantic.ValidationError):
        config()


def test_config_rejects_negative_max_ingest_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """max_ingest_processes must be >= 0."""
    from secondbrain.config import config

    monkeypatch.setenv("SECONDBRAIN_MAX_INGEST_PROCESSES", "-1")
    from secondbrain.config import get_config

    get_config.cache_clear()
    with pytest.raises(pydantic.ValidationError):
        config()


def test_config_rejects_layout_batch_size_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """layout_batch_size must be >= 1."""
    from secondbrain.config import config

    _set_env(monkeypatch, SECONDBRAIN_PDF_LAYOUT_BATCH_SIZE="0")
    with pytest.raises(pydantic.ValidationError):
        config()


def test_config_rejects_nonpositive_images_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """images_scale must be > 0."""
    from secondbrain.config import config

    _set_env(monkeypatch, SECONDBRAIN_PDF_IMAGES_SCALE="0")
    with pytest.raises(pydantic.ValidationError):
        config()


# ---------------------------------------------------------------------------
# Factory wiring (stub-robust: asserts exact kwargs passed to docling classes)
# ---------------------------------------------------------------------------


def test_default_pipeline_uses_pdf_options_and_auto_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Threaded off -> PdfPipelineOptions, default AUTO device + num_threads."""
    _set_env(monkeypatch)
    pdf_options_mock, threaded_mock, accelerator_mock = _capture(monkeypatch)

    option = docling_factory._build_pdf_format_option(
        do_ocr=False, do_table_structure=False
    )

    threaded_mock.assert_not_called()
    kwargs = pdf_options_mock.call_args.kwargs
    assert kwargs["generate_page_images"] is False
    assert kwargs["generate_picture_images"] is False
    assert kwargs["images_scale"] == 1.0
    accelerator_mock.assert_called_once_with(device=DEV_AUTO, num_threads=4)
    assert kwargs["accelerator_options"] is accelerator_mock.return_value
    assert option.pipeline_options is pdf_options_mock.return_value


def test_device_and_num_threads_map_to_accelerator_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Device string maps to the enum and num_threads is forwarded."""
    _set_env(
        monkeypatch,
        SECONDBRAIN_PDF_ACCELERATOR_DEVICE="cuda",
        SECONDBRAIN_PDF_NUM_THREADS="8",
    )
    _, _, accelerator_mock = _capture(monkeypatch)

    docling_factory._build_pdf_format_option(do_ocr=False, do_table_structure=False)

    accelerator_mock.assert_called_once_with(device=DEV_CUDA, num_threads=8)


def test_threaded_pipeline_uses_threaded_class_and_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Threaded on -> ThreadedPdfPipelineOptions + layout_batch_size forwarded."""
    _set_env(
        monkeypatch,
        SECONDBRAIN_PDF_THREADED_PIPELINE="true",
        SECONDBRAIN_PDF_LAYOUT_BATCH_SIZE="16",
    )
    _, threaded_mock, _ = _capture(monkeypatch)

    option = docling_factory._build_pdf_format_option(
        do_ocr=False, do_table_structure=False
    )

    assert option.pipeline_options is threaded_mock.return_value
    assert threaded_mock.call_args.kwargs["layout_batch_size"] == 16


def test_threaded_pipeline_preserves_image_and_device_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Threaded pipeline still forwards image/scale/accelerator options."""
    _set_env(
        monkeypatch,
        SECONDBRAIN_PDF_THREADED_PIPELINE="true",
        SECONDBRAIN_PDF_GENERATE_PAGE_IMAGES="true",
        SECONDBRAIN_PDF_IMAGES_SCALE="1.5",
    )
    _, threaded_mock, accelerator_mock = _capture(monkeypatch)

    docling_factory._build_pdf_format_option(do_ocr=False, do_table_structure=False)

    kwargs = threaded_mock.call_args.kwargs
    assert kwargs["generate_page_images"] is True
    assert kwargs["images_scale"] == 1.5
    accelerator_mock.assert_called_once_with(device=DEV_AUTO, num_threads=4)


def test_table_structure_options_still_added_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing table-structure block still runs alongside the speed levers."""
    _set_env(monkeypatch, SECONDBRAIN_PDF_TABLE_STRUCTURE_ENABLED="true")
    pdf_options_mock, _, _ = _capture(monkeypatch)

    docling_factory._build_pdf_format_option(do_ocr=False, do_table_structure=True)

    assert "table_structure_options" in pdf_options_mock.call_args.kwargs
