"""MCP ingest tool implementation."""
from typing import Any

import logging

logger = logging.getLogger(__name__)


async def handle_ingest(arguments: dict[str, Any]) -> str:
    """Handle ingest tool call.

    Args:
        arguments: Tool arguments with path, recursive, chunk_size, etc.

    Returns:
        Result message with ingestion statistics.
    """
    from secondbrain.config import get_config
    from secondbrain.document import DocumentIngestor

    path = arguments.get("path")
    if not path:
        return "Error: path is required"

    try:
        config = get_config()
        chunk_size = arguments.get("chunk_size", config.chunk_size)
        chunk_overlap = arguments.get("chunk_overlap", config.chunk_overlap)
        recursive = arguments.get("recursive", False)
        cores = arguments.get("cores")
        batch_size = arguments.get("batch_size", 10)

        ingestor = DocumentIngestor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            verbose=False,
        )

        results = ingestor.ingest(
            path,
            recursive=recursive,
            batch_size=batch_size,
            cores=cores,
        )

        success_count = sum(
            1 for r in results if isinstance(r, dict) and r.get("success")
        )
        fail_count = len(results) - success_count

        return (
            f"Ingestion complete: {success_count} files succeeded, "
            f"{fail_count} files failed"
        )
    except Exception as e:
        logger.exception(f"Ingest failed: {e}")
        return f"Error: {e!s}"
