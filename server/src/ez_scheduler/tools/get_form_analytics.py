"""Get Form Analytics Tool - High-performance analytics via PostgreSQL client"""

import logging

from ez_scheduler.auth.dependencies import User
from ez_scheduler.backends.postgres_client import PostgresClient

logger = logging.getLogger(__name__)


async def get_form_analytics_handler(
    user: User,
    analytics_query: str,
    postgres_client: PostgresClient,
) -> str:
    """
    Get analytics about user's forms using natural language queries via PostgreSQL.

    Args:
        user: User object
        analytics_query: Natural language query about form analytics
        postgres_client: High-performance PostgreSQL client

    Returns:
        Analytics results formatted for the user
    """
    logger.info(f"Analytics query for user {user.user_id}: {analytics_query}")

    async with postgres_client:
        response = await postgres_client.process_analytics_query(
            user=user, analytics_query=analytics_query
        )

    return response
