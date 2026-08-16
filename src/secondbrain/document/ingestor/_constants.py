"""Pure helper functions, constants, and file-type detection for ingestion."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

from secondbrain.config import config

# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)


def _element_text(el: Any) -> str:
    if hasattr(el, "export_to_data_frame"):
        try:
            return str(el.export_to_data_frame().to_csv(index=False))
        except Exception:
            return str(el)
    if hasattr(el, "text") and el.text:
        return str(el.text)
    return ""


def _get_doc_config() -> Any:

    return config()


def _detect_cpu_count() -> int | None:
    """Wrap os.cpu_count() for testability."""
    return os.cpu_count()


# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)

MAX_MEMORY_BATCH_SIZE = 100

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".asciidoc",
    ".adoc",
    ".tex",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".wav",
    ".mp3",
    ".vtt",
    ".xml",
    ".json",
}


def is_supported(file_path: Path) -> bool:
    """Check if file extension is supported.

    Args:
        file_path: Path to check.

    Returns
    -------
        True if file type is supported, False otherwise.
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
    """Get the file type category for a given file path.

    Args:
        file_path: Path to determine file type for.

    Returns
    -------
        File type string (e.g., 'pdf', 'docx', 'image', 'audio', etc.).
    """
    ext = file_path.suffix.lower()
    type_map: dict[str, str] = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
        ".xlsx": "xlsx",
        ".html": "html",
        ".htm": "html",
        ".md": "markdown",
        ".txt": "text",
        ".asciidoc": "asciidoc",
        ".adoc": "asciidoc",
        ".tex": "latex",
        ".csv": "csv",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
        ".bmp": "image",
        ".webp": "image",
        ".wav": "audio",
        ".mp3": "audio",
        ".vtt": "webvtt",
        ".xml": "xml",
        ".json": "docling-json",
    }
    return type_map.get(ext, "unknown")
