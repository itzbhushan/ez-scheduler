"""Centralized PostgreSQL MCP service for the application"""

import logging

from fastapi import Depends

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_mcp_client import PostgresMCPClient
from ez_scheduler.config import config
from ez_scheduler.services.llm_service import get_llm_client

logger = logging.getLogger(__name__)

# Global singleton instance
_postgres_mcp_client = None


def get_postgres_mcp_client(
    llm_client: LLMClient = Depends(get_llm_client),
) -> PostgresMCPClient:
    """Get the singleton PostgreSQL MCP client instance with injected LLM client"""
    global _postgres_mcp_client
    if _postgres_mcp_client is None:
        _postgres_mcp_client = PostgresMCPClient(config, llm_client)
        logger.info("Initialized singleton PostgreSQL MCP client")
    return _postgres_mcp_client
