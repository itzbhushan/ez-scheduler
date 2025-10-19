"""
Reproduction tests for reported timeslot bugs using /gpt/create-or-update-form endpoint.

These tests verify the specific scenarios reported:
1. New dates not being added correctly
2. Number of registrations per slot not handled correctly
3. Removing specific slots doesn't work
"""

import re

import pytest


def test_bug_new_dates_not_added(
    authenticated_client, timeslot_service, signup_service
):
    """
    BUG REPRODUCTION: New dates not being added correctly

    Scenario:
    1. Create form with Monday 10-11 AM slots for Oct 5, 2026
    2. Add Tuesday 10-11 AM slots (new date)
    3. Verify both Monday and Tuesday slots exist
    """
    client, _ = authenticated_client

    # Step 1: Create form with Monday timeslots
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for Coaching at Library on October 5, 2026. Monday from 10:00 to 11:00, 60 minute slots, 1 person per slot, timezone UTC"
        },
    )
    assert response1.status_code == 200
    result1 = response1.json()["response"]

    # Extract form slug from response
    url_pattern = r"form/([a-zA-Z0-9-]+)"
    match = re.search(url_pattern, result1)

    # May need follow-ups
    follow_ups = ["Yes that's correct", "Create it", "Looks good"]
    for follow_up in follow_ups:
        if not match:
            response = client.post(
                "/gpt/create-or-update-form", json={"message": follow_up}
            )
            result1 = response.json()["response"]
            match = re.search(url_pattern, result1)

    assert match, f"Form not created. Response: {result1}"
    url_slug = match.group(1)

    # Get form
    form = signup_service.get_form_by_url_slug(url_slug)
    assert form is not None

    # Verify Monday slots exist
    monday_slots = timeslot_service.list_available(form.id)
    assert len(monday_slots) >= 1, "Should have Monday slots"
    assert all(
        s.start_at.weekday() == 0 for s in monday_slots
    ), "All slots should be Monday"

    # Step 2: Add Tuesday slots (NEW DATE)
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={"message": "Also add Tuesday October 6 from 10:00 to 11:00"},
    )
    assert response2.status_code == 200
    result2 = response2.json()["response"]

    # Step 3: Verify BOTH Monday and Tuesday slots exist
    all_slots = timeslot_service.list_available(form.id)
    assert (
        len(all_slots) >= 2
    ), f"Expected at least 2 slots (Mon + Tue), got {len(all_slots)}"

    weekdays = {slot.start_at.weekday() for slot in all_slots}
    assert 0 in weekdays, "Monday slot should exist (weekday=0)"
    assert 1 in weekdays, "Tuesday slot should exist (weekday=1)"


def test_bug_capacity_per_slot_not_respected(
    authenticated_client, timeslot_service, signup_service
):
    """
    TEST: Verify capacity_per_slot is enforced consistently across all slots

    Per product decision: All slots in a form must have the same capacity.
    This test verifies the system enforces this constraint.

    Scenario:
    1. Create slots with capacity=2
    2. Try to add slots with capacity=5
    3. Verify the LLM asks for clarification OR all slots maintain the same capacity
    """
    client, _ = authenticated_client

    # Step 1: Create form with Monday 10-11 slots, capacity=2
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for Workshops at Building A on October 5, 2026. Monday from 10:00 to 11:00, 60 minute slots, 2 people per slot, timezone UTC"
        },
    )
    assert response1.status_code == 200
    result1 = response1.json()["response"]

    url_pattern = r"form/([a-zA-Z0-9-]+)"
    match = re.search(url_pattern, result1)

    follow_ups = ["Yes that's correct", "Create it", "Looks good"]
    for follow_up in follow_ups:
        if not match:
            response = client.post(
                "/gpt/create-or-update-form", json={"message": follow_up}
            )
            result1 = response.json()["response"]
            match = re.search(url_pattern, result1)

    assert match, f"Form not created. Response: {result1}"
    url_slug = match.group(1)

    form = signup_service.get_form_by_url_slug(url_slug)
    assert form is not None

    # Verify Monday slot has capacity=2
    monday_slots = timeslot_service.list_available(form.id)
    assert len(monday_slots) >= 1
    monday_slot = monday_slots[0]
    assert (
        monday_slot.capacity == 2
    ), f"Monday slot should have capacity=2, got {monday_slot.capacity}"

    # Step 2: Add Tuesday 10-11 slots with capacity=5
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Also add Tuesday October 6 from 10:00 to 11:00 with 5 people per slot"
        },
    )
    assert response2.status_code == 200

    # Step 3: Verify all slots have the SAME capacity (product requirement)
    all_slots = timeslot_service.list_available(form.id)

    # We should have at least 1 slot (the original Monday slot)
    # The Tuesday request may have been rejected or the LLM may have asked for clarification
    assert len(all_slots) >= 1, f"Expected at least 1 slot, got {len(all_slots)}"

    # All slots that exist must have the SAME capacity
    capacities = {slot.capacity for slot in all_slots}
    assert (
        len(capacities) == 1
    ), f"All slots must have the same capacity. Found different capacities: {capacities}"

    # The capacity should be either 2 (original) or some consistent value
    consistent_capacity = capacities.pop()
    assert (
        consistent_capacity >= 1
    ), f"Capacity must be at least 1, got {consistent_capacity}"


@pytest.mark.skip(reason="Known bug: Removing specific timeslots not working yet")
def test_bug_removing_specific_slots_fails(
    authenticated_client, timeslot_service, signup_service
):
    """
    BUG REPRODUCTION: Removing specific slots doesn't work

    Scenario:
    1. Create Monday 10-13 slots (10AM, 11AM, 12PM)
    2. Remove only 11-12 slot (specific time window)
    3. Verify 10AM and 12PM slots remain, 11AM is removed
    """
    client, _ = authenticated_client

    # Step 1: Create Monday 10-13 (3 slots: 10AM, 11AM, 12PM)
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for Tutoring at Room 101 on October 5, 2026. Monday from 10:00 to 13:00, 60 minute slots, 1 person per slot, timezone UTC"
        },
    )
    assert response1.status_code == 200
    result1 = response1.json()["response"]

    url_pattern = r"form/([a-zA-Z0-9-]+)"
    match = re.search(url_pattern, result1)

    follow_ups = ["Yes that's correct", "Create it", "Looks good"]
    for follow_up in follow_ups:
        if not match:
            response = client.post(
                "/gpt/create-or-update-form", json={"message": follow_up}
            )
            result1 = response.json()["response"]
            match = re.search(url_pattern, result1)

    assert match, f"Form not created. Response: {result1}"
    url_slug = match.group(1)

    form = signup_service.get_form_by_url_slug(url_slug)
    assert form is not None

    initial_slots = timeslot_service.list_available(form.id)
    assert (
        len(initial_slots) == 3
    ), f"Should have 3 slots initially, got {len(initial_slots)}"
    initial_hours = sorted([s.start_at.hour for s in initial_slots])
    assert initial_hours == [
        10,
        11,
        12,
    ], f"Should have [10, 11, 12], got {initial_hours}"

    # Step 2: Remove ONLY the 11-12 slot (11AM)
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={"message": "Remove the 11:00 AM slot"},
    )
    assert response2.status_code == 200

    # Step 3: Verify 10AM and 12PM remain, 11AM is gone
    remaining_slots = timeslot_service.list_available(form.id)
    assert (
        len(remaining_slots) == 2
    ), f"Should have 2 remaining slots, got {len(remaining_slots)}"

    remaining_hours = sorted([s.start_at.hour for s in remaining_slots])
    assert remaining_hours == [10, 12], f"Should have [10, 12], got {remaining_hours}"

    # Specifically verify 11AM is gone
    assert all(
        s.start_at.hour != 11 for s in remaining_slots
    ), "11AM slot should be removed"


@pytest.mark.skip(reason="Known bug: Removing specific day timeslots not working yet")
def test_bug_removing_specific_day_keeps_others(
    authenticated_client, timeslot_service, signup_service
):
    """
    BUG REPRODUCTION: Removing specific day should keep other days

    Scenario:
    1. Create Mon-Fri 10-11 slots (5 slots)
    2. Remove only Wednesday slots
    3. Verify Mon, Tue, Thu, Fri remain
    """
    client, _ = authenticated_client

    # Step 1: Create Mon-Fri 10-11 slots for just the first week
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for Office Hours at Conference Room on October 5, 2026. Monday to Friday from 10:00 to 11:00, 60 minute slots, 1 person per slot, timezone UTC, for 1 week only"
        },
    )
    assert response1.status_code == 200
    result1 = response1.json()["response"]

    url_pattern = r"form/([a-zA-Z0-9-]+)"
    match = re.search(url_pattern, result1)

    follow_ups = ["Yes that's correct", "Create it", "Looks good", "Perfect"]
    for follow_up in follow_ups:
        if not match:
            response = client.post(
                "/gpt/create-or-update-form", json={"message": follow_up}
            )
            result1 = response.json()["response"]
            match = re.search(url_pattern, result1)

    assert match, f"Form not created. Response: {result1}"
    url_slug = match.group(1)

    form = signup_service.get_form_by_url_slug(url_slug)
    assert form is not None

    initial_slots = timeslot_service.list_available(form.id)
    # Should have 5 weekday slots for 1 week (Mon-Fri)
    assert (
        len(initial_slots) == 5
    ), f"Should have 5 weekday slots (1 week, Mon-Fri), got {len(initial_slots)}"

    # Step 2: Remove only Wednesday (weekday=2)
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={"message": "Remove Wednesday slots"},
    )
    assert response2.status_code == 200

    # Step 3: Verify Mon, Tue, Thu, Fri remain
    remaining_slots = timeslot_service.list_available(form.id)
    assert (
        len(remaining_slots) == 4
    ), f"Should have 4 slots after removing Wed, got {len(remaining_slots)}"

    remaining_weekdays = sorted([s.start_at.weekday() for s in remaining_slots])
    assert remaining_weekdays == [
        0,
        1,
        3,
        4,
    ], f"Should have [Mon, Tue, Thu, Fri], got {remaining_weekdays}"

    # Specifically verify Wednesday is gone
    assert all(
        s.start_at.weekday() != 2 for s in remaining_slots
    ), "Wednesday slot should be removed"
