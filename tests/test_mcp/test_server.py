"""Unit tests for MCP server."""

import pytest

from secondbrain_mcp.server import TOOL_HANDLERS, app, call_tool, list_tools


class TestMCPToolList:
    """Tests for MCP tool listing."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """Test that list_tools returns all 8 tools."""
        tools = await list_tools()
        assert len(tools) == 8
        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "ingest",
            "search",
            "chat",
            "ls",
            "delete",
            "health",
            "status",
            "metrics",
        ]
        assert sorted(tool_names) == sorted(expected_tools)

    @pytest.mark.asyncio
    async def test_list_tools_has_required_schema(self):
        """Test that each tool has required schema fields."""
        tools = await list_tools()
        for tool in tools:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.inputSchema is not None
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"

    @pytest.mark.asyncio
    async def test_ingest_tool_schema(self):
        """Test ingest tool has correct schema."""
        tools = await list_tools()
        ingest_tool = next(t for t in tools if t.name == "ingest")

        assert "path" in ingest_tool.inputSchema["required"]
        assert "recursive" in ingest_tool.inputSchema["properties"]
        assert "chunk_size" in ingest_tool.inputSchema["properties"]

    @pytest.mark.asyncio
    async def test_search_tool_schema(self):
        """Test search tool has correct schema."""
        tools = await list_tools()
        search_tool = next(t for t in tools if t.name == "search")

        assert "query" in search_tool.inputSchema["required"]
        assert "top_k" in search_tool.inputSchema["properties"]

    @pytest.mark.asyncio
    async def test_chat_tool_schema(self):
        """Test chat tool has correct schema."""
        tools = await list_tools()
        chat_tool = next(t for t in tools if t.name == "chat")

        # Query is optional in chat (can start interactive mode without it)
        assert "session_id" in chat_tool.inputSchema["properties"]
        assert "temperature" in chat_tool.inputSchema["properties"]


class TestMCPToolHandlers:
    """Tests for MCP tool handler registration."""

    def test_all_tools_registered(self):
        """Test that all tools have registered handlers."""
        expected_tools = [
            "ingest",
            "search",
            "chat",
            "ls",
            "delete",
            "health",
            "status",
            "metrics",
        ]
        for tool_name in expected_tools:
            assert tool_name in TOOL_HANDLERS, f"Handler missing for tool: {tool_name}"

    def test_handler_callable(self):
        """Test that all handlers are callable."""
        for tool_name, handler in TOOL_HANDLERS.items():
            assert callable(handler), f"Handler for {tool_name} is not callable"


class TestMCPToolCall:
    """Tests for MCP tool call routing."""

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self):
        """Test that calling unknown tool returns error."""
        result = await call_tool("unknown_tool", {})
        assert len(result.content) == 1
        assert result.isError is True
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_with_none_arguments(self):
        """Test that calling tool with None arguments is handled."""
        result = await call_tool("health", None)
        # Should handle gracefully, either return result or error
        assert result is not None


class TestMCPInitialization:
    """Tests for MCP server initialization."""

    def test_server_instance_created(self):
        """Test that server instance is created."""
        assert app is not None
        assert app.name == "secondbrain"
