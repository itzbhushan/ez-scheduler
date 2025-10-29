"""Tests for EZ Scheduler MCP Server Connection"""

import asyncio

import pytest
from fastmcp.client import Client


class TestMCPServerConnection:
    """Test suite for MCP Server connection and tools"""

    @pytest.mark.asyncio
    async def test_server_startup(self, mcp_server_process):
        """Test that the MCP server starts without errors"""
        # Wait a moment for startup
        await asyncio.sleep(1)

        # Check if process is still running (hasn't crashed)
        if mcp_server_process.poll() is not None:
            # Process has exited, get the output to debug
            stdout, stderr = mcp_server_process.communicate()
            print(f"Server stdout: {stdout.decode() if stdout else 'None'}")
            print(f"Server stderr: {stderr.decode() if stderr else 'None'}")
            print(f"Server return code: {mcp_server_process.returncode}")

        assert mcp_server_process.poll() is None, "Server process should be running"

    @pytest.mark.asyncio
    async def test_mcp_client_connection(self, mcp_client):
        """Test connecting to the MCP server using FastMCP HTTP client"""
        try:
            async with Client(mcp_client) as client:
                # Test basic connection by listing tools
                tools = await client.list_tools()

                # Verify we got tools back
                assert tools is not None, "Should receive tools list"
                assert len(tools) > 0, "Should have at least one tool"

                # Verify key tools exist
                tool_names = [tool.name for tool in tools]
                assert "create_or_update_form" in tool_names
                assert "publish_form" not in tool_names
                assert "archive_form" in tool_names
                assert "get_form_analytics" in tool_names

        except Exception as e:
            pytest.fail(f"Failed to connect to MCP server: {e}")

    @pytest.mark.asyncio
    async def test_tool_schema_validation(self, mcp_client):
        """Test that the unified form tool exposes the expected schema"""
        try:
            async with Client(mcp_client) as client:
                tools = await client.list_tools()
                unified_tool = next(
                    (tool for tool in tools if tool.name == "create_or_update_form"),
                    None,
                )

                assert (
                    unified_tool is not None
                ), "create_or_update_form tool should exist"
                assert unified_tool.description, "Tool should have description"
                assert "conversational" in unified_tool.description.lower()

                if hasattr(unified_tool, "inputSchema") and unified_tool.inputSchema:
                    schema = unified_tool.inputSchema
                    schema_str = str(schema)
                    assert "user_id" in schema_str
                    assert "message" in schema_str

        except Exception as e:
            pytest.fail(f"Failed to validate tool schema: {e}")

    @pytest.mark.asyncio
    async def test_invalid_tool_call(self, mcp_client):
        """Test calling a non-existent tool"""
        try:
            async with Client(mcp_client) as client:
                # Try to call a non-existent tool
                with pytest.raises(Exception):
                    await client.call_tool("non_existent_tool", {})

        except Exception:
            # This is expected for the non-existent tool call
            pass
