"""Value objects for the SecondBrain domain model.

Value objects are immutable objects defined by their attributes rather than identity.
They represent concepts like chunk IDs, embedding vectors, and file paths.
"""

from dataclasses import dataclass
from typing import NewType

# Type aliases for better type safety
ChunkId = NewType("ChunkId", str)
EmbeddingVector = NewType("EmbeddingVector", list[float])
SourcePath = NewType("SourcePath", str)


@dataclass(frozen=True)
class FileSize:
    """Immutable file size value object.

    Attributes
    ----------
    bytes : int
        Size in bytes (must be non-negative)
    """

    bytes: int

    def __post_init__(self) -> None:
        """Validate file size is non-negative."""
        if self.bytes < 0:
            raise ValueError("File size cannot be negative")

    @property
    def kilobytes(self) -> float:
        """Size in kilobytes."""
        return self.bytes / 1024

    @property
    def megabytes(self) -> float:
        """Size in megabytes."""
        return self.bytes / (1024 * 1024)

    def __str__(self) -> str:
        """Human-readable string representation of file size."""
        if self.megabytes >= 1:
            return f"{self.megabytes:.2f} MB"
        if self.kilobytes >= 1:
            return f"{self.kilobytes:.2f} KB"
        return f"{self.bytes} B"


@dataclass(frozen=True)
class PageNumber:
    """Immutable page number value object.

    Attributes
    ----------
    number : int
        Page number (1-indexed, must be positive)
    """

    number: int

    def __post_init__(self) -> None:
        """Validate page number is positive (1-indexed)."""
        if self.number < 1:
            raise ValueError("Page number must be positive (1-indexed)")

    def __int__(self) -> int:
        """Convert to integer."""
        return self.number
