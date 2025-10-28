from fastmcp import FastMCP

from ez_scheduler.auth.models import User
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.config import config
from ez_scheduler.logging_config import get_logger
from ez_scheduler.models.database import get_db, get_redis
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.routers.request_validator import resolve_form_or_ask
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.form_state_manager import FormStateManager
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_or_update_form import CreateOrUpdateFormTool
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler

logger = get_logger(__name__)

# TODO: Consider using fastapi+MCP instead of FastMCP for better integration.
# Create MCP app
mcp = FastMCP("ez-scheduler")


# Register MCP tools
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


@mcp.tool()
async def archive_form(
    user_id: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    """Archive a form (removes from public view).

    - Resolution order: `form_id → url_slug → title_contains (drafts) → latest draft`.
    - Permissions: Only the form owner may archive.
    - Idempotent: If already archived, returns a no-op message.

    Args:
        user_id: Auth0 user identifier (e.g., "auth0|123").
        form_id: Optional UUID of the target form.
        url_slug: Optional URL slug of the target form.
        title_contains: Optional substring to match a single draft title.

    Returns:
        Text message describing the result.
    """
    user = User(user_id=user_id, claims={})
    try:
        db_session = next(get_db())
        try:
            signup_form_service = SignupFormService(db_session)

            form = resolve_form_or_ask(
                signup_form_service,
                user,
                form_id=form_id,
                url_slug=url_slug,
                title_contains=title_contains,
                fallback_latest=True,
            )
            if not form:
                return "Form not found"

            if form.user_id != user.user_id:
                return "You do not own this form"

            if form.status == FormStatus.ARCHIVED:
                return "This form is already archived"

            result = signup_form_service.update_signup_form(
                form.id, {"status": FormStatus.ARCHIVED}
            )
            if not result.get("success"):
                return f"Archive failed: {result.get('error', 'unknown error')}"
            return "Form archived successfully"
        finally:
            db_session.close()
    except Exception as e:
        return f"Error archiving form: {str(e)}"


@mcp.tool()
async def create_or_update_form(user_id: str, message: str) -> str:
    """Create or update a form through natural conversation.

    This unified tool manages conversational form building:
    - Automatically detects active conversation threads
    - Maintains conversation history and form state in Redis
    - Auto-creates new drafts or updates existing ones based on context
    - Supports multi-turn conversations for gathering form requirements

    Use this for all form creation and update conversations. The tool will:
    - Remember previous exchanges (30-minute window)
    - Ask follow-up questions to gather missing information
    - Automatically create a draft when all required fields are collected
    - Update the same draft if user continues the conversation with changes

    Args:
        user_id: Auth0 user identifier (e.g., "auth0|123")
        message: User's natural language message (e.g., "Create a birthday party form")

    Returns:
        Natural language response continuing the conversation or confirming form creation

    Examples:
        create_or_update_form(user_id="auth0|abc", message="Create a form for my birthday party")
        create_or_update_form(user_id="auth0|abc", message="It's on December 15th at Central Park")
        create_or_update_form(user_id="auth0|abc", message="Actually, change the date to December 20th")
    """
    llm_client = get_llm_client()
    user = User(user_id=user_id, claims={})

    try:
        db_session = next(get_db())
        try:
            # Initialize services
            signup_form_service = SignupFormService(db_session)
            form_field_service = FormFieldService(db_session)

            # Initialize Redis-backed managers
            redis_client = get_redis()
            redis_url = config["redis_url"]

            conversation_manager = ConversationManager(
                redis_client=redis_client,
                redis_url=redis_url,
                ttl_seconds=1800,  # 30 minutes
            )
            form_state_manager = FormStateManager(
                redis_client=redis_client, ttl_seconds=1800
            )

            # Initialize tool
            tool = CreateOrUpdateFormTool(
                llm_client=llm_client,
                conversation_manager=conversation_manager,
                form_state_manager=form_state_manager,
                signup_form_service=signup_form_service,
                form_field_service=form_field_service,
            )

            # Execute conversational flow
            return await tool.execute(user=user, message=message)

        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error in create_or_update_form: {e}")
        return f"Error processing your request: {str(e)}"


# Create the ASGI app from the MCP server
mcp_app = mcp.http_app(path="/")
