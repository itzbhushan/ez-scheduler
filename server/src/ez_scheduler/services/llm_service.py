"""Centralized LLM service for the application"""

import logging

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.config import config

logger = logging.getLogger(__name__)

# Global LLM client instance
_llm_client = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(config)
        logger.info("Initialized global LLM client")
    return _llm_client
