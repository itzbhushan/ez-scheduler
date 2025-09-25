"""Tests for TimeslotService.booking (MR-TS-3).

Verifies transactional booking behavior with capacity checks and rollback.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from ez_scheduler.services import TimeslotSchedule, TimeslotService


def _create_published_form(signup_service) -> uuid.UUID:
    from ez_scheduler.models.signup_form import SignupForm

    form = SignupForm(
        id=uuid.uuid4(),
        user_id="test-user",
        title="Coaching",
        event_date=date(2025, 1, 1),
        location="Field A",
        description="",
        url_slug=f"form-{uuid.uuid4().hex[:8]}",
        time_zone="UTC",
    )
    res = signup_service.create_signup_form(form)
    assert res.get("success") is True
    form_id = uuid.UUID(res["form_id"])
    # publish
    assert signup_service.update_signup_form(form_id, {"status": "published"})[
        "success"
    ]
    return form_id


def _create_registration(registration_service, form_id: uuid.UUID):
    return registration_service.create_registration(
        form_id=form_id,
        name="Alice",
        email="alice@example.com",
        phone="+10000000000",
    )


def test_book_single_slot_success(
    signup_service, registration_service, timeslot_service: TimeslotService
):
    form_id = _create_published_form(signup_service)

    # One future slot at 12:00 UTC
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="12:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        time_zone="UTC",
    )
    gen = timeslot_service.generate_slots(form_id, spec)
    slot_id = gen.created[0].id

    reg = _create_registration(registration_service, form_id)
    result = timeslot_service.book_slots(reg.id, [slot_id])
    assert result.success is True
    assert result.unavailable_ids == []
    assert result.already_booked_ids == []

    # Slot is now full (capacity 1) → not available
    now = datetime(2024, 1, 8, 9, 0, tzinfo=timezone.utc)
    avail = timeslot_service.list_available(form_id, now=now)
    assert all(s.id != slot_id for s in avail)


def test_capacity_two_allows_two_bookings_then_blocks_third(
    signup_service, registration_service, timeslot_service: TimeslotService
):
    form_id = _create_published_form(signup_service)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="11:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        time_zone="UTC",
        capacity_per_slot=2,
    )
    gen = timeslot_service.generate_slots(form_id, spec)
    slot_id = gen.created[0].id

    r1 = _create_registration(registration_service, form_id)
    r2 = _create_registration(registration_service, form_id)
    r3 = _create_registration(registration_service, form_id)

    assert timeslot_service.book_slots(r1.id, [slot_id]).success is True
    assert timeslot_service.book_slots(r2.id, [slot_id]).success is True

    # Third should fail (capacity reached)
    fail = timeslot_service.book_slots(r3.id, [slot_id])
    assert fail.success is False
    assert slot_id in fail.unavailable_ids


def test_atomic_rollback_on_partial_failure(
    signup_service, registration_service, timeslot_service: TimeslotService
):
    form_id = _create_published_form(signup_service)
    # Create two slots: 10:00 and 11:00
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="12:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        time_zone="UTC",
    )
    gen = timeslot_service.generate_slots(form_id, spec)
    s10, s11 = gen.created[0].id, gen.created[1].id

    # Pre-book 10:00 to make it full
    r0 = _create_registration(registration_service, form_id)
    assert timeslot_service.book_slots(r0.id, [s10]).success is True

    # Attempt to book [10:00, 11:00] for another user — should fail and not book 11:00
    r1 = _create_registration(registration_service, form_id)
    res = timeslot_service.book_slots(r1.id, [s10, s11])
    assert res.success is False
    assert s10 in res.unavailable_ids

    # 11:00 should still be available (not partially booked)
    now = datetime(2024, 1, 8, 9, 0, tzinfo=timezone.utc)
    avail_ids = [s.id for s in timeslot_service.list_available(form_id, now=now)]
    assert s11 in avail_ids

