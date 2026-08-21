"""SQLite storage settings fragment for :class:`secondbrain.config.Config`.

Hosts conversation sessions/messages (non-vector data) that previously lived
in MongoDB. SQLite is embedded; no server is required.
"""

from pathlib import Path

from pydantic import Field, field_validator


class SqliteMixin:
    """SQLite conversation storage configuration."""

    sqlite_path: str = Field(
        default="~/.secondbrain/secondbrain.db",
        description=(
            "Filesystem path to the SQLite database for conversation sessions "
            "(override via SECONDBRAIN_SQLITE_PATH env var)"
        ),
    )

    @field_validator("sqlite_path")
    @classmethod
    def validate_sqlite_path(cls, v: str) -> str:
        """Validate and normalize the SQLite path."""
        if not v or not v.strip():
            raise ValueError("sqlite_path must be a non-empty path")
        expanded = str(Path(v).expanduser())
        return expanded
