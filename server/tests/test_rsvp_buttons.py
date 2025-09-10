"""Test RSVP button functionality from form creation to response recording"""

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService


@pytest.mark.asyncio
async def test_rsvp_form_creation_and_responses(
    mcp_client, test_db_session, authenticated_client, llm_client
):
    """Test complete RSVP workflow: form creation with RSVP buttons and response recording"""

    client_instance, test_user = authenticated_client

    # Test 1: Create an RSVP form (wedding reception - should get RSVP yes/no buttons)
    form_url = None
    async with Client(mcp_client) as mcp:
        # Create wedding reception form that should trigger RSVP buttons
        form_response = await mcp.call_tool(
            "create_form",
            {
                "user_id": test_user.user_id,
                "initial_request": "Create a form for Sarah's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown. This is an intimate celebration with dinner and dancing. I need RSVP yes/no buttons and want to collect guest count and meal preferences (Chicken, Beef, Vegetarian).",
            },
        )

        response_text = form_response.content[0].text.lower()

        # If LLM asks for more info, provide it
        if "form/" not in response_text and (
            "additional" in response_text or "custom" in response_text
        ):
            # LLM is asking for more details, provide them
            form_response = await mcp.call_tool(
                "create_form",
                {
                    "user_id": test_user.user_id,
                    "initial_request": "Create a form for Sarah's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown. Yes, include guest count and meal preferences with options: Chicken, Beef, Vegetarian, Vegan.",
                },
            )

    # Verify form was created successfully
    response_text = form_response.content[0].text
    assert (
        "form/" in response_text.lower() or "created" in response_text.lower()
    ), f"Expected form to be created, got: {response_text[:200]}..."

    # Test 2: Get the created form from database and verify button configuration
    signup_form_service = SignupFormService(test_db_session)

    # Find the created form (should be the most recent one for this user)
    from sqlmodel import desc, select

    statement = (
        select(SignupForm)
        .where(SignupForm.user_id == test_user.user_id)
        .order_by(desc(SignupForm.created_at))
    )

    form = test_db_session.execute(statement).scalar_one_or_none()
    assert (
        form is not None
    ), f"Form should have been created. Response was: {response_text[:200]}..."

    # Verify this is an RSVP form with proper button configuration
    assert (
        form.button_type == "rsvp_yes_no"
    ), f"Wedding reception should use RSVP buttons, got {form.button_type}"
    assert form.primary_button_text is not None
    assert form.secondary_button_text is not None
    assert (
        "yes" in form.primary_button_text.lower()
        or "accept" in form.primary_button_text.lower()
        or "count" in form.primary_button_text.lower()
    )
    assert (
        "no" in form.secondary_button_text.lower()
        or "decline" in form.secondary_button_text.lower()
        or "can't" in form.secondary_button_text.lower()
    )

    # Test 3: Submit RSVP "Yes" response
    yes_form_data = {
        "name": "John Doe",
        "phone": "555-1234",
        "rsvp_response": "yes",
        "guest_count": "2",
        "meal_preference": "Chicken",
    }

    yes_response = client_instance.post(f"/form/{form.url_slug}", data=yes_form_data)
    assert yes_response.status_code == 200

    yes_result = yes_response.json()
    assert yes_result["success"] is True

    # Test 4: Verify RSVP "Yes" response was recorded
    registration_service = RegistrationService(test_db_session, llm_client)

    # Get registrations for this form
    from ez_scheduler.models.registration import Registration

    statement = select(Registration).where(Registration.form_id == form.id)
    registrations = test_db_session.execute(statement).scalars().all()

    yes_registration = next((r for r in registrations if r.name == "John Doe"), None)
    assert yes_registration is not None, "RSVP Yes registration should exist"
    assert yes_registration.additional_data is not None
    assert yes_registration.additional_data.get("rsvp_response") == "yes"

    # Test 5: Submit RSVP "No" response
    no_form_data = {
        "name": "Jane Smith",
        "phone": "555-5678",
        "rsvp_response": "no",
        "guest_count": "1",
        "meal_preference": "Vegetarian",
    }

    no_response = client_instance.post(f"/form/{form.url_slug}", data=no_form_data)
    assert no_response.status_code == 200

    no_result = no_response.json()
    assert no_result["success"] is True

    # Test 6: Verify RSVP "No" response was recorded
    statement = select(Registration).where(Registration.form_id == form.id)
    registrations = test_db_session.execute(statement).scalars().all()

    no_registration = next((r for r in registrations if r.name == "Jane Smith"), None)
    assert no_registration is not None, "RSVP No registration should exist"
    assert no_registration.additional_data is not None
    assert no_registration.additional_data.get("rsvp_response") == "no"

    # Test 7: Verify both responses are distinct
    assert len(registrations) >= 2, "Should have at least 2 registrations (yes and no)"
    assert yes_registration.id != no_registration.id, "Registrations should be separate"


@pytest.mark.asyncio
async def test_single_submit_form_creation(
    mcp_client, test_db_session, authenticated_client
):
    """Test that non-RSVP events get single submit buttons"""

    client_instance, test_user = authenticated_client

    # Create a conference form (should get single submit button)
    async with Client(mcp_client) as mcp:
        form_response = await mcp.call_tool(
            "create_form",
            {
                "user_id": test_user.user_id,
                "initial_request": "Create a form for Tech Conference 2024 on September 20th at Convention Center. Keep it simple - just basic registration info, no custom fields needed.",
            },
        )

        response_text = form_response.content[0].text.lower()

        # # If LLM asks for more info, provide it
        # if "form/" not in response_text and ("additional" in response_text or "custom" in response_text):
        #     # LLM is asking for more details, provide them
        #     form_response = await mcp.call_tool(
        #         "create_form",
        #         {
        #             "user_id": test_user.user_id,
        #             "initial_request": "Create a form for Tech Conference 2024 on September 20th at Convention Center. Keep it simple - just basic registration info, no custom fields needed.",
        #         },
        #     )

    # Verify form was created
    # response_text = form_response.content[0].text
    assert (
        "form/" in response_text.lower() or "created" in response_text.lower()
    ), f"Expected form to be created, got: {response_text[:200]}..."

    # Get the created form and verify button configuration
    signup_form_service = SignupFormService(test_db_session)

    from sqlmodel import desc, select

    statement = (
        select(SignupForm)
        .where(SignupForm.user_id == test_user.user_id)
        .order_by(desc(SignupForm.created_at))
    )

    form = test_db_session.execute(statement).scalar_one_or_none()
    assert form is not None

    # Verify this is a single submit form
    assert (
        form.button_type == "single_submit"
    ), f"Conference should use single submit button, got {form.button_type}"
    assert form.primary_button_text is not None
    assert form.secondary_button_text is None
    # Check that button text is appropriate for registration
    button_text = form.primary_button_text.lower()
    assert (
        "register" in button_text
        or "sign up" in button_text
        or "join" in button_text
        or "enroll" in button_text
        or "reserve" in button_text
        or "submit" in button_text
    ), f"Expected registration-appropriate button text, got: {form.primary_button_text}"

    # Test submission without RSVP response (normal registration)
    form_data = {
        "name": "Tech Attendee",
        "phone": "555-9999",
        "company": "Tech Solutions Inc",
        "job_title": "Software Engineer",
    }

    response = client_instance.post(f"/form/{form.url_slug}", data=form_data)
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True

    # Verify registration was created without RSVP response
    from ez_scheduler.models.registration import Registration

    statement = select(Registration).where(Registration.form_id == form.id)
    registration = test_db_session.execute(statement).scalar_one_or_none()

    assert registration is not None
    assert registration.name == "Tech Attendee"
    # Should not have rsvp_response in additional_data for single submit forms
    if registration.additional_data:
        assert "rsvp_response" not in registration.additional_data


@pytest.mark.asyncio
async def test_form_template_rendering_with_buttons(
    authenticated_client, signup_service
):
    """Test that form templates render the correct buttons based on button configuration"""

    client_instance, test_user = authenticated_client

    # Create RSVP form using service method for template testing
    rsvp_form = SignupForm(
        user_id=test_user.user_id,
        title="Test RSVP Event",
        event_date="2024-12-15",
        location="Test Location",
        description="Test RSVP event description",
        url_slug="test-rsvp-event-12345",
        is_active=True,
        button_type="rsvp_yes_no",
        primary_button_text="Accept Invitation",
        secondary_button_text="Decline",
    )

    result = signup_service.create_signup_form(rsvp_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Test RSVP form template rendering
    rsvp_response = client_instance.get(f"/form/{rsvp_form.url_slug}")
    assert rsvp_response.status_code == 200

    rsvp_html = rsvp_response.text
    assert "Accept Invitation" in rsvp_html
    assert "Decline" in rsvp_html
    assert 'name="rsvp_response"' in rsvp_html
    assert 'value="yes"' in rsvp_html
    assert 'value="no"' in rsvp_html

    # Create single submit form using service method
    single_form = SignupForm(
        user_id=test_user.user_id,
        title="Test Conference",
        event_date="2024-12-20",
        location="Conference Center",
        description="Test conference description",
        url_slug="test-conference-67890",
        is_active=True,
        button_type="single_submit",
        primary_button_text="Register Now",
        secondary_button_text=None,
    )

    result = signup_service.create_signup_form(single_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Test single submit form template rendering
    single_response = client_instance.get(f"/form/{single_form.url_slug}")
    assert single_response.status_code == 200

    single_html = single_response.text
    assert "Register" in single_html
    # Should not have RSVP response inputs
    assert 'name="rsvp_response"' not in single_html
    assert 'value="yes"' not in single_html
    assert 'value="no"' not in single_html


@pytest.mark.asyncio
async def test_rsvp_analytics_query(
    mcp_client, authenticated_client, signup_service, registration_service
):
    """Test that RSVP responses can be queried through analytics"""

    client_instance, test_user = authenticated_client

    # Create form with RSVP responses using service method
    form = SignupForm(
        user_id=test_user.user_id,
        title="Analytics Test Wedding",
        event_date="2024-12-31",
        location="Test Venue",
        description="Test wedding for analytics",
        url_slug="analytics-test-wedding-999",
        is_active=True,
        button_type="rsvp_yes_no",
        primary_button_text="Coming!",
        secondary_button_text="Sorry, can't make it",
    )

    result = signup_service.create_signup_form(form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Create registrations with different RSVP responses using fixture

    # RSVP Yes responses
    registration_service.create_registration(
        form_id=form.id,
        name="Yes Person 1",
        email="yes1@example.com",
        phone="555-0001",
        additional_data={"rsvp_response": "yes"},
    )

    registration_service.create_registration(
        form_id=form.id,
        name="Yes Person 2",
        email="yes2@example.com",
        phone="555-0002",
        additional_data={"rsvp_response": "yes"},
    )

    # RSVP No response
    registration_service.create_registration(
        form_id=form.id,
        name="No Person 1",
        phone="555-0003",
        email="no1@example.com",
        additional_data={"rsvp_response": "no"},
    )

    # Query RSVP responses via analytics
    async with Client(mcp_client) as mcp:
        analytics_response = await mcp.call_tool(
            "get_form_analytics",
            {
                "user_id": test_user.user_id,
                "analytics_query": "How many people RSVPed yes vs no for my Analytics Test Wedding?",
            },
        )

    analytics_text = analytics_response.content[0].text.lower()

    # Should contain information about RSVP responses with correct counts
    # Check for 2 yes responses and 1 no response
    assert (
        "2" in analytics_text
    ), f"Expected '2' (for yes responses) in analytics text: {analytics_text}"
    assert (
        "1" in analytics_text
    ), f"Expected '1' (for no responses) in analytics text: {analytics_text}"
