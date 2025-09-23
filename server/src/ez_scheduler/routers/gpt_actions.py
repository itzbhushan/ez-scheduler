"""GPT Actions router - REST API wrapper for MCP tools"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import User, get_current_user
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
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


class FormMutateRequest(BaseModel):
    form_id: str | None = Field(
        default=None, description="UUID of the form (optional if url_slug provided)"
    )
    url_slug: str | None = Field(
        default=None, description="URL slug of the form (optional if form_id provided)"
    )


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


def _get_form_by_identifier(
    signup_form_service: SignupFormService, req: FormMutateRequest
):
    form = None
    if req.form_id:
        try:
            import uuid as _uuid

            form = signup_form_service.db.get(
                __import__(
                    "ez_scheduler.models.signup_form", fromlist=["SignupForm"]
                ).SignupForm,
                _uuid.UUID(req.form_id),
            )
        except Exception:
            form = None
    if not form and req.url_slug:
        form = signup_form_service.get_form_by_url_slug(req.url_slug)
    return form


@router.post(
    "/publish-form",
    summary="Publish a draft form",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": True},
)
async def gpt_publish_form(
    request: FormMutateRequest,
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
):
    signup_form_service = SignupFormService(db_session)

    form = _get_form_by_identifier(signup_form_service, request)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    if form.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this form")
    if form.status == FormStatus.ARCHIVED:
        raise HTTPException(
            status_code=409, detail="Archived forms cannot be published"
        )
    if form.status == FormStatus.PUBLISHED:
        return GPTResponse(response="This form is already published.")

    result = signup_form_service.update_signup_form(
        form.id, {"status": FormStatus.PUBLISHED}
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Publish failed")
        )
    return GPTResponse(response="Form published successfully.")


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

    form = _get_form_by_identifier(signup_form_service, request)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    if form.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this form")
    if form.status == FormStatus.ARCHIVED:
        return GPTResponse(response="This form is already archived.")

    result = signup_form_service.update_signup_form(
        form.id, {"status": FormStatus.ARCHIVED}
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Archive failed")
        )
    return GPTResponse(response="Form archived successfully.")


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
