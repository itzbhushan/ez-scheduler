"""Tests for MCP publish_form tool"""

import uuid

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus, SignupForm


@pytest.mark.asyncio
async def test_publish_draft_form_success(mcp_client, signup_service):
    """Create a draft form in DB, publish via MCP, and verify status."""
    user_id = f"auth0|{uuid.uuid4()}"
    slug = f"draft-to-publish-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=user_id,
        title="Publish Test",
        event_date=__import__("datetime").date.today(),
        location="Test Venue",
        description="Desc",
        url_slug=slug,
        status=FormStatus.DRAFT,
        button_type="single_submit",
        primary_button_text="Register",
    )
    res = signup_service.create_signup_form(form)
    assert res["success"], res

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "publish_form",
            {"user_id": user_id, "url_slug": slug},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "published" in message.lower()

    refreshed = signup_service.reload_form(form.id)
    assert refreshed is not None
    assert refreshed.status == FormStatus.PUBLISHED


@pytest.mark.asyncio
async def test_publish_form_idempotent(mcp_client, signup_service):
    user_id = f"auth0|{uuid.uuid4()}"
    slug = f"already-published-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=user_id,
        title="Already Published",
        event_date=__import__("datetime").date.today(),
        location="Venue",
        description="",
        url_slug=slug,
        status=FormStatus.PUBLISHED,
        button_type="single_submit",
        primary_button_text="Register",
    )
    res = signup_service.create_signup_form(form)
    assert res["success"], res

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "publish_form",
            {"user_id": user_id, "url_slug": slug},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "already published" in message.lower()


@pytest.mark.asyncio
async def test_publish_archived_form_blocked(mcp_client, signup_service):
    user_id = f"auth0|{uuid.uuid4()}"
    other_user = f"auth0|{uuid.uuid4()}"

    archived = SignupForm(
        user_id=user_id,
        title="Archived",
        event_date=__import__("datetime").date.today(),
        location="X",
        description="",
        url_slug=f"archived-{uuid.uuid4().hex[:8]}",
        status=FormStatus.ARCHIVED,
        button_type="single_submit",
        primary_button_text="Register",
    )
    res = signup_service.create_signup_form(archived)
    assert res["success"], res

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "publish_form",
            {"user_id": user_id, "form_id": str(archived.id)},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "cannot be published" in message.lower()


@pytest.mark.asyncio
async def test_publish_requires_ownership(mcp_client, signup_service):
    owner = f"auth0|{uuid.uuid4()}"
    not_owner = f"auth0|{uuid.uuid4()}"
    slug = f"ownership-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=owner,
        title="Ownership",
        event_date=__import__("datetime").date.today(),
        location="Y",
        description="",
        url_slug=slug,
        status=FormStatus.DRAFT,
        button_type="single_submit",
        primary_button_text="Register",
    )
    res = signup_service.create_signup_form(form)
    assert res["success"], res

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "publish_form",
            {"user_id": not_owner, "url_slug": slug},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "do not own" in message.lower() or "permission" in message.lower()
