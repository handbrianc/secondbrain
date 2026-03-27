"""Document converter wrapper and file conversion logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from secondbrain.document.segment import Segment
from secondbrain.exceptions import DocumentExtractionError
from secondbrain.utils.tracing import trace_operation


class DocumentConverterWrapper:
    """Wrapper for docling DocumentConverter with extraction logic."""

    def __init__(self) -> None:
        """Initialize the document converter."""
        from docling.document_converter import DocumentConverter

        self.converter: DocumentConverter = DocumentConverter()

    def convert(self, file_path: Path) -> Any:
        """Delegate to inner docling converter for backward compatibility.

        This method exists for tests that mock the converter directly.
        """
        return self.converter.convert(file_path)

    def extract_text(self, file_path: Path) -> list[Segment]:
        """Extract text content from a file."""
        segments: list[Segment] = []

        # Try docling first
        try:
            with trace_operation("extract_text"):
                result = self.convert(file_path)
                content = result.document

                if hasattr(content, "texts") and content.texts:
                    for text_item in content.texts:
                        if not hasattr(text_item, "text") or not text_item.text:
                            continue

                        page_num = 1
                        if hasattr(text_item, "prov") and text_item.prov:
                            prov = text_item.prov[0]
                            if hasattr(prov, "page_no"):
                                page_num = prov.page_no

                        segments.append({"text": text_item.text, "page": page_num})
        except DocumentExtractionError:
            raise
        except Exception as e:
            # Check if this is a "format not supported" error - if so, try fallback
            error_msg = str(e).lower()
            if "format not allowed" in error_msg or "format not supported" in error_msg:
                segments = []  # Fall through to text file fallback
            else:
                # Re-raise other exceptions as DocumentExtractionError
                raise DocumentExtractionError(
                    f"Failed to extract text from {file_path}: {e}"
                ) from e

        # Fallback: read as plain text if docling didn't produce segments
        if not segments:
            try:
                with file_path.open(encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                    if True:  # Always create segment, even for empty text
                        segments = [{"text": text, "page": 1}]
            except Exception as e:
                raise DocumentExtractionError(
                    f"Failed to extract text from {file_path}: {e}"
                ) from e

        return segments
