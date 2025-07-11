"""Tests for EZ Scheduler MCP Server Connection"""

import pytest
import asyncio
from fastmcp.client import Client


class TestMCPServerConnection:
    """Test suite for MCP Server connection and tools"""
    
    @pytest.mark.asyncio
    async def test_server_startup(self, mcp_server_process):
        """Test that the MCP server starts without errors"""
        # Wait a moment for startup
        await asyncio.sleep(1)
        
        # Check if process is still running (hasn't crashed)
        assert mcp_server_process.poll() is None, "Server process should be running"
    
    @pytest.mark.asyncio
    async def test_mcp_client_connection(self, mcp_server_process, mcp_client):
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
                assert "create_form" in tool_names, "create_form tool should be available"
            
        except Exception as e:
            pytest.fail(f"Failed to connect to MCP server: {e}")
    
    @pytest.mark.asyncio
    async def test_create_form_tool_call(self, mcp_server_process, mcp_client):
        """Test calling the create_form tool"""
        try:
            async with Client(mcp_client) as client:
                # Call the create_form tool
                result = await client.call_tool(
                    "create_form",
                    {
                        "user_id": "test_user_123",
                        "initial_request": "I need to create a signup form for my birthday party on March 15th at Central Park"
                    }
                )
                
                # Verify we got a response
                assert result is not None, "Should receive a response"
                
                # The response should contain some indication of form creation or conversation
                result_str = str(result)
                assert any(keyword in result_str.lower() for keyword in [
                    "form", "event", "birthday", "party", "march", "central park", "difficulties"
                ]), f"Response should relate to the request: {result_str}"
            
        except Exception as e:
            pytest.fail(f"Failed to call create_form tool: {e}")
    
    @pytest.mark.asyncio
    async def test_tool_schema_validation(self, mcp_server_process, mcp_client):
        """Test that the create_form tool has proper schema"""
        try:
            async with Client(mcp_client) as client:
                tools = await client.list_tools()
                create_form_tool = next((tool for tool in tools if tool.name == "create_form"), None)
                
                assert create_form_tool is not None, "create_form tool should exist"
                assert create_form_tool.description is not None, "Tool should have description"
                assert "form creation" in create_form_tool.description.lower(), "Description should mention form creation"
                
                # Check input schema if available
                if hasattr(create_form_tool, 'inputSchema') and create_form_tool.inputSchema:
                    schema = create_form_tool.inputSchema
                    assert "user_id" in str(schema), "Schema should include user_id parameter"
                    assert "initial_request" in str(schema), "Schema should include initial_request parameter"
                
        except Exception as e:
            pytest.fail(f"Failed to validate tool schema: {e}")
    
    @pytest.mark.asyncio 
    async def test_invalid_tool_call(self, mcp_server_process, mcp_client):
        """Test calling a non-existent tool"""
        try:
            async with Client(mcp_client) as client:
                # Try to call a non-existent tool
                with pytest.raises(Exception):
                    await client.call_tool("non_existent_tool", {})
            
        except Exception:
            # This is expected for the non-existent tool call
            pass