"""Integration tests for public registration endpoints with timeslots (MR-TS-4)."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.services import TimeslotSchedule, TimeslotService

# Fixed reference Monday date for deterministic scheduling
TEST_MONDAY = date(2025, 10, 6)


def _create_published_form(
    signup_service, slug: str = None, tz: str = "UTC"
) -> SignupForm:
    form = SignupForm(
        id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
        title="Coaching",
        event_date=date(2025, 1, 1),
        location="Field A",
        description="",
        url_slug=slug or f"form-{uuid.uuid4().hex[:8]}",
        status=FormStatus.PUBLISHED,
        time_zone=tz,
    )
    signup_service.create_signup_form(form)
    return form


class TestTimeslotEndpoints:
    @pytest.mark.asyncio
    async def test_get_form_shows_timeslots(
        self, signup_service, timeslot_service: TimeslotService, authenticated_client
    ):
        client, _ = authenticated_client
        form = _create_published_form(signup_service, slug="ts-form-get")

        # Use a fixed future Monday window for determinism
        spec = TimeslotSchedule(
            days_of_week=["monday"],
            window_start="10:00",
            window_end="12:00",
            slot_minutes=60,
            weeks_ahead=1,
            start_from_date=TEST_MONDAY,
            time_zone="UTC",
        )
        gen = timeslot_service.generate_slots(form.id, spec)
        assert len(gen.created) == 2

        resp = client.get(f"/form/{form.url_slug}")
        assert resp.status_code == 200
        body = resp.text
        # Heading present
        assert "Available Timeslots" in body
        # At least one checkbox present for timeslot selection
        assert 'name="timeslot_ids"' in body

    @pytest.mark.asyncio
    async def test_post_requires_timeslot_selection_for_timeslot_form(
        self, signup_service, timeslot_service: TimeslotService, authenticated_client
    ):
        client, _ = authenticated_client
        form = _create_published_form(signup_service, slug="ts-form-require")

        # Create exactly one slot on a fixed Monday
        spec = TimeslotSchedule(
            days_of_week=["monday"],
            window_start="10:00",
            window_end="11:00",
            slot_minutes=60,
            weeks_ahead=1,
            start_from_date=TEST_MONDAY,
            time_zone="UTC",
        )
        timeslot_service.generate_slots(form.id, spec)

        # Submit without timeslot_ids
        resp = client.post(
            f"/form/{form.url_slug}",
            data={
                "name": "Alice",
                "phone": "555-1234",
            },
        )
        assert resp.status_code == 400
        assert "select at least one timeslot" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_post_books_timeslot_and_conflicts_on_second(
        self, signup_service, timeslot_service: TimeslotService, authenticated_client
    ):
        client, _ = authenticated_client
        form = _create_published_form(signup_service, slug="ts-form-book")

        # Fixed Monday single-slot window with capacity 1
        spec = TimeslotSchedule(
            days_of_week=["monday"],
            window_start="10:00",
            window_end="11:00",
            slot_minutes=60,
            weeks_ahead=1,
            start_from_date=TEST_MONDAY,
            time_zone="UTC",
            capacity_per_slot=1,
        )
        gen = timeslot_service.generate_slots(form.id, spec)
        slot_id = str(gen.created[0].id)

        # First booking succeeds
        resp1 = client.post(
            f"/form/{form.url_slug}",
            data={
                "name": "Bob",
                "phone": "555-1234",
                "timeslot_ids": slot_id,
            },
        )
        assert resp1.status_code == 200
        js1 = resp1.json()
        assert js1["success"] is True
        assert slot_id in js1.get("timeslot_ids", [])

        # Second booking for the same slot should 409
        resp2 = client.post(
            f"/form/{form.url_slug}",
            data={
                "name": "Carol",
                "phone": "555-5678",
                "timeslot_ids": slot_id,
            },
        )
        assert resp2.status_code == 409
        js2 = resp2.json()
        assert isinstance(js2.get("detail"), dict)
        assert "unavailable_ids" in js2["detail"]

    @pytest.mark.asyncio
    async def test_post_rejects_timeslot_not_belonging_to_form(
        self, signup_service, timeslot_service: TimeslotService, authenticated_client
    ):
        client, _ = authenticated_client
        form_a = _create_published_form(signup_service, slug="ts-form-a")
        form_b = _create_published_form(signup_service, slug="ts-form-b")

        # Fixed Monday single-slot window
        spec = TimeslotSchedule(
            days_of_week=["monday"],
            window_start="10:00",
            window_end="11:00",
            slot_minutes=60,
            weeks_ahead=1,
            start_from_date=TEST_MONDAY,
            time_zone="UTC",
        )
        # Create a slot for form B
        gen_b = timeslot_service.generate_slots(form_b.id, spec)
        foreign_slot_id = str(gen_b.created[0].id)

        # Submit against form A using form B's slot id → 403
        resp = client.post(
            f"/form/{form_a.url_slug}",
            data={
                "name": "Dana",
                "phone": "555-9999",
                "timeslot_ids": foreign_slot_id,
            },
        )
        assert resp.status_code == 403
        assert "invalid" in resp.json()["detail"].lower()
