"""Tests for HF-hub progress-bar suppression in the docling factory.

Verifies that the ``HF_HUB_DISABLE_PROGRESS_BARS`` / ``HF_HUB_VERBOSITY``
environment variables and the ``huggingface_hub`` logger are set idempotently
(``os.environ.setdefault``) whenever docling is configured, and that the env
var is honored by the installed ``huggingface_hub`` at runtime.
"""

import logging
import os

import huggingface_hub.utils
import pytest

# Imported for its module-level side effect: importing the document package
# pulls in processor, which sets the HF-hub suppression env vars via setdefault.
import secondbrain.document.docling_factory  # noqa: F401
from secondbrain.document.docling_factory import _build_pdf_format_option


def test_env_vars_set_on_docling_factory_import() -> None:
    assert os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"
    assert os.environ.get("HF_HUB_VERBOSITY") == "error"


def test_env_vars_set_within_build_pdf_format_option() -> None:
    _build_pdf_format_option(do_ocr=False, do_table_structure=False)
    assert os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"
    assert os.environ.get("HF_HUB_VERBOSITY") == "error"


def test_hf_logger_level_error() -> None:
    _build_pdf_format_option(do_ocr=False, do_table_structure=False)
    assert logging.getLogger("huggingface_hub").level <= logging.ERROR


def test_setdefault_preserves_user_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_DISABLE_PROGRESS_BARS", "0")
    _build_pdf_format_option(do_ocr=False, do_table_structure=False)
    assert os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "0"


def test_runtime_env_honored_even_if_hf_imported_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # huggingface_hub imported at module scope above; force the env var after
    # import to prove the runtime guard consults it dynamically, not at import.
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        # Not exported in py.typed __all__ but present at runtime.
        are_disabled = huggingface_hub.utils.are_progress_bars_disabled  # type: ignore[attr-defined]
        assert are_disabled() is True
    finally:
        monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
