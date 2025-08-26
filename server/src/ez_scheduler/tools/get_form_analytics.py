"""Get Form Analytics Tool - Queries analytics about user's events via PostgreSQL MCP"""

import logging

from ez_scheduler.auth.dependencies import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_mcp_client import PostgresMCPClient

logger = logging.getLogger(__name__)


async def get_form_analytics_handler(
    user: User,
    analytics_query: str,
    postgres_mcp_client: PostgresMCPClient,
    llm_client: LLMClient,
) -> str:
    """
    Get analytics about user's forms using natural language queries.

    Args:
        user_id: User object
        analytics_query: Natural language query about form analytics

    Returns:
        Analytics results formatted for the user
    """
    logger.info(f"Analytics query for user {user.user_id}: {analytics_query}")

    try:
        # Use PostgreSQL MCP to execute analytics query
        async with postgres_mcp_client:
            results = await postgres_mcp_client.query_from_intent(
                user_intent=analytics_query,
                user=user,
                context={"query_type": "analytics"},
            )

        # Format results for user consumption
        if not results:
            return "No data found for your query. You may not have any forms or registrations yet."

        # Format the response using LLM for natural language formatting
        formatted_response = await _format_analytics_response(
            analytics_query, results, llm_client
        )
        return formatted_response

    except Exception as e:
        logger.error(f"Error processing analytics query: {e}")
        return "I'm having trouble retrieving your analytics data. Please try again or rephrase your question."


async def _format_analytics_response(
    query: str, results: list, llm_client: LLMClient
) -> str:
    """Format analytics results into a user-friendly response using LLM"""

    # Prepare data for LLM formatting
    analytics_data = {"query": query, "results": results, "result_count": len(results)}

    # Use LLM to format the analytics response
    try:
        response = await llm_client.process_instruction(
            messages=[
                {
                    "role": "user",
                    "content": f"""Format this analytics data into a user-friendly response for the user's query: "{query}"

                Analytics Data:
                {analytics_data}

                Requirements:
                - Use markdown formatting (** for bold)
                - Be conversational and helpful
                - Highlight key metrics and insights
                - If there are many results, show the most important ones first
                - Include counts, totals, or summaries where relevant
                - Keep the response concise but informative
                - If no results, explain that no data was found
                - If the user's intent includes request for the registration form url, return the full URL instead of just the slug.

                Format the response as if you're directly answering the user's question about their event analytics.""",
                }
            ],
            max_tokens=1000,
        )

        return response

    except Exception as e:
        logger.error(f"Error formatting analytics response with LLM: {e}")
        raise Exception("Failed to format analytics response. Please try again later.")
