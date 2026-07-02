"""Protocol interfaces for the document ingestion pipeline.

This module defines the structural contracts (Protocol) that components of the
document processing pipeline implement. No implementation logic lives here.

Exports:
    Segment: TypedDict representing a text segment with page info.
    DocumentParsingProtocol: structural protocol for file→segments conversion.
    ChunkAssemblyProtocol: structural protocol for segments→chunks assembly.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import TypedDict

if TYPE_CHECKING:
    pass


class Segment(TypedDict):
    """Text segment extracted from a document.

    Attributes
    ----------
    text : str
        The extracted text content.
    page : int
        The page number where this segment was found.
    """

    text: str
    page: int


class DocumentParsingProtocol:
    """Structural protocol for converting a file path to text segments."""

    @abstractmethod
    def parse(self, file_path: Path) -> list[Segment]:
        """Parse a file and extract text segments."""
        ...


class ChunkAssemblyProtocol:
    """Structural protocol for assembling raw segments into chunks."""

    @abstractmethod
    def assemble(
        self,
        segments: list[Segment],
        *,
        chunk_size: int,
        overlap: int,
    ) -> list[dict[str, Any]]:
        """Assemble segments into overlapping text chunks."""
        ...
