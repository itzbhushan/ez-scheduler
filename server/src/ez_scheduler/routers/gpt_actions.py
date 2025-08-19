"""GPT Actions router - REST API wrapper for MCP tools"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ez_scheduler.models.database import get_db
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.postgres_mcp_service import get_postgres_mcp_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler
from ez_scheduler.tools.get_form_analytics import get_form_analytics_handler

router = APIRouter(prefix="/gpt", tags=["GPT Actions"])

# Shared services (reuse existing pattern)
db_session = next(get_db())
llm_client = get_llm_client()
signup_form_service = SignupFormService(db_session)
postgres_mcp_client = get_postgres_mcp_client(llm_client)


class GPTFormRequest(BaseModel):
    user_id: uuid.UUID = Field(
        ...,
        description="Unique identifier for the user creating the form",
        example="123e4567-e89b-12d3-a456-426614174000",
    )
    description: str = Field(
        ...,
        description="Natural language description of the event form to create",
        example="Create a form for John's birthday party on December 15th at 6 PM at Central Park",
    )


class GPTAnalyticsRequest(BaseModel):
    user_id: uuid.UUID = Field(
        ...,
        description="Unique identifier for the user requesting analytics",
        example="123e4567-e89b-12d3-a456-426614174000",
    )
    query: str = Field(
        ...,
        description="Natural language query about form analytics",
        example="How many people have registered for the birthday party?",
    )


class GPTResponse(BaseModel):
    response: str = Field(..., description="Response message for the user")


@router.post(
    "/create-form",
    summary="Create Signup Form",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": False},
)
async def gpt_create_form(request: GPTFormRequest):
    """
    Create a signup form using natural language description.

    This endpoint wraps the existing MCP create_form tool to provide
    REST API access for ChatGPT Custom GPTs.
    """
    response_text = await create_form_handler(
        user_id=request.user_id,
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
async def gpt_analytics(request: GPTAnalyticsRequest):
    """
    Get analytics about forms and registrations using natural language queries.

    This endpoint wraps the existing MCP analytics tool to provide
    REST API access for ChatGPT Custom GPTs.
    """
    response_text = await get_form_analytics_handler(
        user_id=request.user_id,
        analytics_query=request.query,
        postgres_mcp_client=postgres_mcp_client,
        llm_client=llm_client,
    )
    return GPTResponse(response=response_text)
