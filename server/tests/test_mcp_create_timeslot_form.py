"""MCP tool test for creating a timeslot-based form (MR-TS-5).

Note: This test exercises the MCP create_or_update_form tool end-to-end and thus
depends on the LLM to extract a timeslot_schedule. It is skipped by default
in CI unless the environment provides a working LLM key and stable behavior.
"""

import uuid
from datetime import datetime, timezone
from http import HTTPStatus

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services import TimeslotService
from ez_scheduler.services.signup_form_service import SignupFormService


@pytest.mark.asyncio
async def test_mcp_create_timeslot_form(
    mcp_client,
    signup_service: SignupFormService,
    timeslot_service: TimeslotService,
    authenticated_client,
):
    user_id = f"auth0|{uuid.uuid4()}"

    # Use explicit schedule (UTC) for deterministic counts: 4 slots/day * 2 days/week * 2 weeks = 16
    initial_request = (
        "Create a signup form for 1-1 soccer coaching between 17:00 and 21:00 on Mondays and Wednesdays "
        "with 60 minute slots for the next 2 weeks, starting 2026-10-05. Time zone UTC. "
        "Location is City Park field. Keep fields to name, email, and phone. Limit 1 registration per slot."
    )

    # Call MCP tool
    draft_form = None
    async with Client(mcp_client) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "create_or_update_form" in tool_names
        assert "publish_form" not in tool_names
        result = await client.call_tool(
            "create_or_update_form", {"user_id": user_id, "message": initial_request}
        )

        # Normalize string result for sanity check
        message = (
            result
            if isinstance(result, str)
            else getattr(result, "data", None) or str(result)
        )
        assert isinstance(message, str) and len(message) > 0

        # Confirm completeness so the publish tool has the form in context
        finalize_result = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": user_id,
                "message": "Thanks, that covers everything. Save the form now so I can publish it.",
            },
        )
        finalize_message = (
            finalize_result
            if isinstance(finalize_result, str)
            else getattr(finalize_result, "data", None) or str(finalize_result)
        )
        assert isinstance(finalize_message, str) and len(finalize_message) > 0

        draft_form = signup_service.get_latest_draft_form_for_user(user_id)
        assert draft_form is not None, "Expected a draft form to be created via MCP"

        # Publish via service to simulate browser-based publish flow
        publish_result = signup_service.update_signup_form(
            draft_form.id, {"status": FormStatus.PUBLISHED}
        )
        assert publish_result.get("success"), publish_result.get("error")

    # Verify the form has been published
    assert draft_form is not None
    form = signup_service.reload_form(draft_form.id)
    assert form is not None, "Expected the form to be persisted via MCP"

    # Verify expected number of timeslots generated (16 total for the schedule above)
    # Use a fixed 'now' before the schedule start so all are considered available
    avail_for_count = timeslot_service.list_available(
        form.id, now=datetime(2025, 10, 1, 12, 0, tzinfo=timezone.utc)
    )
    assert (
        len(avail_for_count) == 16
    ), f"Expected 16 slots, found {len(avail_for_count)}"

    assert form.status == FormStatus.PUBLISHED

    # Book a couple of timeslots via public POST and verify they are no longer available
    avail = timeslot_service.list_available(form.id)
    assert len(avail) >= 2
    to_book = [avail[0].id, avail[1].id]

    client, _ = authenticated_client
    payload = {
        "name": "Alice",
        "email": "vb@signuppro.ai",
        "timeslot_ids": [str(to_book[0]), str(to_book[1])],
    }
    client.get(f"/form/{form.url_slug}")
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token, "Expected csrftoken cookie before submission"

    resp = client.post(
        f"/form/{form.url_slug}",
        data=payload,
        headers={"X-CSRFToken": csrf_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("success") is True
    booked_returned = set(body.get("timeslot_ids", []))
    assert {str(to_book[0]), str(to_book[1])}.issubset(booked_returned)

    # Try to register for the same slot again — should be disallowed by the server
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token, "Expected csrftoken cookie before submission"

    resp2 = client.post(
        f"/form/{form.url_slug}",
        data={
            "name": "Bob",
            "email": "bob@example.com",
            "timeslot_ids": [str(to_book[0])],
        },
        headers={"X-CSRFToken": csrf_token},
    )
    # Endpoint returns a client error (conflict); some flows use 409, others may normalize to 400
    assert resp2.status_code == HTTPStatus.CONFLICT, resp2.text


@pytest.mark.asyncio
async def test_mcp_create_timeslot_form_capacity_two(
    mcp_client,
    signup_service: SignupFormService,
    timeslot_service: TimeslotService,
    authenticated_client,
):
    user_id = f"auth0|{uuid.uuid4()}"

    # Explicit capacity 2 for deterministic behavior
    initial_request = (
        "Create a signup form for beginner yoga classes between 17:00 and 21:00 on Mondays and Wednesdays "
        "with 60 minute slots for the next 2 weeks, starting 2026-10-05. Time zone UTC. "
        "Location is Community Center. Keep fields to name, email, and phone. Limit 2 registration per slot."
    )

    draft_form = None
    async with Client(mcp_client) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "create_or_update_form" in tool_names
        assert "publish_form" not in tool_names
        result = await client.call_tool(
            "create_or_update_form", {"user_id": user_id, "message": initial_request}
        )

        msg = (
            result
            if isinstance(result, str)
            else getattr(result, "data", None) or str(result)
        )
        assert isinstance(msg, str) and len(msg) > 0

        finalize_result = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": user_id,
                "message": "Looks good. Please finalize this form so I can publish it.",
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

        publish_result = signup_service.update_signup_form(
            draft_form.id, {"status": FormStatus.PUBLISHED}
        )
        assert publish_result.get("success"), publish_result.get("error")

    assert draft_form is not None
    form = signup_service.reload_form(draft_form.id)
    assert form is not None

    # 16 slots available before the schedule, same as above
    avail_for_count = timeslot_service.list_available(
        form.id, now=datetime(2025, 10, 1, 12, 0, tzinfo=timezone.utc)
    )
    assert len(avail_for_count) == 16

    assert form.status == FormStatus.PUBLISHED

    # Choose a slot and book twice successfully, third attempt should fail
    avail = timeslot_service.list_available(form.id)
    assert len(avail) >= 1
    target = str(avail[0].id)

    client, _ = authenticated_client

    # First booking
    r1 = client.post(
        f"/form/{form.url_slug}",
        data={"name": "P1", "phone": "123", "timeslot_ids": [target]},
    )
    assert r1.status_code == 200, r1.text

    # Second booking (capacity 2)
    r2 = client.post(
        f"/form/{form.url_slug}",
        data={"name": "P2", "phone": "234", "timeslot_ids": [target]},
    )
    assert r2.status_code == 200, r2.text

    # Third booking should be rejected
    r3 = client.post(
        f"/form/{form.url_slug}",
        data={"name": "P3", "phone": "567", "timeslot_ids": [target]},
    )
    assert r3.status_code == HTTPStatus.CONFLICT, r3.text
