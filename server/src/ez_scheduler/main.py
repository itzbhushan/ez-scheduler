#!/usr/bin/env python3
"""EZ Scheduler MCP Server - Signup Form Generation"""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

from ez_scheduler.tools.create_form import create_form_handler

# Load environment variables
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug: Check if API key is loaded
logger.info(f"API key loaded: {bool(os.getenv('ANTHROPIC_API_KEY'))}")
logger.info(f"Env file path: {env_path}")
logger.info(f"Env file exists: {env_path.exists()}")

# Create MCP app
mcp = FastMCP("ez-scheduler")

# Register tools
@mcp.tool()
async def create_form(user_id: str, initial_request: str) -> str:
    """
    Initiates form creation conversation.
    
    Args:
        user_id: User identifier
        initial_request: Initial form creation request
        
    Returns:
        Response from the form creation process
    """
    return await create_form_handler(user_id, initial_request)


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8080"))
    logger.info(f"Starting HTTP MCP server on 0.0.0.0:{port}")
    try:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise