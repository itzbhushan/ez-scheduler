"""Centralized PostgreSQL MCP service for the application"""

import logging

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_mcp_client import PostgresMCPClient
from ez_scheduler.config import config

logger = logging.getLogger(__name__)

# Global PostgreSQL MCP client instance
_postgres_mcp_client = None


def get_postgres_mcp_client(llm_client: LLMClient) -> PostgresMCPClient:
    """Get or create the global PostgreSQL MCP client instance"""
    global _postgres_mcp_client
    if _postgres_mcp_client is None:
        _postgres_mcp_client = PostgresMCPClient(config, llm_client)
        logger.info("Initialized global PostgreSQL MCP client")
    return _postgres_mcp_client
