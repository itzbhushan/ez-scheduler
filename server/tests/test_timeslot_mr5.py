"""MR-TS-5 tests: internal create_form with timeslot_schedule generates slots."""

import uuid
from datetime import date

import pytest

from ez_scheduler.services.llm_service import LLMClient
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.services.timeslot_service import TimeslotService
from ez_scheduler.tools.create_form import FormExtractionSchema, _create_form


@pytest.mark.asyncio
async def test_internal_create_form_with_schedule(
    signup_service: SignupFormService,
    llm_client: LLMClient,
    timeslot_service: TimeslotService,
    mock_current_user,
):
    user = mock_current_user()

    data = FormExtractionSchema(
        title="Soccer Coaching",
        event_date="2025-10-01",
        location="City Park",
        description="1-1 coaching program",
        button_config=None,
        is_complete=True,
        timeslot_schedule={
            "days_of_week": ["monday", "wednesday"],
            "window_start": "17:00",
            "window_end": "21:00",
            "slot_minutes": 60,
            "weeks_ahead": 2,
            "start_from_date": "2025-10-06",
            "capacity_per_slot": 1,
            "time_zone": "UTC",
        },
    )

    # Call internal creator (it commits)
    msg = await _create_form(data, llm_client, signup_service, user)
    assert isinstance(msg, str)

    # Verify form exists and slots created
    # Extract slug from data.form_url
    assert data.form_url and data.form_id
    form = signup_service.get_form_by_id(uuid.UUID(data.form_id))
    assert form is not None

    slots = timeslot_service.list_available(form.id)
    # For a future schedule, availability should be non-empty
    assert len(slots) >= 1
