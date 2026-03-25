"""MCP health and status tools implementation."""
from typing import Any

import logging

logger = logging.getLogger(__name__)


async def handle_health(arguments: dict[str, Any]) -> str:
    """Handle health tool call.

    Args:
        arguments: Tool arguments (none required).

    Returns:
        Health status of all services.
    """
    from secondbrain.logging import get_health_status

    try:
        status = get_health_status()

        output = f"Health Status: {status['status'].upper()}\n"
        output += f"Timestamp: {status['timestamp']}\n"
        output += f"Check Duration: {status['check_duration_seconds']:.3f}s\n\n"
        output += "Services:\n"

        for service, available in status["services"].items():
            icon = "✓" if available else "✗"
            output += f"  {icon} {service}\n"

        return output
    except Exception as e:
        logger.exception(f"Health check failed: {e}")
        return f"Error: {e!s}"


async def handle_status(arguments: dict[str, Any]) -> str:
    """Handle status tool call.

    Args:
        arguments: Tool arguments (none required).

    Returns:
        Database statistics.
    """
    from secondbrain.conversation.storage import ConversationStorage
    from secondbrain.storage.storage import VectorStorage

    try:
        with ConversationStorage() as storage:
            # Use VectorStorage instance to list chunks
            vector_storage = VectorStorage(storage)
            chunks = vector_storage.list_chunks(limit=1000)

            total_chunks = len(chunks)
            unique_sources = len({c["source_file"] for c in chunks}) if chunks else 0

            output = "Database Status\n"
            output += "=" * 40 + "\n"
            output += f"Total chunks: {total_chunks}\n"
            output += f"Unique sources: {unique_sources}\n"

            return output
    except Exception as e:
        logger.exception(f"Status check failed: {e}")
        return f"Error: {e!s}"


async def handle_metrics(arguments: dict[str, Any]) -> str:
    """Handle metrics tool call.

    Args:
        arguments: Tool arguments with type (ingestion/search/all).

    Returns:
        Performance metrics.
    """
    from secondbrain.utils.perf_monitor import metrics as perf_metrics

    try:
        metrics_type = arguments.get("type", "all")

        output = "Performance Metrics\n"
        output += "=" * 40 + "\n\n"

        if metrics_type in ["ingestion", "all"]:
            output += "Ingestion Metrics:\n"
            output += f"  Total documents processed: {perf_metrics.get('total_documents', 0)}\n"
            output += f"  Total chunks created: {perf_metrics.get('total_chunks', 0)}\n"
            output += "\n"

        if metrics_type in ["search", "all"]:
            output += "Search Metrics:\n"
            output += f"  Total searches: {perf_metrics.get('total_searches', 0)}\n"
            output += f"  Average query time: {perf_metrics.get('avg_query_time_ms', 0):.2f}ms\n"

        return output
    except Exception as e:
        logger.exception(f"Metrics failed: {e}")
        return f"Error: {e!s}"
