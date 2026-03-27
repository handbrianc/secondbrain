"""File type detection utilities for document processing."""

from __future__ import annotations

from pathlib import Path

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
    """Check if file extension is supported."""
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
    """Get the file type category for a given file path."""
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
