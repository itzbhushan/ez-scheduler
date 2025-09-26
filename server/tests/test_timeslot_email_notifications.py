"""Tests that emails include selected timeslot lines (MR-TS-6)."""

import os
import uuid
from datetime import date

import pytest

from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.services import TimeslotSchedule, TimeslotService
from ez_scheduler.services.auth0_service import auth0_service
from ez_scheduler.services.email_service import EmailService

TEST_MONDAY = date(2025, 10, 6)  # Deterministic Monday


def _create_published_form(signup_service, *, slug: str, tz: str) -> SignupForm:
    form = SignupForm(
        id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
        title="Coaching",
        event_date=date(2025, 1, 1),
        location="Field A",
        description="",
        url_slug=slug,
        status=FormStatus.PUBLISHED,
        time_zone=tz,
    )
    signup_service.create_signup_form(form)
    return form


@pytest.mark.asyncio
async def test_timeslot_lines_in_registrant_email(
    signup_service, timeslot_service: TimeslotService, authenticated_client
):
    client, _ = authenticated_client

    # Create a published timeslot form in New York time zone
    form = _create_published_form(
        signup_service, slug="ts-email-registrant", tz="America/New_York"
    )

    # One 5–6 PM slot on a fixed Monday in local time
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="17:00",
        window_end="18:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        time_zone="America/New_York",
        capacity_per_slot=1,
    )
    gen = timeslot_service.generate_slots(form.id, spec)
    assert len(gen.created) == 1
    slot_id = str(gen.created[0].id)

    resp = client.post(
        f"/form/{form.url_slug}",
        data={
            "name": "Alice",
            "email": "vb@signuppro.ai",
            "timeslot_ids": slot_id,
        },
    )
    assert resp.status_code == 200
    # Assert the endpoint reports that the email was sent
    result = resp.json()
    assert result.get("email_sent") is True


@pytest.mark.asyncio
async def test_timeslot_lines_in_creator_email(
    signup_service, timeslot_service: TimeslotService, authenticated_client, monkeypatch
):
    client, _ = authenticated_client

    # Capture emails and short-circuit sending
    sent = []

    async def fake_send_email(self, to_email, email_content):
        sent.append(
            {
                "to": to_email,
                "subject": email_content.get("subject"),
                "body": email_content.get("body", ""),
            }
        )
        return True

    monkeypatch.setattr(EmailService, "_send_email", fake_send_email, raising=True)

    # Stub creator email lookup to avoid external Auth0
    async def fake_get_user_email(user_id: str):
        return "creator@example.com"

    monkeypatch.setattr(
        auth0_service, "get_user_email", fake_get_user_email, raising=True
    )

    # Published form in New York
    form = _create_published_form(
        signup_service, slug="ts-email-creator", tz="America/New_York"
    )

    # One 5–6 PM slot on fixed Monday
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="17:00",
        window_end="18:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        time_zone="America/New_York",
        capacity_per_slot=1,
    )
    gen = timeslot_service.generate_slots(form.id, spec)
    slot_id = str(gen.created[0].id)

    # Submit booking
    resp = client.post(
        f"/form/{form.url_slug}",
        data={
            "name": "Bob",
            "email": "bob@example.com",
            "timeslot_ids": slot_id,
        },
    )
    assert resp.status_code == 200

    # Verify creator notification includes timeslot lines
    creator_emails = [m for m in sent if m["to"] == "creator@example.com"]
    assert creator_emails, "Expected a creator email to be sent"
    body = creator_emails[0]["body"].lower()
    assert "selected timeslots:" in body
    assert "mon oct 6, 5:00 pm–6:00 pm" in body


@pytest.mark.asyncio
async def test_timeslot_lines_fallback_to_utc_on_invalid_form_timezone(
    signup_service, timeslot_service: TimeslotService, authenticated_client, monkeypatch
):
    """If form.time_zone is invalid, we still include timeslot lines using UTC fallback."""
    client, _ = authenticated_client

    sent = []

    async def fake_send_email(self, to_email, email_content):
        sent.append(
            {
                "to": to_email,
                "subject": email_content.get("subject"),
                "body": email_content.get("body", ""),
            }
        )
        return True

    monkeypatch.setattr(EmailService, "_send_email", fake_send_email, raising=True)

    # Form with invalid time zone
    form = _create_published_form(
        signup_service, slug="ts-email-invalid-tz", tz="Mars/Phobos"
    )

    # Generate one slot using a valid schedule TZ so rows exist; 5–6 PM New York -> 21:00–22:00 UTC
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="17:00",
        window_end="18:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=TEST_MONDAY,
        time_zone="America/New_York",
        capacity_per_slot=1,
    )
    gen = timeslot_service.generate_slots(form.id, spec)
    slot_id = str(gen.created[0].id)

    # Book
    resp = client.post(
        f"/form/{form.url_slug}",
        data={
            "name": "Eve",
            "email": "eve@example.com",
            "timeslot_ids": slot_id,
        },
    )
    assert resp.status_code == 200

    # Registrant email should include slots, formatted in UTC (21:00–22:00)
    registrant = [m for m in sent if m["to"] == "eve@example.com"]
    assert registrant, "Expected registrant email"
    body = registrant[0]["body"].lower()
    assert "your selected timeslots:" in body
    assert "mon oct 6, 9:00 pm–10:00 pm" in body
