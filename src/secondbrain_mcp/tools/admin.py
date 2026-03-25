"""MCP admin tools (ls, delete) implementation."""

from typing import Any

import logging

logger = logging.getLogger(__name__)


async def handle_ls(arguments: dict[str, Any]) -> str:
    """Handle ls tool call.

    Args:
        arguments: Tool arguments with type (document/chunk), limit.

    Returns:
        List of documents or chunks.
    """
    from secondbrain.management import Lister

    doc_type = arguments.get("type", "document")
    limit = arguments.get("limit", 100)

    try:
        with Lister(verbose=False) as lister:
            if doc_type == "document":
                # List chunks and group by source
                chunks = lister.list_chunks(limit=limit * 10)
                documents = {}
                for chunk in chunks:
                    source = chunk["source_file"]
                    if source not in documents:
                        documents[source] = {
                            "filename": source,
                            "chunk_count": 0,
                        }
                    documents[source]["chunk_count"] = (
                        documents[source]["chunk_count"] + 1  # type: ignore[operator]
                    )

                output = f"Documents ({len(documents)} total):\n\n"
                for doc in list(documents.values())[:limit]:
                    output += f"- {doc['filename']}: {doc['chunk_count']} chunks\n"
                return output
            else:
                # List chunks
                chunks = lister.list_chunks(limit=limit)
                output = f"Chunks ({len(chunks)} total):\n\n"
                for chunk in chunks:
                    output += (
                        f"- {chunk['chunk_id'][:12]}...: "
                        f"{chunk['source_file']} (page {chunk.get('page_number', 'N/A')})\n"
                    )
                return output
    except Exception as e:
        logger.exception(f"List failed: {e}")
        return f"Error: {e!s}"


async def handle_delete(arguments: dict[str, Any]) -> str:
    """Handle delete tool call.

    Args:
        arguments: Tool arguments with type, id, filename_pattern.

    Returns:
        Deletion result message.
    """
    import re

    from secondbrain.storage.storage import VectorStorage

    doc_type = arguments.get("type", "document")
    doc_id = arguments.get("id")
    filename_pattern = arguments.get("filename_pattern")

    if not doc_id and not filename_pattern:
        return "Error: Either id or filename_pattern is required"

    try:
        storage = VectorStorage()
        deleted_count = 0

        if doc_type == "document":
            if filename_pattern:
                # Delete by pattern
                chunks = storage.list_chunks(limit=100000)
                pattern = re.compile(filename_pattern)
                for chunk in chunks:
                    if pattern.search(chunk["source_file"]):
                        storage.delete_by_chunk_id(chunk["chunk_id"])
                        deleted_count += 1
            elif doc_id:
                # Delete by ID - treat as filename
                chunks = storage.list_chunks(limit=100000)
                for chunk in chunks:
                    if chunk["source_file"] == doc_id:
                        storage.delete_by_chunk_id(chunk["chunk_id"])
                        deleted_count += 1
        else:
            # Delete chunk by ID
            if doc_id:
                storage.delete_by_chunk_id(doc_id)
                deleted_count = 1

        return f"Deleted {deleted_count} items"
    except Exception as e:
        logger.exception(f"Delete failed: {e}")
        return f"Error: {e!s}"
