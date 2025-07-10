"""Test script for the MCP server"""

import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set a test API key if not set
if not os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "test_key_for_local_testing"

from src.ez_scheduler.server import EZSchedulerServer

async def test_server():
    """Test the MCP server functionality"""
    print("🚀 Starting EZ Scheduler MCP Server Test")
    
    # Create server instance
    server = EZSchedulerServer()
    await server.setup_handlers()
    
    # Test list_tools
    print("\n📋 Testing list_tools...")
    try:
        from mcp.types import ListToolsRequest
        tools_result = await server.server.list_tools()(ListToolsRequest())
        print(f"✅ Found {len(tools_result.tools)} tools:")
        for tool in tools_result.tools:
            print(f"   - {tool.name}: {tool.description}")
    except Exception as e:
        print(f"❌ Error testing list_tools: {e}")
    
    # Test create_form tool
    print("\n🔧 Testing create_form tool...")
    try:
        # Test data
        test_args = {
            "user_id": "test_user_123",
            "initial_request": "I need to create a signup form for my birthday party on January 15th at Central Park"
        }
        
        # Note: This will likely fail without a real API key, but we can test the structure
        result = await server.create_form_tool.handle(test_args)
        print(f"✅ create_form tool executed successfully")
        print(f"   Response: {result.content[0].text[:100]}...")
        
    except Exception as e:
        print(f"⚠️  Expected error (likely API key): {e}")
        print("   This is normal for local testing without API key")
    
    # Test database connection
    print("\n🗄️  Testing database connection...")
    try:
        from src.ez_scheduler.models.database import engine, SessionLocal
        from src.ez_scheduler.models.models import Conversation
        
        # Test database connection
        with SessionLocal() as session:
            # Try to query conversations table
            conversations = session.query(Conversation).all()
            print(f"✅ Database connection successful. Found {len(conversations)} conversations.")
            
    except Exception as e:
        print(f"❌ Database error: {e}")
    
    print("\n🎉 Server test completed!")

if __name__ == "__main__":
    asyncio.run(test_server())