"""Tests for MCP publish_form tool"""

import uuid

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus


@pytest.mark.asyncio
async def test_publish_draft_form_success(mcp_client, signup_service):
    """Create a form via MCP conversation and publish it through the MCP tool."""
    user_id = f"auth0|{uuid.uuid4()}"
    create_request = (
        "Create a signup form titled Product Launch Party scheduled for July 20, 2025 "
        "from 18:00 to 21:00 at the Innovation Hub in San Francisco. The description is "
        "'Celebrate with our team and learn about the new release.' Use the button text "
        "'RSVP Now' and set the time zone to America/Los_Angeles."
    )

    async with Client(mcp_client) as client:
        create_result = await client.call_tool(
            "create_or_update_form",
            {"user_id": user_id, "message": create_request},
        )

        create_message = (
            create_result
            if isinstance(create_result, str)
            else getattr(create_result, "data", None) or str(create_result)
        )
        assert isinstance(create_message, str) and len(create_message) > 0

        # Confirm the assistant can finish the conversation when details are complete.
        finalize_result = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": user_id,
                "message": "Those details are correct. Please finalize the form now.",
            },
        )

        finalize_message = (
            finalize_result
            if isinstance(finalize_result, str)
            else getattr(finalize_result, "data", None) or str(finalize_result)
        )
        assert isinstance(finalize_message, str) and len(finalize_message) > 0

        draft_form = signup_service.get_latest_draft_form_for_user(user_id)
        assert draft_form is not None
        assert draft_form.status == FormStatus.DRAFT

        # Publish the form from the active conversation context
        publish_result = await client.call_tool("publish_form", {"user_id": user_id})

    publish_message = (
        publish_result
        if isinstance(publish_result, str)
        else getattr(publish_result, "data", None) or str(publish_result)
    )
    assert publish_message == "Form published successfully!"

    refreshed = signup_service.reload_form(draft_form.id)
    assert refreshed is not None
    assert refreshed.status == FormStatus.PUBLISHED


@pytest.mark.asyncio
async def test_publish_requires_active_conversation(mcp_client):
    """Publishing without a prior conversation should prompt the user to create one."""
    user_id = f"auth0|{uuid.uuid4()}"

    async with Client(mcp_client) as client:
        result = await client.call_tool("publish_form", {"user_id": user_id})

    message = (
        result if isinstance(result, str) else getattr(result, "data", str(result))
    )
    assert "no active form conversation" in message.lower()
