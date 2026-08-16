"""CLI command implementations.

Commands are split into domain submodules (ingest, search, system, chat,
summarize, docker) that each register their ``@cli.command()`` decorators
onto the shared :data:`secondbrain.cli.cli` group. This module imports all of
them so the entry point and test reloads see every registered command.
"""

from . import cli
from .chat import chat  # noqa: F401
from .docker import start, stop  # noqa: F401
from .errors import handle_cli_errors
from .ingest import ingest  # noqa: F401
from .search import delete, ls, search  # noqa: F401
from .summarize import summarize  # noqa: F401
from .system import health, metrics, status  # noqa: F401

__all__ = ["cli", "handle_cli_errors"]
