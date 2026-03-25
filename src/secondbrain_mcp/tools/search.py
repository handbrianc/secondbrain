"""MCP search tool implementation."""
from typing import Any

import logging

logger = logging.getLogger(__name__)


async def handle_search(arguments: dict[str, Any]) -> str:
    """Handle search tool call.

    Args:
        arguments: Tool arguments with query, top_k, min_score, format.

    Returns:
        Search results formatted as text.
    """
    from secondbrain.search import Searcher

    query = arguments.get("query")
    if not query:
        return "Error: query is required"

    try:
        top_k = arguments.get("top_k", 5)

        searcher = Searcher(verbose=False)
        results = searcher.search(query, top_k=top_k)

        # Filter by min_score after retrieval
        min_score = arguments.get("min_score", 0.78)
        results = [r for r in results if r.get("score", 0) >= min_score]

        if not results:
            return "No results found"

        output = f"Found {len(results)} results:\n\n"
        for i, result in enumerate(results, 1):
            output += (
                f"{i}. Score: {result.get('score', 0):.4f}\n"
                f"   File: {result.get('source_file', 'N/A')}\n"
                f"   Page: {result.get('page_number', 'N/A')}\n"
                f"   Text: {result.get('chunk_text', '')[:200]}...\n\n"
            )

        return output
    except Exception as e:
        logger.exception(f"Search failed: {e}")
        return f"Error: {e!s}"
