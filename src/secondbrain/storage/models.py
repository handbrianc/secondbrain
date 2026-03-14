"""Storage models and type definitions."""

from typing import TypedDict


class DatabaseStats(TypedDict):
    """Typed dictionary for database statistics.

    Attributes
    ----------
        total_chunks: Total number of chunks stored.
        unique_sources: Number of unique source files.
        database: Database name.
        collection: Collection name.
    """

    total_chunks: int
    unique_sources: int
    database: str
    collection: str
