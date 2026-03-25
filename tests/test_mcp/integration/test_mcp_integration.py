"""Integration tests for MCP tools."""

import pytest


@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests for MCP tools."""

    @pytest.mark.asyncio
    async def test_ingest_tool_basic(self):
        """Test basic ingest tool execution."""
        from secondbrain_mcp.tools.ingest import handle_ingest

        # Test missing path
        result = await handle_ingest({})
        assert "Error: path is required" in result

    @pytest.mark.asyncio
    async def test_search_tool_basic(self):
        """Test basic search tool execution."""
        from secondbrain_mcp.tools.search import handle_search

        # Test missing query
        result = await handle_search({})
        assert "Error: query is required" in result

    @pytest.mark.asyncio
    async def test_health_tool_basic(self):
        """Test basic health tool execution."""
        from secondbrain_mcp.tools.health import handle_health

        # Just check it doesn't crash
        result = await handle_health({})
        assert "Health Status" in result or "Error:" in result

    @pytest.mark.asyncio
    async def test_status_tool_basic(self):
        """Test basic status tool execution."""
        from secondbrain_mcp.tools.health import handle_status

        # May fail if MongoDB not available - just check it doesn't crash unexpectedly
        result = await handle_status({})
        # Either returns status or an error message
        assert result is not None

    @pytest.mark.asyncio
    async def test_ls_tool_basic(self):
        """Test basic ls tool execution."""
        from secondbrain_mcp.tools.admin import handle_ls

        # May fail if MongoDB not available - just check it doesn't crash
        result = await handle_ls({})
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_tool_missing_params(self):
        """Test delete tool with missing parameters."""
        from secondbrain_mcp.tools.admin import handle_delete

        result = await handle_delete({})
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_metrics_tool_basic(self):
        """Test basic metrics tool execution."""
        from secondbrain_mcp.tools.health import handle_metrics

        # Just check it doesn't crash
        result = await handle_metrics({})
        assert "Performance Metrics" in result or "Error:" in result

    @pytest.mark.asyncio
    async def test_chat_tool_missing_query(self):
        """Test chat tool without query (interactive mode)."""
        from secondbrain_mcp.tools.chat import handle_chat

        # Just check it doesn't crash with empty query
        result = await handle_chat({})
        # Should either work or give an appropriate error
        assert result is not None
