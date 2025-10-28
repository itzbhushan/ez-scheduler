"""GPT Actions router - REST API wrapper for MCP tools"""

import logging
from datetime import date, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from ez_scheduler.auth.dependencies import (
    User,
    get_current_user,
    get_current_user_optional,
)
from ez_scheduler.auth.models import is_user_anonymous, resolve_effective_user_id
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db, get_redis
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.routers.request_validator import resolve_form_or_ask
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.form_state_manager import FormStateManager
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.postgres_service import get_postgres_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_or_update_form import CreateOrUpdateFormTool
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler

router = APIRouter(prefix="/gpt", tags=["GPT Actions"])


class GPTAnalyticsRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query about form analytics",
        json_schema_extra={
            "example": "How many people have registered for the birthday party?"
        },
    )


class GPTConversationRequest(BaseModel):
    message: str = Field(
        ...,
        description="Conversational message for form creation or updates",
        json_schema_extra={
            "example": "I want to create a form for my birthday party on December 15th"
        },
    )
    user_id: Optional[str] = Field(
        None,
        description="Anonymous user ID from previous response (for Custom GPTs to maintain conversation)",
    )


class GPTResponse(BaseModel):
    response: str = Field(..., description="Response message for the user")
    user_id: Optional[str] = Field(
        None,
        description="User ID for anonymous users (pass in next request to continue conversation). None for authenticated users.",
    )


class FormMutateRequest(BaseModel):
    form_id: str | None = Field(
        default=None, description="UUID of the form (optional if url_slug provided)"
    )
    url_slug: str | None = Field(
        default=None, description="URL slug of the form (optional if form_id provided)"
    )
    title_contains: str | None = Field(
        default=None,
        description="Publish a draft whose title contains this text (fallback)",
    )


@router.post(
    "/archive-form",
    summary="Archive a form (removes from public view)",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": True},
)
async def gpt_archive_form(
    request: FormMutateRequest,
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
):
    signup_form_service = SignupFormService(db_session)

    form = resolve_form_or_ask(
        signup_form_service,
        user,
        form_id=request.form_id,
        url_slug=request.url_slug,
        title_contains=request.title_contains,
        fallback_latest=True,
    )
    if not form:
        raise HTTPException(status_code=400, detail="Form not found")
    if form.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this form")
    if form.status == FormStatus.ARCHIVED:
        return GPTResponse(
            response="This form is already archived.",
            user_id=None,
        )

    result = signup_form_service.update_signup_form(
        form.id, {"status": FormStatus.ARCHIVED}
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Archive failed")
        )
    return GPTResponse(response="Form archived successfully.", user_id=None)


@router.post(
    "/analytics",
    summary="Get Form Analytics",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": False},
)
async def gpt_analytics(
    request: GPTAnalyticsRequest,
    user: User = Depends(get_current_user),
    postgres_client: PostgresClient = Depends(get_postgres_client),
):
    """
    Get analytics about forms and registrations using natural language queries.

    This endpoint uses high-performance PostgreSQL client for direct database access.
    """
    response_text = await get_form_analytics_handler(
        user=user,
        analytics_query=request.query,
        postgres_client=postgres_client,
    )
    return GPTResponse(response=response_text, user_id=None)


@router.post(
    "/create-or-update-form",
    summary="Create or Update Form",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": False},
)
async def gpt_create_or_update_form(
    request: GPTConversationRequest,
    auth_user: Optional[User] = Depends(get_current_user_optional),
    db_session=Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    redis_client=Depends(get_redis),
) -> GPTResponse:
    """
    Unified conversational endpoint for creating or updating forms.

    - Automatically detects active or new conversations for the user
    - Creates new draft forms when conversation is complete
    - Seamlessly handles multi-turn conversations
    - Supports anonymous users with anon|{uuid} IDs
    """
    # Resolve effective user_id with security checks
    effective_user_id = resolve_effective_user_id(
        auth_user=auth_user, request_user_id=request.user_id
    )

    logger.info(f"Effective user_id for conversation: {effective_user_id}")

    user = User(user_id=effective_user_id, claims=auth_user.claims if auth_user else {})

    # Initialize services
    signup_form_service = SignupFormService(db_session)
    form_field_service = FormFieldService(db_session)

    # Initialize conversation and state managers
    redis_url = config["redis_url"]
    conversation_manager = ConversationManager(
        redis_client=redis_client, redis_url=redis_url, ttl_seconds=1800
    )
    form_state_manager = FormStateManager(redis_client=redis_client, ttl_seconds=1800)

    # Initialize the tool
    tool = CreateOrUpdateFormTool(
        llm_client=llm_client,
        conversation_manager=conversation_manager,
        form_state_manager=form_state_manager,
        signup_form_service=signup_form_service,
        form_field_service=form_field_service,
    )

    # Execute the conversation
    response_text = await tool.execute(user=user, message=request.message)

    # TODO: According to chat gpt best practices, return a JSON response
    # instead of a human readable string. he GPT will provide its own natural
    # language response using the returned data.

    # Only return user_id for anonymous users (Custom GPTs need to remember it)
    return_user_id = user.user_id if is_user_anonymous(user) else None
    return GPTResponse(response=response_text, user_id=return_user_id)
