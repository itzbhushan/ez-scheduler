"""Unit tests for TimeslotService (MR-TS-2).

These tests validate:
- Slot generation across weekdays/windows
- Time zone conversion (local → UTC)
- Skipping past slots for "today"
- Availability filtering (future only)
- Cap enforcement

Note: The global test session requires ANTHROPIC_API_KEY due to other suites.
These tests themselves do not call the LLM.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from ez_scheduler.models import SignupForm
from ez_scheduler.models.timeslot import Timeslot
from ez_scheduler.services import TimeslotSchedule, TimeslotService


def _create_form(signup_service, *, tz: str = "UTC") -> SignupForm:
    """Create and return a persisted SignupForm via the service."""
    form = SignupForm(
        id=uuid.uuid4(),
        user_id="test-user",
        title="Coaching",
        event_date=date(2025, 1, 1),
        location="Field A",
        description="",
        url_slug=f"form-{uuid.uuid4().hex[:8]}",
        time_zone=tz,
    )
    result = signup_service.create_signup_form(form)
    assert result.get("success") is True
    form_id = uuid.UUID(result["form_id"])
    persisted = signup_service.get_form_by_id(form_id)
    assert persisted is not None
    return persisted


def test_generate_slots_mon_wed_two_weeks_60min(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    # Choose a Monday as the start_from_date for determinism
    start_monday = date(2025, 10, 6)  # 2025-10-06 is a Monday
    spec = TimeslotSchedule(
        days_of_week=["monday", "wednesday"],
        window_start="17:00",
        window_end="21:00",
        slot_minutes=60,
        weeks_ahead=2,
        start_from_date=start_monday,
        capacity_per_slot=1,
        time_zone="UTC",
    )

    result = svc.generate_slots(form.id, spec)

    # 4 slots/day * 2 days/week * 2 weeks = 16
    assert len(result.created) == 16
    assert result.skipped_existing == 0

    # Ensure all stored as UTC and within expected hour range
    starts = sorted(s.start_at for s in result.created)
    assert all(dt.tzinfo is not None for dt in starts)
    assert all(17 <= dt.hour <= 20 for dt in starts)  # last slot starts at 20:00


def test_timezone_conversion_new_york_to_utc(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="America/New_York")
    svc = timeslot_service

    # 2024-01-08 is a Monday; EST is UTC-5, so 17:00 local -> 22:00 UTC
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="17:00",
        window_end="19:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        capacity_per_slot=1,
    )

    result = svc.generate_slots(form.id, spec)
    assert len(result.created) == 2

    starts = sorted(s.start_at for s in result.created)
    assert starts[0] == datetime(2024, 1, 8, 22, 0, tzinfo=timezone.utc)
    assert starts[1] == datetime(2024, 1, 8, 23, 0, tzinfo=timezone.utc)


def test_skip_past_slots_on_today(signup_service, timeslot_service: TimeslotService):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    # Today window 10:00-12:00 UTC, 60m slots; at 10:30 only 11:00–12:00 should be generated
    today = date(2024, 1, 8)  # treat as "today" in test now
    now = datetime(2024, 1, 8, 10, 30, tzinfo=timezone.utc)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="12:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=today,
        capacity_per_slot=1,
        time_zone="UTC",
    )

    result = svc.generate_slots(form.id, spec, now=now)
    assert len(result.created) == 1
    assert result.created[0].start_at == datetime(
        2024, 1, 8, 11, 0, tzinfo=timezone.utc
    )


def test_do_not_skip_when_now_equals_slot_start(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    # Window 10:00-12:00 UTC, now exactly 10:00 → should include 10:00 and 11:00
    today = date(2024, 1, 8)
    now = datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="12:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=today,
        capacity_per_slot=1,
        time_zone="UTC",
    )

    result = svc.generate_slots(form.id, spec, now=now)
    starts = sorted(s.start_at for s in result.created)
    assert starts == [
        datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 8, 11, 0, tzinfo=timezone.utc),
    ]


def test_list_available_filters_past_only(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    # Create slots between 10:00 and 13:00 (10:00, 11:00, 12:00)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),  # Monday
        capacity_per_slot=1,
        time_zone="UTC",
    )
    svc.generate_slots(form.id, spec)

    # At 11:30 UTC, only the 12:00 slot is in the future
    now = datetime(2024, 1, 8, 11, 30, tzinfo=timezone.utc)
    results = svc.list_available(form.id, now=now)
    assert len(results) == 1
    assert results[0].start_at == datetime(2024, 1, 8, 12, 0, tzinfo=timezone.utc)


def test_list_available_date_range_filter(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    # Create 10:00, 11:00, 12:00
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        time_zone="UTC",
    )
    svc.generate_slots(form.id, spec)

    # Filter range [11:00, 12:00)
    results = svc.list_available(
        form.id,
        now=datetime(2024, 1, 8, 9, 0, tzinfo=timezone.utc),
        from_date=datetime(2024, 1, 8, 11, 0, tzinfo=timezone.utc),
        to_date=datetime(2024, 1, 8, 12, 0, tzinfo=timezone.utc),
    )
    assert len(results) == 1
    assert results[0].start_at == datetime(2024, 1, 8, 11, 0, tzinfo=timezone.utc)


def test_list_available_form_not_found(timeslot_service: TimeslotService):
    # Random UUID should raise for nonexistent form
    with pytest.raises(ValueError):
        timeslot_service.list_available(uuid.uuid4())


def test_generate_slots_invalid_timezone(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="11:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=date(2024, 1, 8),
        time_zone="Mars/Phobos",
    )
    with pytest.raises(ValueError):
        svc.generate_slots(form.id, spec)


def test_cap_enforcement(
    signup_service, timeslot_service: TimeslotService, monkeypatch
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    spec = TimeslotSchedule(
        days_of_week=["monday", "tuesday", "wednesday", "thursday", "friday"],
        window_start="10:00",
        window_end="12:00",
        slot_minutes=30,  # 10:00, 10:30, 11:00 => 3 slots
        weeks_ahead=10,
        start_from_date=date(2024, 1, 8),  # Monday
        capacity_per_slot=1,
        time_zone="UTC",
    )

    with pytest.raises(ValueError) as exc:
        svc.generate_slots(form.id, spec)
    assert "exceeding the limit" in str(exc.value)


# -------------------------
# MR-TS-9: Add/Remove Schedules
# -------------------------


def test_add_schedule_idempotent_counts(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    monday = date(2025, 10, 6)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=monday,
        capacity_per_slot=1,
        time_zone="UTC",
    )
    # Initial generation: 10:00, 11:00, 12:00
    gen = svc.generate_slots(form.id, spec)
    assert len(gen.created) == 3

    # Add again via add_schedule -> should skip all 3 as existing
    add_res = svc.add_schedule(form.id, spec)
    assert add_res.added_count == 0
    assert add_res.skipped_existing == 3


def test_remove_schedule_by_weekday_and_window(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    monday = date(2025, 10, 6)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=monday,
        capacity_per_slot=1,
        time_zone="UTC",
    )
    svc.generate_slots(form.id, spec)

    # Remove only the first hour using window [10:00, 11:00)
    remove_spec = TimeslotService.TimeslotRemoveSpec(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="11:00",
        weeks_ahead=1,
        start_from_date=monday,
        time_zone="UTC",
    )
    res = svc.remove_schedule(form.id, remove_spec)
    assert res.removed_count == 1
    assert res.skipped_booked == 0

    # Remaining should be 11:00 and 12:00
    remaining = svc.list_upcoming(
        form.id, now=datetime(2025, 10, 6, 9, 0, tzinfo=timezone.utc)
    )
    starts = [s.start_at for s in remaining]
    assert starts == [
        datetime(2025, 10, 6, 11, 0, tzinfo=timezone.utc),
        datetime(2025, 10, 6, 12, 0, tzinfo=timezone.utc),
    ]


def test_remove_schedule_skips_booked(
    signup_service, timeslot_service: TimeslotService
):
    form = _create_form(signup_service, tz="UTC")
    svc = timeslot_service

    monday = date(2025, 10, 6)
    spec = TimeslotSchedule(
        days_of_week=["monday"],
        window_start="10:00",
        window_end="13:00",
        slot_minutes=60,
        weeks_ahead=1,
        start_from_date=monday,
        capacity_per_slot=1,
        time_zone="UTC",
    )
    gen = svc.generate_slots(form.id, spec)

    # Mark the 11:00 slot as booked (simulate a booking)
    eleven = next(
        s
        for s in gen.created
        if s.start_at == datetime(2025, 10, 6, 11, 0, tzinfo=timezone.utc)
    )
    eleven.booked_count = 1
    # Persist the change
    svc.db.add(eleven)
    svc.db.commit()

    # Remove all Monday slots that week (no window)
    remove_spec = TimeslotService.TimeslotRemoveSpec(
        days_of_week=["monday"],
        weeks_ahead=1,
        start_from_date=monday,
        time_zone="UTC",
    )
    res = svc.remove_schedule(form.id, remove_spec)
    # Two unbooked removed; one booked skipped
    assert res.removed_count == 2
    assert res.skipped_booked == 1

    # Only the booked 11:00 should remain
    remaining = svc.list_upcoming(
        form.id, now=datetime(2025, 10, 6, 9, 0, tzinfo=timezone.utc)
    )
    assert len(remaining) == 1
    assert remaining[0].start_at == datetime(2025, 10, 6, 11, 0, tzinfo=timezone.utc)
