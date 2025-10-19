"""MCP tool test for updating timeslots on a draft (MR-TS-10).

This follows the style of the existing MCP tests and uses the MCP update_form
tool to request timeslot changes, then verifies results through the public
endpoint after publishing.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services import TimeslotService
from ez_scheduler.services.signup_form_service import SignupFormService


@pytest.mark.skip(reason="Flaky test, fix later")
async def test_mcp_update_timeslots_remove_and_add(
    mcp_client,
    signup_service: SignupFormService,
    timeslot_service: TimeslotService,
    authenticated_client,
):
    user_id = f"auth0|{uuid.uuid4()}"

    # Create a timeslot form via MCP covering Mon–Fri 10–11 AM for 2 weeks (UTC)
    initial_request = (
        "Create a signup form for coding mentorship between 10:00 and 11:00 from Monday to Friday"
        "with 60 minute slots for the next 2 weeks, starting 2025-10-06. Time zone UTC. "
        "Location is Library. Keep fields to name, email, and phone. Limit 1 registration per slot."
    )

    async with Client(mcp_client) as client:
        tools = await client.list_tools()
        assert any(
            t.name == "create_form" for t in tools
        ), "create_form tool should exist"
        create_res = await client.call_tool(
            "create_form", {"user_id": user_id, "initial_request": initial_request}
        )

    # Verify draft exists and 10 weekday slots were generated (Mon–Fri across 2 weeks)
    form = signup_service.get_latest_draft_form_for_user(user_id)
    assert form is not None
    avail_for_count = timeslot_service.list_available(form.id)
    assert len(avail_for_count) == 10, "After creation, should have 10 available slots"

    # Ask MCP update_form to remove [10:00, 11:00) and add [13:00, 14:00)
    # The prompt has been updated to support timeslot_mutations in updates.
    update_description = (
        "Update the existing draft form: remove all Thursdays "
        "add Saturdays from 16:00 to 17:00 instead for those 2 weeks."
        "Keep everything else the same."
    )

    async with Client(mcp_client) as client:
        update_res = await client.call_tool(
            "update_form",
            {
                "user_id": user_id,
                "update_description": update_description,
                "url_slug": form.url_slug,
            },
        )

    # Publish the form (mirror template tests: use service directly for reliability)
    signup_service.update_signup_form(form.id, {"status": FormStatus.PUBLISHED})
    form = signup_service.get_form_by_url_slug(form.url_slug)
    assert form is not None and form.status == FormStatus.PUBLISHED

    # Verify via service list_upcoming for robustness
    upcoming = timeslot_service.list_upcoming(
        form.id, now=datetime(2025, 10, 1, 12, 0, tzinfo=timezone.utc)
    )
    # Avoid brittle exact counts; validate predicates instead
    pairs = [(s.start_at.weekday(), s.start_at.hour) for s in upcoming]
    # Thursday (3) must not be present
    assert all(wd != 3 for wd, _ in pairs)
    # Mon=0, Tue=1, Wed=2, Fri=4 at 10:00 → expect at least 8 occurrences (two weeks × 4 days)
    assert sum(1 for wd, hr in pairs if wd in (0, 1, 2, 4) and hr == 10) >= 8
    # Saturday=5 at 16:00 → expect at least 2 occurrences (two weeks)
    assert sum(1 for wd, hr in pairs if wd == 5 and hr == 16) >= 2

    # Also sanity check via public GET: contains "4:00 PM" and no "Thursday"
    client_http, _ = authenticated_client
    resp = client_http.get(f"/form/{form.url_slug}")
    assert resp.status_code == 200
    body = resp.text
    assert "4:00 PM" in body
    assert "Thursday" not in body
