import logging
from uuid import UUID

from fastmcp import FastMCP

from ez_scheduler.auth.models import User
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.routers.request_validator import (
    resolve_form_or_ask,
    validate_publish_allowed,
)
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler, update_form_handler
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


@mcp.tool()
async def update_form(
    user_id: str,
    update_description: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    """Update a draft form using natural language.

    - Resolution order: `form_id → url_slug → title_contains (drafts) → latest draft`.
    - Permissions: Only the form owner may update; archived forms are not editable.
    - Behavior: Delegates to the existing update handler to modify core fields
      (title, date/time, location, description, button config) and custom fields.
      Returns a message with the preview URL and publish guidance.

    Args:
        user_id: Auth0 user identifier (e.g., "auth0|123").
        update_description: Natural language instructions describing the changes.
        form_id: Optional UUID of the target form.
        url_slug: Optional URL slug of the target form.
        title_contains: Optional substring to match a single draft title.

    Returns:
        Text response describing the result and preview URL.

    Example:
        update_form(user_id="auth0|abc", update_description="Change title to 'Team Offsite' and add guest_count field", url_slug="team-offsite-1234")
    """
    llm_client = get_llm_client()

    # Create User for the handler
    user = User(user_id=user_id, claims={})

    try:
        db_session = next(get_db())
        try:
            signup_form_service = SignupFormService(db_session)
            form_field_service = FormFieldService(db_session)
            return await update_form_handler(
                user=user,
                update_description=update_description,
                llm_client=llm_client,
                signup_form_service=signup_form_service,
                form_field_service=form_field_service,
                form_id=form_id,
                url_slug=url_slug,
                title_contains=title_contains,
            )
        finally:
            db_session.close()
    except Exception as e:
        return f"Error updating form: {str(e)}"


# New MCP tool: publish_form
@mcp.tool()
async def publish_form(
    user_id: str,
    form_id: str | None = None,
    url_slug: str | None = None,
    title_contains: str | None = None,
) -> str:
    """Publish a draft form so it accepts registrations.

    - Resolution order: `form_id → url_slug → title_contains (drafts) → latest draft`.
    - Permissions: Only the form owner may publish; archived forms cannot be published.
    - Idempotent: If already published, returns a no-op message.

    Args:
        user_id: Auth0 user identifier (e.g., "auth0|123").
        form_id: Optional UUID of the target form.
        url_slug: Optional URL slug of the target form.
        title_contains: Optional substring to match a single draft title.

    Returns:
        Text message describing the result.
    """
    # Create User for the handler
    user = User(user_id=user_id, claims={})
    try:
        db_session = next(get_db())
        try:
            signup_form_service = SignupFormService(db_session)

            # Resolve target form using shared helper
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

            # Status/ownership checks
            err = validate_publish_allowed(form, user)
            if err:
                return err
            if form.status == FormStatus.PUBLISHED:
                return "This form is already published"

            # Update status to published
            result = signup_form_service.update_signup_form(
                form.id, {"status": FormStatus.PUBLISHED}
            )
            if not result.get("success"):
                return f"Publish failed: {result.get('error', 'unknown error')}"
            return "Form published successfully"
        finally:
            db_session.close()
    except Exception as e:
        return f"Error publishing form: {str(e)}"


# Create the ASGI app from the MCP server
mcp_app = mcp.http_app(path="/")
