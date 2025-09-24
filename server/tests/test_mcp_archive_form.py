"""Tests for MCP archive_form tool"""

import uuid

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus, SignupForm


@pytest.mark.asyncio
async def test_archive_draft_form_success(mcp_client, signup_service):
    user_id = f"auth0|{uuid.uuid4()}"
    slug = f"draft-to-archive-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=user_id,
        title="Archive Test",
        event_date=__import__("datetime").date.today(),
        location="Venue",
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
            "archive_form",
            {"user_id": user_id, "form_id": str(form.id)},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "archived successfully" in message.lower()

    refreshed = signup_service.reload_form(form.id)
    assert refreshed is not None
    assert refreshed.status == FormStatus.ARCHIVED


@pytest.mark.asyncio
async def test_archive_published_form_success(mcp_client, signup_service):
    user_id = f"auth0|{uuid.uuid4()}"
    slug = f"published-to-archive-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=user_id,
        title="To Archive",
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
            "archive_form",
            {"user_id": user_id, "form_id": str(form.id)},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "archived successfully" in message.lower()

    refreshed = signup_service.reload_form(form.id)
    assert refreshed is not None
    assert refreshed.status == FormStatus.ARCHIVED


@pytest.mark.asyncio
async def test_archive_idempotent(mcp_client, signup_service):
    user_id = f"auth0|{uuid.uuid4()}"
    slug = f"already-archived-{uuid.uuid4().hex[:8]}"

    form = SignupForm(
        user_id=user_id,
        title="Already Archived",
        event_date=__import__("datetime").date.today(),
        location="V",
        description="",
        url_slug=slug,
        status=FormStatus.ARCHIVED,
        button_type="single_submit",
        primary_button_text="Register",
    )
    res = signup_service.create_signup_form(form)
    assert res["success"], res

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "archive_form",
            {"user_id": user_id, "form_id": str(form.id)},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "already archived" in message.lower()


@pytest.mark.asyncio
async def test_archive_requires_ownership(mcp_client, signup_service):
    owner = f"auth0|{uuid.uuid4()}"
    not_owner = f"auth0|{uuid.uuid4()}"
    slug = f"ownership-archive-{uuid.uuid4().hex[:8]}"

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
            "archive_form",
            {"user_id": not_owner, "url_slug": slug},
        )

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "do not own" in message.lower() or "permission" in message.lower()
