import logging

from fastmcp import FastMCP

from ez_scheduler.auth.models import User
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)

# TODO: Consider using fastapi+MCP instead of FastMCP for better integration.
# Create MCP app
mcp = FastMCP("ez-scheduler")


# Register MCP tools
@mcp.tool()
async def create_form(user_id: str, initial_request: str) -> str:
    """
    Initiates form creation conversation.

    Args:
        user_id: Auth0 user identifier (required, string format like 'auth0|123')
        initial_request: Initial form creation request

    Returns:
        Response from the form creation process
    """
    # Create database connections using the standard abstraction
    llm_client = get_llm_client()

    # Create User for the handler
    user = User(user_id=user_id, claims={})

    try:
        # Use the standard database session generator
        db_session = next(get_db())
        try:
            signup_form_service = SignupFormService(db_session)
            return await create_form_handler(
                user, initial_request, llm_client, signup_form_service
            )
        finally:
            db_session.close()
    except Exception as e:
        return f"Error creating form: {str(e)}"


@mcp.tool()
async def get_form_analytics(user_id: str, analytics_query: str) -> str:
    """
    Get analytics about user's forms and registrations.

    Args:
        user_id: Auth0 user identifier (string format like 'auth0|123')
        analytics_query: Natural language query about form analytics

    Returns:
        Analytics results formatted for the user
    """
    llm_client = get_llm_client()

    # Create postgres client (it reads database URL from environment at runtime)
    postgres_client = PostgresClient(llm_client)

    # Create User for the handler
    user = User(user_id=user_id, claims={})

    try:
        return await get_form_analytics_handler(user, analytics_query, postgres_client)
    except Exception as e:
        return f"Error processing analytics query: {str(e)}"


# Create the ASGI app from the MCP server
mcp_app = mcp.http_app(path="/mcp")
