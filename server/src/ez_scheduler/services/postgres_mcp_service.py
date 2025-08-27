"""Centralized PostgreSQL MCP service for the application"""

import logging
import threading

from fastapi import Depends

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_mcp_client import PostgresMCPClient
from ez_scheduler.config import config
from ez_scheduler.services.llm_service import get_llm_client

_postgres_mcp_lock = threading.Lock()
# Global singleton instance
_postgres_mcp_client = None

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


def get_postgres_mcp_client(
    llm_client: LLMClient = Depends(get_llm_client),
) -> PostgresMCPClient:
    global _postgres_mcp_client
    if _postgres_mcp_client is None:
        with _postgres_mcp_lock:
            if _postgres_mcp_client is None:
                _postgres_mcp_client = PostgresMCPClient(config, llm_client)
                logger.info("Initialized singleton PostgreSQL MCP client")

    return _postgres_mcp_client
