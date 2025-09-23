"""GPT Actions router - REST API wrapper for MCP tools"""

from datetime import date, time
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import User, get_current_user
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.backends.postgres_client import PostgresClient
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.postgres_service import get_postgres_client
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.tools.create_form import create_form_handler, process_form_instruction
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
    title_contains: str | None = Field(
        default=None,
        description="Publish a draft whose title contains this text (fallback)",
    )


class CustomFieldUpdate(BaseModel):
    field_name: str
    field_type: str
    label: str
    placeholder: Optional[str] = None
    is_required: Optional[bool] = False
    options: Optional[List[str]] = None
    field_order: Optional[int] = None


class UpdateFormRequest(FormMutateRequest):
    update_description: str = Field(
        ..., description="Natural language description of what to change"
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


def _resolve_form_or_ask(
    signup_form_service: SignupFormService, user: User, req: FormMutateRequest
):
    """Resolve a target form by id/slug/title or fallback to latest draft.

    Returns: tuple(form, error_message)
      - If ambiguous or not found, returns (None, message).
    """
    # Direct lookups first
    if req.form_id:
        try:
            form = signup_form_service.get_form_by_id(UUID(req.form_id))
            return (form, None) if form else (None, "Form not found")
        except Exception:
            return (None, "Invalid form_id")

    if req.url_slug:
        form = signup_form_service.get_form_by_url_slug(req.url_slug)
        return (form, None) if form else (None, "Form not found")

    # Title based search among drafts
    if req.title_contains:
        matches = signup_form_service.search_draft_forms_by_title(
            user.user_id, req.title_contains
        )
        if not matches:
            return (None, "No draft form matching that title was found")
        if len(matches) > 1:
            listing = ", ".join(f"{m.title} (slug: {m.url_slug})" for m in matches[:5])
            return (
                None,
                f"Multiple draft forms match that title. Please specify the form by its URL slug. Candidates: {listing}",
            )
        return (matches[0], None)

    # Fallback: latest draft currently being designed
    latest = signup_form_service.get_latest_draft_form_for_user(user.user_id)
    if not latest:
        return (None, "No draft forms found to publish")
    return (latest, None)


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

    form, err = _resolve_form_or_ask(signup_form_service, user, request)
    if not form:
        raise HTTPException(status_code=400, detail=err or "Form not found")
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

    form, err = _resolve_form_or_ask(signup_form_service, user, request)
    if not form:
        raise HTTPException(status_code=400, detail=err or "Form not found")
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
    "/update-form",
    summary="Update a draft form (core fields and custom fields)",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": True},
)
async def gpt_update_form(
    request: UpdateFormRequest,
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """Update a draft form using LLM-extracted update spec.

    If no identifier is provided, updates the user's latest draft.
    """
    signup_form_service = SignupFormService(db_session)
    form, err = _resolve_form_or_ask(signup_form_service, user, request)
    if not form:
        raise HTTPException(status_code=400, detail=err or "Form not found")
    if form.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this form")
    if form.status == FormStatus.ARCHIVED:
        raise HTTPException(status_code=409, detail="Archived forms cannot be updated")

    # Build current form snapshot
    ff = FormFieldService(db_session)
    current_fields = ff.get_fields_by_form_id(form.id)
    fields_desc = "\n".join(
        f"- {f.field_name} [{f.field_type}] label='{f.label}' required={f.is_required}"
        for f in current_fields
    )
    current_summary = f"""
CURRENT FORM SNAPSHOT:
Title: {form.title}
Date: {form.event_date}
Start Time: {form.start_time or ''}
End Time: {form.end_time or ''}
Location: {form.location}
Description: {form.description or ''}
Button Type: {form.button_type}
Primary Button: {form.primary_button_text}
Secondary Button: {form.secondary_button_text or ''}
Custom Fields:
{fields_desc if fields_desc else '- none'}
"""

    user_message = (
        current_summary
        + "\nUPDATE INSTRUCTIONS:\n"
        + request.update_description
        + "\n\nTASK: Produce a complete form spec using the same JSON schema as initial creation (FORM_BUILDER_PROMPT). Include all fields (not only changes)."
    )

    # Ask LLM to produce the full extracted data
    llm_resp = await process_form_instruction(
        llm_client=llm_client, user_message=user_message
    )
    extracted = llm_resp.extracted_data

    # Map extracted data to update payload
    updated_data: dict = {}
    if extracted.title:
        updated_data["title"] = extracted.title
    if extracted.description is not None:
        updated_data["description"] = extracted.description
    if extracted.location is not None:
        updated_data["location"] = extracted.location
    # Button config
    if getattr(extracted, "button_config", None):
        bc = extracted.button_config
        if bc.button_type:
            updated_data["button_type"] = bc.button_type
        if bc.primary_button_text:
            updated_data["primary_button_text"] = bc.primary_button_text
        if bc.secondary_button_text is not None:
            updated_data["secondary_button_text"] = bc.secondary_button_text
    # Date/time
    try:
        if extracted.event_date:
            updated_data["event_date"] = date.fromisoformat(extracted.event_date)
        if extracted.start_time:
            updated_data["start_time"] = time.fromisoformat(extracted.start_time)
        if extracted.end_time:
            updated_data["end_time"] = time.fromisoformat(extracted.end_time)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date/time from LLM: {e}")

    # Apply core updates
    if updated_data:
        result = signup_form_service.update_signup_form(form.id, updated_data)
        if not result.get("success"):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Update failed")
            )

    # Upsert custom fields if provided
    custom_summary = None
    if getattr(extracted, "custom_fields", None) is not None:
        counts = ff.upsert_form_fields(
            form.id,
            [
                cf.dict() if hasattr(cf, "dict") else dict(cf)
                for cf in extracted.custom_fields
            ],
        )
        db_session.commit()
        custom_summary = f"custom fields updated: created={counts['created']}, updated={counts['updated']}"

    parts = []
    if updated_data:
        parts.append("core fields updated")
    if custom_summary:
        parts.append(custom_summary)
    if not parts:
        parts.append("no changes provided")
    return GPTResponse(response=", ".join(parts) + ".")


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
