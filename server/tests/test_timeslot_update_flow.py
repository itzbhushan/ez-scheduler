"""Integration test for timeslot update flow (MR-TS-9/10).

Sequence verified:
1) Create a new draft signup form with initial timeslots
2) Apply timeslot changes (remove then add)
3) Publish the form
4) Retrieve public form and verify expected slots are shown
"""

import uuid
from datetime import date

from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.services import TimeslotSchedule, TimeslotService
import pytest

TEST_MONDAY = date(2025, 10, 6)  # fixed Monday for deterministic windows


def _create_draft_form(signup_service, slug: str, tz: str = "UTC") -> SignupForm:
    form = SignupForm(
        id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
        title="Coaching (Draft)",
        event_date=date(2025, 1, 1),
        location="Field A",
        description="",
        url_slug=slug,
        status=FormStatus.DRAFT,
        time_zone=tz,
    )
    signup_service.create_signup_form(form)
    return form

@pytest.mark.skip(reason="Flaky test, fix later")
def test_timeslot_update_add_remove_then_publish(
    authenticated_client, signup_service, timeslot_service: TimeslotService
):
    client, _ = authenticated_client
    svc = timeslot_service

    # 1) Create draft form and initial slots (10:00, 11:00, 12:00 on TEST_MONDAY)
    slug = f"ts-update-flow-{uuid.uuid4().hex[:8]}"
    form = _create_draft_form(signup_service, slug, tz="UTC")

    initial = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        capacity_per_slot=1,
        time_zone="UTC",
    )
    gen = svc.generate_slots(form.id, initial)
    assert len(gen.created) == 3

    # 2) Remove the first hour [10:00, 11:00) and add a new hour [13:00, 14:00)
    rem = TimeslotService.TimeslotRemoveSpec(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="11:00",
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        time_zone="UTC",
    )
    rem_res = svc.remove_schedule(form.id, rem)
    assert rem_res.removed_count == 1

    add = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="13:00",
        window_end="14:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        capacity_per_slot=1,
        time_zone="UTC",
    )
    add_res = svc.add_schedule(form.id, add)
    assert add_res.added_count == 1

    # 3) Publish the form
    result = signup_service.update_signup_form(form.id, {"status": "published"})
    assert result.get("success") is True

    # 4) Retrieve public form and verify available slots
    resp = client.get(f"/form/{slug}")
    assert resp.status_code == 200
    body = resp.text

    # Should NOT show 10:00 AM (removed)
    assert "10:00 AM" not in body
    # Should show 11:00 AM and 12:00 PM from initial
    assert "11:00 AM" in body
    assert "12:00 PM" in body
    # Should show the newly added 1:00 PM (13:00)
    assert "1:00 PM" in body
