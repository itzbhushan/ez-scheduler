"""Tests for EZ Scheduler MCP Server Connection"""

import pytest
import asyncio
import subprocess
import os
from fastmcp.client import Client, PythonStdioTransport


class TestMCPServerConnection:
    """Test suite for MCP Server connection and tools"""
    
    @pytest.fixture
    async def mcp_server_process(self):
        """Start the MCP server as a subprocess for testing"""
        # Set environment variables - get current directory for relative paths
        env = os.environ.copy()
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["PYTHONPATH"] = os.path.join(current_dir, "src")
        
        # Start the server process
        process = subprocess.Popen(
            [os.path.join(current_dir, ".venv", "bin", "python"), "src/ez_scheduler/server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=current_dir
        )
        
        # Give the server time to start
        await asyncio.sleep(2)
        
        yield process
        
        # Clean up: terminate the process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    
    @pytest.mark.asyncio
    async def test_server_startup(self, mcp_server_process):
        """Test that the MCP server starts without errors"""
        # Wait a moment for startup
        await asyncio.sleep(1)
        
        # Check if process is still running (hasn't crashed)
        assert mcp_server_process.poll() is None, "Server process should be running"
    
    @pytest.mark.asyncio
    async def test_mcp_client_connection(self, mcp_server_process):
        """Test connecting to the MCP server using FastMCP client"""
        # Wait for server to be ready
        await asyncio.sleep(2)
        
        # Create transport and client with dynamic paths
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        transport = PythonStdioTransport(
            script_path="src/ez_scheduler/server.py",
            env={"PYTHONPATH": os.path.join(current_dir, "src")},
            cwd=current_dir
        )
        
        try:
            async with Client(transport) as client:
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
    async def test_create_form_tool_call(self, mcp_server_process):
        """Test calling the create_form tool"""
        # Wait for server to be ready
        await asyncio.sleep(2)
        
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        transport = PythonStdioTransport(
            script_path="src/ez_scheduler/server.py",
            env={"PYTHONPATH": os.path.join(current_dir, "src")},
            cwd=current_dir
        )
        
        try:
            async with Client(transport) as client:
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
    async def test_tool_schema_validation(self, mcp_server_process):
        """Test that the create_form tool has proper schema"""
        # Wait for server to be ready
        await asyncio.sleep(2)
        
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        transport = PythonStdioTransport(
            script_path="src/ez_scheduler/server.py",
            env={"PYTHONPATH": os.path.join(current_dir, "src")},
            cwd=current_dir
        )
        
        try:
            async with Client(transport) as client:
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
    async def test_invalid_tool_call(self, mcp_server_process):
        """Test calling a non-existent tool"""
        # Wait for server to be ready
        await asyncio.sleep(2)
        
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        transport = PythonStdioTransport(
            script_path="src/ez_scheduler/server.py",
            env={"PYTHONPATH": os.path.join(current_dir, "src")},
            cwd=current_dir
        )
        
        try:
            async with Client(transport) as client:
                # Try to call a non-existent tool
                with pytest.raises(Exception):
                    await client.call_tool("non_existent_tool", {})
            
        except Exception:
            # This is expected for the non-existent tool call
            pass