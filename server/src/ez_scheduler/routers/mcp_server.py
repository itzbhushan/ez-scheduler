import logging
import uuid

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_mcp_client import PostgresMCPClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler
from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)

# Create shared instances
logger.info("Creating shared LLM client...")
llm_client = LLMClient(config)

logger.info("Creating shared PostgresMCPClient...")
postgres_mcp_client = PostgresMCPClient(config, llm_client)

logger.info("Creating shared SignupFormService...")
db_session = next(get_db())
signup_form_service = SignupFormService(db_session)

# Create MCP app
mcp = FastMCP("ez-scheduler")


# Register MCP tools
@mcp.tool()
async def create_form(user_id: uuid.UUID, initial_request: str) -> str:
    """
    Initiates form creation conversation.

    Args:
        user_id: User identifier (required, must be a valid UUID)
        initial_request: Initial form creation request

    Returns:
        Response from the form creation process
    """
    return await create_form_handler(
        str(user_id), initial_request, llm_client, signup_form_service
    )


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


# Create the ASGI app from the MCP server
mcp_app = mcp.http_app()
