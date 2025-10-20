"""Tests for MCP create_or_update_form tool"""

import uuid
from datetime import date

import pytest
from fastmcp.client import Client


@pytest.mark.asyncio
async def test_update_form_updates_title_and_location(mcp_client, signup_service):
    """Create via LLM (MCP create_or_update_form), then update in same conversation."""

    user_id = f"auth0|{uuid.uuid4()}"

    # Use a single MCP client context to maintain conversation state
    async with Client(mcp_client) as client:
        # Step 1: Create the form via MCP create_or_update_form (LLM-driven)
        initial_message = (
            "Create a signup form for a tennis conference for on "
            "next Sunday from 1pm-5pm at Wimbledon. Only include name, email and phone number"
            " in the form. No other fields are necessary There is no limit on maximum participants."
        )

        create_result = await client.call_tool(
            "create_or_update_form", {"user_id": user_id, "message": initial_message}
        )

        # FastMCP returns a CallToolResult; normalize to message for sanity check
        if isinstance(create_result, str):
            create_message = create_result
        else:
            create_message = getattr(create_result, "data", None) or str(create_result)
        assert isinstance(create_message, str) and len(create_message) > 0

        # Verify the form exists in DB by looking up latest draft for this user
        created_form = signup_service.get_latest_draft_form_for_user(user_id)
        assert created_form is not None, "Form should be created in DB"
        form_id = created_form.id

        # Step 2: Update the form via MCP create_or_update_form in same conversation
        new_title = "Soccer conference"
        new_location = "Wembley Stadium"
        update_message = (
            f"Update the form: change the title to '{new_title}' "
            f"and change the location to '{new_location}'."
        )

        update_result = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": user_id,
                "message": update_message,
            },
        )

        if isinstance(update_result, str):
            result_message = update_result
        else:
            result_message = getattr(update_result, "data", None) or str(update_result)
        assert isinstance(result_message, str)

    # Step 3: Verify DB reflects updates
    # Refresh the session to see committed changes from MCP server's database connection
    refreshed = signup_service.reload_form(form_id)
    assert refreshed is not None, f"Form {form_id} should exist"

    # Verify the updates were applied
    assert (
        refreshed.title.lower() == new_title.lower()
    ), f"Title should be updated to '{new_title}', got '{refreshed.title}'"
    assert (
        new_location.lower() in refreshed.location.lower()
    ), f"Location should contain '{new_location}', got '{refreshed.location}'"
