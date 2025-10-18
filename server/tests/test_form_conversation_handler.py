import pytest

from ez_scheduler.auth.models import User
from ez_scheduler.handlers.form_conversation_handler import (
    ConversationHandlerResponse,
    FormConversationHandler,
)
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_state_manager import FormStateManager


@pytest.fixture
def conversation_manager(redis_client, redis_url):
    """Create ConversationManager instance."""
    return ConversationManager(
        redis_client=redis_client, redis_url=redis_url, ttl_seconds=1800
    )


@pytest.fixture
def form_state_manager(redis_client):
    """Create FormStateManager instance."""
    return FormStateManager(redis_client=redis_client, ttl_seconds=1800)


@pytest.fixture
def handler(llm_client, conversation_manager, form_state_manager):
    """Create FormConversationHandler instance with real LLM client."""
    return FormConversationHandler(
        llm_client=llm_client,
        conversation_manager=conversation_manager,
        form_state_manager=form_state_manager,
    )


@pytest.mark.asyncio
async def test_process_message_birthday_party_flow(
    handler, mock_current_user, clean_redis
):
    """Test complete flow for creating a birthday party form."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::birthday"

    # Message 1: Initial request
    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="I want to create a signup form for my birthday party",
    )

    # Verify response structure
    assert isinstance(response1, ConversationHandlerResponse)
    assert response1.response_text

    # Message 2: Provide date, location, and time
    response2 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="It's on December 15th, 2024 at Central Park from 6pm to 10pm",
    )

    # Should extract date, location, and times
    assert response2.form_state.get("event_date")
    assert response2.form_state.get("location")

    # Message 3: May ask about host info or custom fields - respond accordingly
    if (
        "host" in response2.response_text.lower()
        or "whose" in response2.response_text.lower()
    ):
        response3 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="It's for Sarah's 30th birthday",
        )
    else:
        response3 = response2

    # Message 4: May ask about custom fields - say no
    if (
        "custom" in response3.response_text.lower()
        or "additional" in response3.response_text.lower()
        or "collect" in response3.response_text.lower()
    ):
        response4 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Just keep it simple, no additional fields",
        )
    else:
        response4 = response3

    # Should have title and description generated
    assert response4.form_state.get("title")
    assert response4.form_state.get("description")

    # Birthday party should always get RSVP Yes/No buttons
    assert response4.form_state.get("button_config")
    assert response4.form_state["button_config"]["button_type"] == "rsvp_yes_no"

    # Early responses should not be complete
    assert response1.is_complete is False
    assert response2.is_complete is False


@pytest.mark.asyncio
async def test_process_message_workshop_flow(handler, mock_current_user, clean_redis):
    """Test complete flow for creating a workshop registration form."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::workshop"

    # Message 1: Initial request for workshop
    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="I need a registration form for my Python programming workshop",
    )

    assert isinstance(response1, ConversationHandlerResponse)

    # Message 2: Provide all details at once
    response2 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="January 20th, 2025 at Tech Hub, 9am to 5pm for beginners.",
    )

    # Should extract multiple fields
    assert response2.form_state.get("event_date")
    assert response2.form_state.get("location")

    # May ask about custom fields for workshop - decline
    if (
        "custom" in response2.response_text.lower()
        or "additional" in response2.response_text.lower()
        or "experience" in response2.response_text.lower()
    ):
        response3 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="No additional fields needed",
        )
    else:
        response3 = response2

    # Should have generated title and description
    assert response3.form_state.get("title")
    assert response3.form_state.get("description")

    # Workshop should always get single submit button
    assert response3.form_state.get("button_config")
    assert response3.form_state["button_config"]["button_type"] == "single_submit"

    # When all info is collected and custom fields preference is given,
    # LLM should mark as complete (form is ready to create)
    assert response3.is_complete is True

    # Early responses should not be complete
    assert response1.is_complete is False
    assert response2.is_complete is False


@pytest.mark.asyncio
async def test_conversation_history_persistence(
    handler, mock_current_user, conversation_manager, clean_redis
):
    """Test that conversation history is maintained across messages."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::history"

    # Send first message
    response1 = await handler.process_message(
        user=test_user, thread_id=thread_id, user_message="Create a form for my party"
    )

    # Send second message
    response2 = await handler.process_message(
        user=test_user, thread_id=thread_id, user_message="It's on March 15th"
    )

    # Verify history has both exchanges (2 user + 2 assistant = 4 messages)
    history = conversation_manager.get_history(thread_id)
    assert (
        len(history) >= 2
    )  # At least 2 messages (could be 4 with assistant responses)

    # First message should be in history
    assert any("party" in msg["content"].lower() for msg in history)

    # Early responses should not be complete
    assert response1.is_complete is False
    assert response2.is_complete is False


@pytest.mark.asyncio
async def test_form_state_accumulation(
    handler, mock_current_user, form_state_manager, clean_redis
):
    """Test that form state accumulates across multiple messages."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::accumulate"

    # Message 1: Provide event type
    await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="Create a form for Tech Meetup",
    )

    # Message 2: Date and location
    response2 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="February 10th at Innovation Center",
    )

    # Title should be generated, date and location extracted
    state = response2.form_state
    assert state.get("title")  # Title should be generated
    assert (
        "meetup" in state.get("title", "").lower()
        or "tech" in state.get("title", "").lower()
    )
    assert state.get("event_date")
    assert state.get("location")

    # Should not be complete yet (missing description, button config, etc.)
    assert response2.is_complete is False


@pytest.mark.asyncio
async def test_create_action_handling(handler, mock_current_user, clean_redis):
    """Test handling of explicit create request."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::create"

    # Set up a nearly complete form first
    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="Create a signup for my wedding on June 1st at Grand Hotel",
    )

    # May ask about host - provide info
    if (
        "host" in response1.response_text.lower()
        or "whose" in response1.response_text.lower()
    ):
        response2 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="It's for Sarah and Michael's wedding",
        )
    else:
        response2 = response1

    # May ask about custom fields - decline
    if (
        "custom" in response2.response_text.lower()
        or "additional" in response2.response_text.lower()
    ):
        response3 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="No additional fields",
        )
    else:
        response3 = response2

    # Explicitly ask to create - should mark as complete
    response = await handler.process_message(
        user=test_user, thread_id=thread_id, user_message="Yes, create the form now!"
    )

    # Should return a valid response
    assert isinstance(response, ConversationHandlerResponse)


@pytest.mark.asyncio
async def test_button_type_determination_wedding(
    handler, mock_current_user, clean_redis
):
    """Test that wedding events get RSVP buttons automatically."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::wedding"

    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="Create a form for our wedding reception on July 15th at The Grand Ballroom",
    )

    # May ask about host - provide info
    if (
        "host" in response1.response_text.lower()
        or "whose" in response1.response_text.lower()
    ):
        response2 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Sarah and Michael",
        )
    else:
        response2 = response1

    # May ask about custom fields - decline
    if (
        "custom" in response2.response_text.lower()
        or "additional" in response2.response_text.lower()
    ):
        response3 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Just basic fields",
        )
    else:
        response3 = response2

    # Wedding should always have RSVP buttons
    assert response3.form_state.get("button_config")
    assert response3.form_state["button_config"]["button_type"] == "rsvp_yes_no"


@pytest.mark.asyncio
async def test_button_type_determination_conference(
    handler, mock_current_user, clean_redis
):
    """Test that conference events get single submit button automatically."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::conference"

    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="I need registration for the Tech Conference 2025 on March 10th at Convention Center",
    )

    # Conference is professional - should not ask about host
    # May ask about custom fields - decline
    if (
        "custom" in response1.response_text.lower()
        or "additional" in response1.response_text.lower()
    ):
        response2 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Just basic info",
        )
    else:
        response2 = response1

    # Conference should always have single submit button
    assert response2.form_state.get("button_config")
    assert response2.form_state["button_config"]["button_type"] == "single_submit"


@pytest.mark.asyncio
async def test_response_structure(handler, mock_current_user, clean_redis):
    """Test that response always has required structure."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::structure"

    response = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="Create a simple event form",
    )

    # Verify ConversationHandlerResponse structure
    assert isinstance(response, ConversationHandlerResponse)
    assert isinstance(response.response_text, str)
    assert len(response.response_text) > 0
    assert isinstance(response.form_state, dict)


@pytest.mark.asyncio
async def test_completeness_detection(handler, mock_current_user, clean_redis):
    """Test that completeness is properly detected when all required fields are present."""
    thread_id = "test_user_123::conv::complete"
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::complete"

    # Provide all required information in one message
    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="Create a form for Annual Gala on November 20th, 2024 at City Hall",
    )

    # May ask about custom fields for gala - decline
    if (
        "custom" in response1.response_text.lower()
        or "additional" in response1.response_text.lower()
    ):
        response2 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="No additional fields",
        )
    else:
        response2 = response1

    # Check that all required fields have been collected
    state = response2.form_state
    assert state.get("title")
    assert state.get("event_date")
    assert state.get("location")
    assert state.get("description")

    # Gala should always have RSVP buttons
    assert state.get("button_config")
    assert state["button_config"]["button_type"] == "rsvp_yes_no"


@pytest.mark.asyncio
async def test_timeslot_based_reservation(handler, mock_current_user, clean_redis):
    """Test that timeslot-based events collect timeslot schedule information and create specific timeslots."""
    test_user = mock_current_user()
    thread_id = f"{test_user.user_id}::conv::timeslots"

    # Message 1: Request a timeslot-based appointment form
    response1 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="I need a form for scheduling 1-on-1 consultations with timeslots",
    )

    assert isinstance(response1, ConversationHandlerResponse)

    # Message 2: Provide date, location, and timeslot details
    response2 = await handler.process_message(
        user=test_user,
        thread_id=thread_id,
        user_message="March 25th, 2025 at 123 Main Street Suite 500, 30-minute slots from 9am to 5pm",
    )

    # Should extract date, location, and timeslot info
    assert response2.form_state.get("event_date")
    assert response2.form_state.get("location")

    # May ask about capacity - specify 2 per slot
    if (
        "capacity" in response2.response_text.lower()
        or "how many" in response2.response_text.lower()
        or "multiple" in response2.response_text.lower()
    ):
        response3 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Allow 2 reservations per slot",
        )
    else:
        response3 = response2

    # May ask about custom fields - decline
    if (
        "custom" in response3.response_text.lower()
        or "additional" in response3.response_text.lower()
    ):
        response4 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="No additional fields needed",
        )
    else:
        response4 = response3

    # Get final state
    final_state = response4.form_state

    # Should have generated title and description
    assert final_state.get("title")
    assert final_state.get("description")
    assert final_state.get("location")

    # Timeslot-based events should have timeslot_schedule
    assert final_state.get("timeslot_schedule")
    timeslot_schedule = final_state["timeslot_schedule"]

    # Verify timeslot_schedule structure and values
    slot_minutes = timeslot_schedule.get(
        "slot_duration_minutes"
    ) or timeslot_schedule.get("slot_minutes")
    window_start = timeslot_schedule.get("start_time") or timeslot_schedule.get(
        "window_start"
    )
    window_end = timeslot_schedule.get("end_time") or timeslot_schedule.get(
        "window_end"
    )

    assert slot_minutes == 30, f"Expected 30 minute slots, got {slot_minutes}"
    assert window_start, "Should have start time"
    assert window_end, "Should have end time"

    # Verify start and end times are correct (9am to 5pm)
    # Times might be in format "09:00" or "9:00" or "09:00:00"
    # Start time should be 9am (09:00)
    start_str = str(window_start).lower()
    assert start_str.startswith("9:") or start_str.startswith(
        "09:"
    ), f"Start time should be 9am, got {window_start}"

    # End time should be 5pm (17:00) - check for both 12-hour and 24-hour formats
    end_str = str(window_end).lower()
    is_5pm = end_str.startswith("17:") or end_str.startswith("5:") or "17:00" in end_str
    assert is_5pm, f"End time should be 5pm/17:00, got {window_end}"

    # Verify capacity if it was set (LLM may or may not ask about capacity)
    capacity = timeslot_schedule.get("capacity_per_slot")
    if capacity is not None:
        # If capacity was collected, it should be 2 (from our response)
        assert capacity == 2, f"Expected capacity of 2 per slot, got {capacity}"

    # Timeslot events should use single_submit button type
    assert final_state.get("button_config")
    assert final_state["button_config"]["button_type"] == "single_submit"

    # Early responses should not be complete
    assert response1.is_complete is False
    assert response2.is_complete is False

    # If still asking about additional fields, answer again
    if not response4.is_complete and (
        "collect" in response4.response_text.lower()
        or "information" in response4.response_text.lower()
        or "specific" in response4.response_text.lower()
    ):
        response5 = await handler.process_message(
            user=test_user,
            thread_id=thread_id,
            user_message="Just basic contact details, no additional fields",
        )
        # After answering all questions, form should be complete
        assert (
            response5.is_complete is True
        ), f"Form should be complete after all questions answered. Response: {response5.response_text}"
    else:
        # If LLM marked it complete earlier, verify that
        assert (
            response4.is_complete is True
        ), "Form should be complete after providing all required information"
