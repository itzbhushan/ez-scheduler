#!/usr/bin/env python3
"""EZ Scheduler MCP Server - Signup Form Generation"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from ez_scheduler.llm_client import LLMClient
from ez_scheduler.services.postgres_mcp_client import PostgresMCPClient
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler
from fastmcp import FastMCP

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

# Create shared instances
logger.info("Creating shared LLM client...")
llm_client = LLMClient()

logger.info("Creating shared PostgresMCPClient...")
database_uri = os.getenv(
    "DATABASE_URL", "postgresql://ez_user:ez_password@localhost:5432/ez_scheduler"
)
postgres_mcp_client = PostgresMCPClient(database_uri, llm_client)

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
    return await create_form_handler(user_id, initial_request, llm_client)


@mcp.tool()
async def get_form_analytics(user_id: str, analytics_query: str) -> str:
    """
    Get analytics about user's forms and registrations.

    Args:
        user_id: User identifier
        analytics_query: Natural language query about form analytics

    Returns:
        Analytics results formatted for the user
    """
    return await get_form_analytics_handler(
        user_id, analytics_query, postgres_mcp_client, llm_client
    )


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8080"))
    logger.info(f"Starting HTTP MCP server on 0.0.0.0:{port}")
    try:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
