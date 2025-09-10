"""Simplified test for RSVP button functionality"""

from datetime import date

import pytest

from ez_scheduler.models.signup_form import SignupForm


@pytest.mark.asyncio
async def test_rsvp_button_configuration_and_recording(
    authenticated_client, signup_service, registration_service
):
    """Test RSVP button configuration and response recording"""

    client_instance, test_user = authenticated_client

    # Test 1: Create RSVP form using service method
    rsvp_form = SignupForm(
        user_id=test_user.user_id,
        title="Test Wedding Reception",
        event_date=date(2024, 12, 15),
        location="Grand Ballroom",
        description="Wedding reception with dinner and dancing",
        url_slug="test-wedding-rsvp-123",
        is_active=True,
        button_type="rsvp_yes_no",
        primary_button_text="Accept Invitation",
        secondary_button_text="Decline",
    )

    result = signup_service.create_signup_form(rsvp_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object
    # which now has the updated ID from the database

    # Test 2: Verify form has correct button configuration
    assert rsvp_form.button_type == "rsvp_yes_no"
    assert rsvp_form.primary_button_text == "Accept Invitation"
    assert rsvp_form.secondary_button_text == "Decline"

    # Test 3: Submit RSVP "Yes" response
    yes_form_data = {
        "name": "Alice Johnson",
        "phone": "555-1111",
        "rsvp_response": "yes",
    }

    yes_response = client_instance.post(
        f"/form/{rsvp_form.url_slug}", data=yes_form_data
    )
    assert yes_response.status_code == 200

    yes_result = yes_response.json()
    assert yes_result["success"] is True

    # Test 4: Submit RSVP "No" response
    no_form_data = {
        "name": "Bob Wilson",
        "phone": "555-2222",
        "rsvp_response": "no",
    }

    no_response = client_instance.post(f"/form/{rsvp_form.url_slug}", data=no_form_data)
    assert no_response.status_code == 200

    no_result = no_response.json()
    assert no_result["success"] is True

    # Test 5: Verify RSVP responses were recorded correctly using service method
    registrations = registration_service.get_registrations_for_form(rsvp_form.id)

    assert len(registrations) == 2, "Should have 2 registrations"

    # Find specific registrations
    alice_reg = next((r for r in registrations if r.name == "Alice Johnson"), None)
    bob_reg = next((r for r in registrations if r.name == "Bob Wilson"), None)

    assert alice_reg is not None, "Alice's registration should exist"
    assert bob_reg is not None, "Bob's registration should exist"

    # Verify RSVP responses are stored correctly
    assert alice_reg.additional_data is not None
    assert alice_reg.additional_data.get("rsvp_response") == "yes"

    assert bob_reg.additional_data is not None
    assert bob_reg.additional_data.get("rsvp_response") == "no"

    # Test 6: Verify template renders RSVP buttons
    template_response = client_instance.get(f"/form/{rsvp_form.url_slug}")
    assert template_response.status_code == 200

    html_content = template_response.text
    assert "Accept Invitation" in html_content
    assert "Decline" in html_content
    assert 'name="rsvp_response"' in html_content
    assert 'value="yes"' in html_content
    assert 'value="no"' in html_content


@pytest.mark.asyncio
async def test_single_submit_button_configuration(
    authenticated_client, signup_service, registration_service
):
    """Test single submit button configuration"""

    client_instance, test_user = authenticated_client

    # Create single submit form using service method
    single_form = SignupForm(
        user_id=test_user.user_id,
        title="Tech Conference 2024",
        event_date=date(2024, 9, 20),
        location="Convention Center",
        description="Professional networking and learning event",
        url_slug="tech-conference-single-456",
        is_active=True,
        button_type="single_submit",
        primary_button_text="Register Now",
        secondary_button_text=None,
    )

    result = signup_service.create_signup_form(single_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Verify button configuration
    assert single_form.button_type == "single_submit"
    assert single_form.primary_button_text == "Register Now"
    assert single_form.secondary_button_text is None

    # Submit normal registration (no RSVP response)
    form_data = {
        "name": "Conference Attendee",
        "phone": "555-3333",
        # No rsvp_response field
    }

    response = client_instance.post(f"/form/{single_form.url_slug}", data=form_data)
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True

    # Verify registration was created without RSVP response using service method
    registrations = registration_service.get_registrations_for_form(single_form.id)

    assert len(registrations) == 1, "Should have 1 registration"
    registration = registrations[0]
    assert registration.name == "Conference Attendee"

    # Should not have rsvp_response in additional_data
    if registration.additional_data:
        assert "rsvp_response" not in registration.additional_data
    else:
        assert (
            registration.additional_data is None or registration.additional_data == {}
        )

    # Verify template renders single button
    template_response = client_instance.get(f"/form/{single_form.url_slug}")
    assert template_response.status_code == 200

    html_content = template_response.text
    assert "Register Now" in html_content
    # Should not have RSVP-specific elements
    assert 'name="rsvp_response"' not in html_content
    assert 'value="yes"' not in html_content
    assert 'value="no"' not in html_content


@pytest.mark.asyncio
async def test_button_configuration_migration(signup_service, mock_current_user):
    """Test that existing forms get default button configuration"""

    test_user = mock_current_user()

    # Create a form with minimal data (simulating old forms before button config)
    minimal_form = SignupForm(
        user_id=test_user.user_id,
        title="Legacy Form",
        event_date=date(2024, 10, 1),
        location="Legacy Location",
        description="Legacy description",
        url_slug="legacy-form-789",
        is_active=True,
        # Note: not explicitly setting button configuration
    )

    result = signup_service.create_signup_form(minimal_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Should get default values
    assert minimal_form.button_type == "single_submit"  # Default from model
    assert minimal_form.primary_button_text == "Register"  # Default from model
    assert minimal_form.secondary_button_text is None
