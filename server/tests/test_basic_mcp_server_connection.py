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

                # Verify create_form tool exists
                tool_names = [tool.name for tool in tools]
                assert (
                    "create_form" in tool_names
                ), "create_form tool should be available"

        except Exception as e:
            pytest.fail(f"Failed to connect to MCP server: {e}")

    @pytest.mark.asyncio
    async def test_tool_schema_validation(self, mcp_client):
        """Test that the create_form tool has proper schema"""
        try:
            async with Client(mcp_client) as client:
                tools = await client.list_tools()
                create_form_tool = next(
                    (tool for tool in tools if tool.name == "create_form"), None
                )

                assert create_form_tool is not None, "create_form tool should exist"
                assert (
                    create_form_tool.description is not None
                ), "Tool should have description"
                assert (
                    "form creation" in create_form_tool.description.lower()
                ), "Description should mention form creation"

                # Check input schema if available
                if (
                    hasattr(create_form_tool, "inputSchema")
                    and create_form_tool.inputSchema
                ):
                    schema = create_form_tool.inputSchema
                    # Updated: tools now extract user_id from authenticated context
                    assert "initial_request" in str(
                        schema
                    ), "Schema should include initial_request parameter"

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

    @pytest.mark.asyncio
    async def test_mcp_tools_with_mock_authentication(self, mcp_client):
        """Test MCP tools work with mocked authentication"""
        try:
            async with Client(mcp_client) as client:
                # List available tools
                tools = await client.list_tools()
                print(f"Available tools: {[tool.name for tool in tools]}")

                # Verify we got tools back
                assert tools is not None, "Should receive tools list"
                assert len(tools) > 0, "Should have at least one tool"

                # Test get_form_analytics tool with mock user
                analytics_result = await client.call_tool(
                    "get_form_analytics", {"analytics_query": "List all my forms"}
                )

                print(f"Analytics result: {analytics_result}")
                assert analytics_result is not None, "Should receive analytics result"

                # Test create_form tool with mock user
                create_result = await client.call_tool(
                    "create_form",
                    {"initial_request": "Create a test coding workshop signup form"},
                )

                print(f"Create form result: {create_result}")
                assert create_result is not None, "Should receive create form result"

                # Both tools should work without authentication errors
                print("✅ All MCP tools work correctly with mock authentication")

        except Exception as e:
            print(f"MCP tool test failed: {e}")
            import traceback

            traceback.print_exc()
            pytest.fail(f"Failed to test MCP tools with mock authentication: {e}")
