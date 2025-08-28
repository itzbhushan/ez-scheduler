"""Centralized PostgreSQL service for analytics operations"""

import logging
import threading

from fastapi import Depends

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.services.llm_service import get_llm_client

_postgres_lock = threading.Lock()
_postgres_client = None

logger = logging.getLogger(__name__)


def get_postgres_client(
    llm_client: LLMClient = Depends(get_llm_client),
) -> PostgresClient:
    """Get the singleton PostgreSQL client instance with injected LLM client"""
    global _postgres_client
    if _postgres_client is None:
        with _postgres_lock:
            if _postgres_client is None:
                _postgres_client = PostgresClient(llm_client)
                logger.info("Initialized singleton PostgreSQL client")

    return _postgres_client
