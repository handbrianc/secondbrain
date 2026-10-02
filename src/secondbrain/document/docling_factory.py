"""Shared docling ``DocumentConverter`` factory (process-wide singleton).

This module centralizes the heavy docling import and the ``PdfPipelineOptions``
construction so callers can share converter instances instead of building a
fresh, expensive one per file. It existed inline in two places:

- ``secondbrain.document.ingestor._sync.DocumentIngestor.__init__``
- ``secondbrain.document.processor._extract_chunk_and_embed_file`` (per file)

Both sites now call :func:`get_shared_converter`, which returns the same OCR
converter object on every call.

On-demand OCR + audio transcription
-----------------------------------
The factory holds three lazily-built converter instances:

- the OCR converter (``get_shared_converter``): PDFs run with OCR + table
  structure (the historical default);
- the text-only converter (``get_text_converter``): PDFs run with OCR disabled,
  using only the embedded text layer (with table structure per config);
- the audio converter (``get_audio_converter``): audio files run through
  docling's ``AsrPipeline`` with the WhisperS2T model spec from the
  ``audio_asr_model`` config setting (CTranslate2 transcription that never
  imports openai-whisper). ``_build_audio_converter`` also quietens three
  benign-but-noisy upstream messages at their causes (compute-type fallback
  warning, module-level backend print, torch.jit.load FutureWarning); see its
  docstring.

:func:`get_converter_for_path` picks between them per document: audio files
(``_AUDIO_SUFFIXES``) always use the ASR converter, PDFs that have an embedded
text layer skip OCR (the fast path), scanned PDFs still OCR (parity
preserved), and other non-PDF formats always use the OCR converter (behavior
unchanged).

Thread-safety caveat
--------------------
Construction is guarded by a :class:`threading.Lock` so concurrent callers
never double-build the (expensive) converters. Whether docling's
``DocumentConverter.convert`` is itself safe to call concurrently from multiple
threads is **not** guaranteed here; this module does **not** add any global
locking around ``.convert()`` (that could serialize extraction). A later todo
handles process-pool isolation.

Lazy import
-----------
Nothing heavy is imported at module import time. The docling package (and the
options objects) are only imported/built inside the factory functions on first
call, preserving the repo's "avoid 2+ second import overhead" guarantee.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

_lock = threading.Lock()
_ocr_converter: DocumentConverter | None = None
_text_converter: DocumentConverter | None = None
_audio_converter: DocumentConverter | None = None

# Audio file extensions routed to the ASR converter by get_converter_for_path.
# Docling decodes them via PyAV (or a system ffmpeg when present).
_AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"})


def _disable_torch_model_compilation_on_mps() -> None:
    """Disable docling's ``torch.compile`` model compilation on MPS (< torch 2.12).

    Docling compiles the RT-DETR layout model with ``torch.compile`` by default
    (``settings.inference.compile_torch_models``). On Apple Silicon, torch's
    Inductor-Metal (MPS) backend in torch < 2.12 embeds invalid Metal shaders
    for nested masked-index blocks — a self-referential ``auto`` such as
    ``auto tmp_scoped_0 = static_cast<int>(tmp_scoped_0);`` — which crashes the
    layout stage of PDF ingest with an ``InductorError``. See
    pytorch/pytorch#186369 (fixed in 2.12.0 via #178304).

    This guard flips the global docling flag off only when on MPS with a torch
    older than the fix, sidestepping the bug entirely (eager MPS inference
    remains correct). On torch >= 2.12 or non-MPS devices it's a no-op, so the
    compile speedup is preserved where it is safe.
    """
    try:
        import torch
    except ImportError:
        return
    if not torch.backends.mps.is_available():
        return
    try:
        from packaging.version import Version
    except ImportError:
        return
    if Version(torch.__version__) >= Version("2.12"):
        return

    try:
        from docling.datamodel import settings as docling_settings

        docling_settings.settings.inference.compile_torch_models = False
    except Exception:  # pragma: no cover - defensive; non-fatal for ingestion
        return


def _rapidocr_use_mps_available() -> bool:
    """Whether RapidOCR's torch engine may target MPS on this host.

    RapidOCR validates ``use_mps`` against ``torch.backends.mps`` at engine
    construction and raises when MPS is absent (e.g. Intel/CUDA hosts), so the
    accelerator hint must only be emitted where MPS actually exists.
    """
    try:
        import torch
    except ImportError:
        return False
    # torch 2.14's inline stubs resolve mps.is_available() to Any; normalize
    # explicitly rather than returning Any from a bool function.
    return bool(torch.backends.mps.is_available())


class AcceleratorDeviceUnavailableError(ValueError):
    """A configured accelerator pin cannot be honored on this host."""


def _preflight_accelerator_device(device_name: str) -> None:
    """Fail fast at converter-build time when a pinned device is unavailable.

    Docling resolves each model's device lazily during pipeline initialization,
    so an unfulfillable ``pdf_accelerator_device`` pin otherwise surfaces as one
    confusing error per extracted file. A preflight here turns that into a
    single clear error on the first converter build.
    """
    try:
        from docling.utils.accelerator_utils import decide_device
    except ModuleNotFoundError:
        return

    try:
        decide_device(device_name)
    except Exception as exc:
        raise AcceleratorDeviceUnavailableError(
            f"SECONDBRAIN_PDF_ACCELERATOR_DEVICE='{device_name}' is unavailable "
            f"on this host ({type(exc).__name__}: {exc}). Install torch support "
            "for that device (for 'xpu': an XPU-enabled torch build plus the "
            "Level-Zero runtime), or set SECONDBRAIN_PDF_ACCELERATOR_DEVICE=auto."
        ) from exc


def _build_pdf_format_option(*, do_ocr: bool, do_table_structure: bool) -> Any:
    """Build a ``PdfFormatOption`` for the given OCR/table flags (lazy)."""
    import logging as _logging

    _logging.getLogger("RapidOCR").setLevel(_logging.ERROR)
    _logging.getLogger("docling").setLevel(_logging.WARNING)
    # Silence benign upstream chatter that fires during the layout/OCR stages:
    #   - transformers: "`torch_dtype` is deprecated" (docling passes the old
    #     arg name; it's docling's library code, not ours)
    #   - torch inductor: "Not enough SMs to use max_autotune_gemm mode" (a
    #     CUDA-only tuning path that is skipped on MPS)
    _logging.getLogger("transformers").setLevel(_logging.ERROR)
    _logging.getLogger("torch._inductor").setLevel(_logging.ERROR)

    # Suppress HF-hub progress bars; setdefault preserves a user's existing override.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    _logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)

    _disable_torch_model_compilation_on_mps()

    from secondbrain.config import config

    cfg = config()

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
        ThreadedPdfPipelineOptions,
    )
    from docling.document_converter import PdfFormatOption

    device = getattr(AcceleratorDevice, cfg.pdf_accelerator_device.upper())
    _preflight_accelerator_device(cfg.pdf_accelerator_device)
    pipe_cls = (
        ThreadedPdfPipelineOptions if cfg.pdf_threaded_pipeline else PdfPipelineOptions
    )

    pipeline_kwargs: dict[str, Any] = {
        "do_ocr": do_ocr,
        "do_table_structure": do_table_structure,
        "ocr_options": RapidOcrOptions(
            backend="torch",
            rapidocr_params=(
                {"EngineConfig.torch.use_mps": True}
                if _rapidocr_use_mps_available()
                else {}
            ),
        ),
        "accelerator_options": AcceleratorOptions(
            device=device, num_threads=cfg.pdf_num_threads
        ),
        "generate_page_images": cfg.pdf_generate_page_images,
        "generate_picture_images": cfg.pdf_generate_picture_images,
        "images_scale": cfg.pdf_images_scale,
    }

    if cfg.pdf_threaded_pipeline:
        pipeline_kwargs["layout_batch_size"] = cfg.pdf_layout_batch_size

    if do_table_structure:
        pipeline_kwargs["table_structure_options"] = TableStructureOptions(
            mode=(
                TableFormerMode.FAST
                if cfg.pdf_table_fast_mode
                else TableFormerMode.ACCURATE
            ),
            do_cell_matching=cfg.pdf_table_cell_matching,
        )

    return PdfFormatOption(pipeline_options=pipe_cls(**pipeline_kwargs))


def _build_docling_converter(
    *, do_ocr: bool, do_table_structure: bool
) -> DocumentConverter:
    """Build a docling converter configured for PDFs (lazy)."""
    from secondbrain.utils.mps_patch import patch_transformers_for_mps

    # RT-DETR position-embedding patch must be in place before the layout
    # pipeline initializes (first _get_pipeline call), not at import time —
    # applying it here keeps torch/transformers out of the import path.
    patch_transformers_for_mps()

    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    pdf_options = _build_pdf_format_option(
        do_ocr=do_ocr, do_table_structure=do_table_structure
    )
    return DocumentConverter(format_options={InputFormat.PDF: pdf_options})


def _build_converter() -> DocumentConverter:
    """Build the OCR-enabled configured docling converter.

    Imported lazily here (not at module scope) so that importing this module
    never triggers the 2+ second docling import overhead. This is the
    historical default: PDFs run with OCR. Table structure follows the
    ``pdf_table_structure_enabled`` config setting.
    """
    from secondbrain.config import config

    cfg = config()
    return _build_docling_converter(
        do_ocr=True, do_table_structure=cfg.pdf_table_structure_enabled
    )


def _build_text_converter() -> DocumentConverter:
    """Build the text-only (no OCR) configured docling converter.

    Table structure follows the ``pdf_table_structure_enabled`` config setting
    so the digital-PDF fast path still detects tables by default.
    """
    from secondbrain.config import config

    cfg = config()
    return _build_docling_converter(
        do_ocr=False, do_table_structure=cfg.pdf_table_structure_enabled
    )


def _coerce_s2t_preset_for_device(spec: Any, device: str) -> Any:
    """Coerce a WhisperS2T preset's ``torch_dtype`` for the resolved device.

    CTranslate2 cannot run ``float16``/``bfloat16`` compute on CPU. The
    ``*_S2T`` presets default to ``torch_dtype="float16"`` (a CUDA performance
    choice), so on a CPU-only install docling's transcriber would log
    ``compute_type='float16' is not supported by CTranslate2 on CPU; falling
    back to 'float32'.`` and quietly discard the preset value. Coercing here
    (on a deep copy — presets are module-level singletons in
    ``docling.datamodel.asr_model_specs``) removes both the warning and the
    pointless float16 attempt at their cause.

    Mirrors the exact condition in
    ``docling.pipeline.asr_transcriber._WhisperS2TModel.__init__``. Defensive
    throughout: anything unexpected (non-pydantic spec, stubbed attribute,
    import failure) returns the original spec unmodified.
    """
    if device != "cpu" or spec is None:
        return spec
    try:
        torch_dtype = getattr(spec, "torch_dtype", None)
        if torch_dtype not in ("float16", "bfloat16"):
            return spec
        copy = spec.model_copy(deep=True)
        copy.torch_dtype = "float32"
        return copy
    except Exception:  # pragma: no cover - defensive; never break builder
        return spec


def _resolve_s2t_device(cfg: Any, spec: Any) -> str:
    """Resolve the ASR device the same way docling's transcriber will.

    Calls docling's ``decide_device`` with the configured accelerator device
    (mapped to its ``AcceleratorDevice`` enum member, as docling compares
    against the lowercase enum values) and the preset's supported-device list.
    Falls back to ``"cpu"`` on any failure, mirroring the tolerance of
    :func:`_preflight_accelerator_device` — device resolution is only used
    here to pre-coerce ``torch_dtype``, so a wrong guess must never break
    converter construction (docling re-resolves authoritatively later).
    """
    try:
        from docling.datamodel.accelerator_options import AcceleratorDevice
        from docling.utils.accelerator_utils import decide_device

        device_name = getattr(AcceleratorDevice, cfg.pdf_accelerator_device.upper())
        return decide_device(device_name, supported_devices=spec.supported_devices)
    except Exception:  # pragma: no cover - defensive; cpu is the safe default
        return "cpu"


def _build_audio_converter() -> DocumentConverter:
    """Build the audio (ASR) configured docling converter.

    Uses docling's ``AsrPipeline`` with the WhisperS2T model spec named by the
    ``audio_asr_model`` config setting (default ``whisper_tiny_s2t``).
    WhisperS2T transcribes through CTranslate2 and never imports
    openai-whisper, which keeps audio ingestion working on Python 3.14 (the
    native Whisper backend does import it and fails there). The backend
    defaults to docling's ``NoOpBackend`` — correct for ASR-only pipelines.

    Three benign-but-noisy upstream messages are silenced at their causes:

    1. The transcriber's "compute_type='float16' is not supported by
       CTranslate2 on CPU" warning: the preset's ``torch_dtype`` is coerced to
       ``float32`` on a deep copy before handoff whenever the device resolves
       to CPU (:func:`_coerce_s2t_preset_for_device`), so docling's fallback
       branch never triggers.
    2. ``whisper_s2t.audio``'s module-level ``print("Audio backend: ...")``
       fires when ``whisper_s2t.backends`` is first imported (its package body
       does ``from ..audio import LogMelSpectogram``), which docling does
       lazily during the first transcription. Pre-importing that chain here
       with captured stdout keeps the terminal quiet; a missing install stays
       a loud, clear error (docling's own ImportError with its pip hint,
       raised at transcriber init).
    3. torch raises ``FutureWarning: `torch.jit.load` is not supported in
       Python 3.14+ ...`` when whisper_s2t's VAD loads its TorchScript assets
       during transcription. Only a scoped message filter is applied — never a
       blanket FutureWarning ignore (until upstream migrates to torch.export).
    """
    import logging as _logging
    import warnings as _warnings

    _logging.getLogger("docling").setLevel(_logging.WARNING)
    # Scoped filter for whisper_s2t's VAD TorchScript loads (torch.jit.load)
    # on Python 3.14+, until upstream migrates to torch.export. Message- and
    # category-scoped, so unrelated FutureWarnings stay visible.
    _warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        message=r".*torch\.jit\.load.*not supported in Python 3\.14.*",
    )

    from secondbrain.config import config

    cfg = config()

    from docling.datamodel import asr_model_specs
    from docling.datamodel.pipeline_options import AsrPipelineOptions

    pipeline_options = AsrPipelineOptions()
    # Config stores lowercase preset names ("whisper_tiny_s2t"); the module
    # exposes them uppercase (WHISPER_TINY_S2T). Membership-check via dir()
    # instead of relying on getattr raising: under test stubs a missing
    # attribute may be auto-created instead of raising AttributeError.
    spec_name = cfg.audio_asr_model.upper()
    available = [
        name
        for name in dir(asr_model_specs)
        if name.startswith("WHISPER") and name.endswith("_S2T")
    ]
    if spec_name not in available:
        raise ValueError(
            f"Unknown audio_asr_model value '{cfg.audio_asr_model}': no such "
            "WhisperS2T preset on docling.datamodel.asr_model_specs. Valid "
            f"values: {', '.join(sorted(name.lower() for name in available))}."
        )
    spec = getattr(asr_model_specs, spec_name)

    # Coerce the preset's dtype for the device docling will actually use, on a
    # deep copy (asr_model_specs members are module-level singletons). The
    # whole block is defensive: under docling test stubs the attributes are
    # MagicMocks and any failure must fall back to the untouched spec.
    try:
        device = _resolve_s2t_device(cfg, spec)
        spec = _coerce_s2t_preset_for_device(spec, device)
    except Exception:  # pragma: no cover - defensive; keep original spec
        spec = getattr(asr_model_specs, spec_name)
    pipeline_options.asr_options = spec

    # Pre-import whisper_s2t with captured stdout so the module-level
    # "Audio backend: ..." print (whisper_s2t.audio backend probe) never
    # reaches the terminal. The print fires on the first import of
    # ``whisper_s2t.backends`` (its package body does
    # ``from ..audio import LogMelSpectogram``), not at bare
    # ``import whisper_s2t`` — so the chain is pre-imported down to the
    # CTranslate2 model module docling's transcriber loads later. Docling's
    # subsequent imports then resolve from sys.modules silently. A missing
    # install must stay a loud, clear failure — only the print is silenced
    # here (ImportError is not caught).
    try:
        import contextlib as _contextlib
        import io as _io

        with _contextlib.redirect_stdout(_io.StringIO()):
            import whisper_s2t
            import whisper_s2t.backends.ctranslate2.model  # noqa: F401
    except ImportError:
        pass  # _WhisperS2TModel raises a clear error at transcriber init

    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import AudioFormatOption, DocumentConverter
    from docling.pipeline.asr_pipeline import AsrPipeline

    return DocumentConverter(
        format_options={
            InputFormat.AUDIO: AudioFormatOption(
                pipeline_cls=AsrPipeline, pipeline_options=pipeline_options
            )
        }
    )


def get_shared_converter() -> DocumentConverter:
    """Return the single shared OCR converter, building it on first call.

    The heavy docling imports and options construction happen lazily the first
    time this is called. Subsequent (and concurrent) calls return the same
    object without rebuilding.

    Returns
    -------
        The process-wide shared OCR ``DocumentConverter`` instance.
    """
    global _ocr_converter
    if _ocr_converter is None:
        with _lock:
            if _ocr_converter is None:
                _ocr_converter = _build_converter()
    return _ocr_converter


def get_text_converter() -> DocumentConverter:
    """Return the single shared text-only converter, building it on first call.

    Runs PDFs without OCR (text layer only) and with table structure per config.
    """
    global _text_converter
    if _text_converter is None:
        with _lock:
            if _text_converter is None:
                _text_converter = _build_text_converter()
    return _text_converter


def get_audio_converter() -> DocumentConverter:
    """Return the single shared audio (ASR) converter, building it on first call.

    Runs audio files through docling's ``AsrPipeline`` with the WhisperS2T
    model spec from the ``audio_asr_model`` config setting.
    """
    global _audio_converter
    if _audio_converter is None:
        with _lock:
            if _audio_converter is None:
                _audio_converter = _build_audio_converter()
    return _audio_converter


def close_shared_converter() -> None:
    """Reset the shared converter singletons (for tests / cleanup).

    Idempotent — safe to call even when no converter has been built.
    """
    global _ocr_converter, _text_converter, _audio_converter
    _ocr_converter = None
    _text_converter = None
    _audio_converter = None


# ---------------------------------------------------------------------------
# Text-layer probe + per-document resolver
# ---------------------------------------------------------------------------


def _open_pdf_backend(path: Path) -> Any:
    """Open a docling pypdfium2 backend for a PDF path (lazy)."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument

    in_doc = InputDocument(
        path, format=InputFormat.PDF, backend=PyPdfiumDocumentBackend
    )
    return PyPdfiumDocumentBackend(in_doc, path)


def _page_has_text(page: Any) -> bool:
    """Return True if a backend page yields at least one non-empty text cell."""
    for cell in page.get_text_cells():
        text = getattr(cell, "text", None)
        if isinstance(text, str) and text.strip():
            return True
    return False


def pdf_has_text_layer(path: str | Path) -> bool:
    """Return True if the PDF has an embedded text layer on any page.

    Scans the PDF's pages via docling's pypdfium2 backend, which is cheap
    relative to running OCR. If the backend is unavailable or the open fails,
    conservatively returns False (treat the document as needing OCR).
    """
    try:
        backend = _open_pdf_backend(Path(path))
        try:
            return any(_page_has_text(page) for page in backend.iter_pages())
        finally:
            backend.unload()
    except Exception:
        return False


def get_converter_for_path(path: str | Path) -> DocumentConverter:
    """Return the converter best suited for the given file path.

    Routing
    -------
    - Audio formats (``_AUDIO_SUFFIXES``) always use the ASR converter.
    - Non-PDF, non-audio formats always use the OCR converter (unchanged
      behavior).
    - PDFs: if ``pdf_ocr_enabled`` is True, always OCR. Otherwise a PDF with an
      embedded text layer uses the text-only converter (fast path, no OCR),
      and a scanned PDF (no text layer) falls back to the OCR converter.

    The text-layer probe is cheap relative to OCR, so this stays fast on the
    digital-PDF path.
    """
    from secondbrain.config import config

    file_path = Path(path)
    cfg = config()
    if file_path.suffix.lower() in _AUDIO_SUFFIXES:
        return get_audio_converter()
    if file_path.suffix.lower() == ".pdf":
        if cfg.pdf_ocr_enabled:
            return get_shared_converter()
        if pdf_has_text_layer(file_path):
            return get_text_converter()
    return get_shared_converter()
