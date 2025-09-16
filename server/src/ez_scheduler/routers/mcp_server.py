import logging
import uuid

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from fastmcp.server.dependencies import get_access_token
from pydantic import AnyHttpUrl

from ez_scheduler.auth.models import User
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler


def get_authenticated_user() -> User:
    """
    Get authenticated user based on environment.

    Returns:
        User: Authenticated user object with proper context

    Raises:
        ValueError: If authentication fails or user cannot be determined
    """
    # Handle authentication based on environment
    if config["environment"] == "test":
        # Test mode - use random mock user ID for each session
        user_id = str(uuid.uuid4())
        user = User(user_id=user_id, claims={"sub": user_id, "email": "dev@localhost"})
        logger.info(f"Test mode - Using mock user_id: {user_id}")
        return user
    else:
        # Production mode - get authenticated user from token
        token = get_access_token()
        if token is None:
            raise ValueError("Authentication required")

        # Extract user ID from token claims (Auth0 uses 'sub' claim for user ID)
        user_id = token.claims.get("sub")
        logger.info(f"Extracted user_id from JWT: {user_id}")
        if not user_id:
            raise ValueError("User ID not found in authentication token")

        # Create User for the handler
        return User(user_id=user_id, claims=token.claims)


# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)

# Skip authentication only for testing
if config["environment"] == "test":
    # Create MCP app without authentication for local/test environments
    mcp = FastMCP("ez-scheduler")
    logger.info("MCP server running without authentication (local/test mode)")
else:
    # Configure JWT verification for Auth0 in production
    token_verifier = JWTVerifier(
        jwks_uri=f"https://{config['auth0_domain']}/.well-known/jwks.json",
        issuer=f"https://{config['auth0_domain']}/",
        audience=[
            "https://ez-scheduler-staging.up.railway.app/mcp",
            f"{config['app_base_url']}/mcp",
        ],
    )

    # Configure RemoteAuthProvider with Auth0
    auth_provider = RemoteAuthProvider(
        token_verifier=token_verifier,
        authorization_servers=[AnyHttpUrl(f"https://{config['auth0_domain']}")],
        base_url=config["app_base_url"],
    )

    # Create authenticated MCP app
    mcp = FastMCP("ez-scheduler", auth=auth_provider)
    logger.info("MCP server running with Auth0 authentication")


# Register MCP tools
@mcp.tool()
async def create_form(initial_request: str) -> str:
    """
    Initiates form creation conversation.

    Args:
        initial_request: Initial form creation request

    Returns:
        Response from the form creation process
    """
    # Get authenticated user
    user = get_authenticated_user()

    # Create database connections using the standard abstraction
    llm_client = get_llm_client()

    # Use the standard database session generator
    db_session = next(get_db())
    try:
        signup_form_service = SignupFormService(db_session)
        return await create_form_handler(
            user, initial_request, llm_client, signup_form_service
        )
    finally:
        db_session.close()


@mcp.tool()
async def get_form_analytics(analytics_query: str) -> str:
    """
    Get analytics about user's forms and registrations.

    Args:
        analytics_query: Natural language query about form analytics

    Returns:
        Analytics results formatted for the user
    """
    # Get authenticated user
    user = get_authenticated_user()

    llm_client = get_llm_client()

    # Create postgres client (it reads database URL from environment at runtime)
    postgres_client = PostgresClient(llm_client)

    return await get_form_analytics_handler(user, analytics_query, postgres_client)


# Create MCP app for mounting
mcp_app = mcp.http_app(path="/")
