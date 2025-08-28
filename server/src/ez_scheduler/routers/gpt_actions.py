"""GPT Actions router - REST API wrapper for MCP tools"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import User, get_current_user
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.models.database import get_db
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.postgres_service import get_postgres_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler

router = APIRouter(prefix="/gpt", tags=["GPT Actions"])


class GPTFormRequest(BaseModel):
    description: str = Field(
        ...,
        description="Natural language description of the event form to create",
        json_schema_extra={
            "example": "Create a form for John's birthday party on December 15th at 6 PM at Central Park"
        },
    )


class GPTAnalyticsRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query about form analytics",
        json_schema_extra={
            "example": "How many people have registered for the birthday party?"
        },
    )


class GPTResponse(BaseModel):
    response: str = Field(..., description="Response message for the user")


@router.post(
    "/create-form",
    summary="Create Signup Form",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": False},
)
async def gpt_create_form(
    request: GPTFormRequest,
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Create a signup form using natural language description.

    This endpoint wraps the existing MCP create_form tool to provide
    REST API access for ChatGPT Custom GPTs.
    """
    signup_form_service = SignupFormService(db_session)

    response_text = await create_form_handler(
        user=user,
        initial_request=request.description,
        llm_client=llm_client,
        signup_form_service=signup_form_service,
    )
    return GPTResponse(response=response_text)


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
    return GPTResponse(response=response_text)
