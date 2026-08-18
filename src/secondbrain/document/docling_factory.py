"""Shared docling ``DocumentConverter`` factory (process-wide singleton).

This module centralizes the heavy docling import and the ``PdfPipelineOptions``
construction so callers can share converter instances instead of building a
fresh, expensive one per file. It existed inline in two places:

- ``secondbrain.document.ingestor._sync.DocumentIngestor.__init__``
- ``secondbrain.document.processor._extract_chunk_and_embed_file`` (per file)

Both sites now call :func:`get_shared_converter`, which returns the same OCR
converter object on every call.

On-demand OCR
-------------
The factory holds two lazily-built converter instances:

- the OCR converter (``get_shared_converter``): PDFs run with OCR + table
  structure (the historical default);
- the text-only converter (``get_text_converter``): PDFs run with OCR disabled,
  using only the embedded text layer (with table structure per config).

:func:`get_converter_for_path` picks between them per document: PDFs that have
an embedded text layer skip OCR (the fast path), scanned PDFs still OCR
(parity preserved), and non-PDF formats always use the OCR converter (their
behavior is unchanged).

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

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import PdfFormatOption

    return PdfFormatOption(
        pipeline_options=PdfPipelineOptions(
            do_ocr=do_ocr,
            do_table_structure=do_table_structure,
            ocr_options=RapidOcrOptions(
                backend="torch",
                rapidocr_params={"EngineConfig.torch.use_mps": True},
            ),
            accelerator_options=AcceleratorOptions(
                device=AcceleratorDevice.AUTO, num_threads=4
            ),
        )
    )


def _build_docling_converter(
    *, do_ocr: bool, do_table_structure: bool
) -> DocumentConverter:
    """Build a docling converter configured for PDFs (lazy)."""
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
    historical default: PDFs run with OCR + table structure.
    """
    return _build_docling_converter(do_ocr=True, do_table_structure=True)


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


def close_shared_converter() -> None:
    """Reset the shared converter singletons (for tests / cleanup).

    Idempotent — safe to call even when no converter has been built.
    """
    global _ocr_converter, _text_converter
    _ocr_converter = None
    _text_converter = None


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
    - Non-PDF formats always use the OCR converter (unchanged behavior).
    - PDFs: if ``pdf_ocr_enabled`` is True, always OCR. Otherwise a PDF with an
      embedded text layer uses the text-only converter (fast path, no OCR),
      and a scanned PDF (no text layer) falls back to the OCR converter.

    The text-layer probe is cheap relative to OCR, so this stays fast on the
    digital-PDF path.
    """
    from secondbrain.config import config

    file_path = Path(path)
    cfg = config()
    if file_path.suffix.lower() == ".pdf":
        if cfg.pdf_ocr_enabled:
            return get_shared_converter()
        if pdf_has_text_layer(file_path):
            return get_text_converter()
    return get_shared_converter()
