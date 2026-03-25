"""MCP Server for SecondBrain.

This module provides the Model Context Protocol (MCP) server implementation
that exposes SecondBrain CLI commands as MCP tools.
"""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

from secondbrain_mcp.tools import (
    handle_chat,
    handle_delete,
    handle_health,
    handle_ingest,
    handle_ls,
    handle_metrics,
    handle_search,
    handle_status,
)

logger = logging.getLogger(__name__)

# Create the MCP server instance
app = Server("secondbrain")

# Tool handler mapping
TOOL_HANDLERS = {
    "ingest": handle_ingest,
    "search": handle_search,
    "chat": handle_chat,
    "ls": handle_ls,
    "delete": handle_delete,
    "health": handle_health,
    "status": handle_status,
    "metrics": handle_metrics,
}


@app.list_tools()  # type: ignore[no-untyped-call,misc]
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="ingest",
            description="Ingest documents into the vector database",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file or directory to ingest",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Recursively process directories",
                        "default": False,
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "Override default chunk size",
                    },
                    "chunk_overlap": {
                        "type": "integer",
                        "description": "Override default chunk overlap",
                    },
                    "cores": {
                        "type": "integer",
                        "description": "Number of CPU cores for parallel processing",
                    },
                    "batch_size": {
                        "type": "integer",
                        "description": "Batch size for processing",
                        "default": 10,
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="search",
            description="Search the vector database with semantic query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum similarity score (0.0-1.0)",
                        "default": 0.78,
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format",
                        "enum": ["table", "json"],
                        "default": "table",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="chat",
            description="Conversational Q&A with your documents using local LLM",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question or query",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Conversation session ID",
                        "default": "default",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of context chunks",
                        "default": 5,
                    },
                    "temperature": {
                        "type": "number",
                        "description": "LLM temperature (0.0-1.0)",
                        "default": 0.7,
                    },
                    "model": {
                        "type": "string",
                        "description": "LLM model name",
                    },
                    "show_sources": {
                        "type": "boolean",
                        "description": "Show source documents",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="ls",
            description="List ingested documents/chunks",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Type to list",
                        "enum": ["document", "chunk"],
                        "default": "document",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 100,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="delete",
            description="Delete documents from the vector database",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Type to delete",
                        "enum": ["document", "chunk"],
                        "default": "document",
                    },
                    "id": {
                        "type": "string",
                        "description": "Document/chunk ID to delete",
                    },
                    "filename_pattern": {
                        "type": "string",
                        "description": "Pattern to match filenames",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="health",
            description="Check health status of all services",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="status",
            description="Show statistics about the vector database",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="metrics",
            description="Show performance metrics and statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Metrics type",
                        "enum": ["ingestion", "search", "all"],
                        "default": "all",
                    },
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()  # type: ignore[misc]
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Call an MCP tool by name with arguments."""
    logger.info(f"Calling tool: {name} with arguments: {arguments}")

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ],
            isError=True,
        )

    try:
        result = await handler(arguments)
        return CallToolResult(
            content=[TextContent(type="text", text=result)],
            isError=False,
        )
    except Exception as e:
        logger.exception(f"Tool {name} failed: {e}")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Tool execution failed: {e!s}",
                )
            ],
            isError=True,
        )


async def main() -> None:
    """Run the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting SecondBrain MCP server...")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
