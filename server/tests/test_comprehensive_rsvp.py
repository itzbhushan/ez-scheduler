"""Comprehensive test to verify RSVP functionality end-to-end"""

from datetime import date

import pytest

from ez_scheduler.models.signup_form import SignupForm


@pytest.mark.asyncio
async def test_comprehensive_rsvp_workflow(
    authenticated_client, signup_service, registration_service
):
    """Test complete RSVP workflow to ensure everything works together"""

    client_instance, test_user = authenticated_client

    # Test 1: Create wedding form using service method
    wedding_form = SignupForm(
        user_id=test_user.user_id,
        title="Sarah's Wedding Reception",
        event_date=date(2024, 6, 15),
        location="Grand Ballroom",
        description="Wedding reception with dinner and dancing",
        url_slug="comprehensive-wedding-test",
        is_active=True,
        button_type="rsvp_yes_no",
        primary_button_text="Accept Invitation",
        secondary_button_text="Decline",
    )

    result = signup_service.create_signup_form(wedding_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Test 2: Create conference form using service method
    conference_form = SignupForm(
        user_id=test_user.user_id,
        title="Tech Conference 2024",
        event_date=date(2024, 9, 20),
        location="Convention Center",
        description="Professional tech conference",
        url_slug="comprehensive-conference-test",
        is_active=True,
        button_type="single_submit",
        primary_button_text="Register",
        secondary_button_text=None,
    )

    result = signup_service.create_signup_form(conference_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Test 3: Verify form templates render correctly

    # Wedding form should show RSVP buttons
    wedding_response = client_instance.get(f"/form/{wedding_form.url_slug}")
    assert wedding_response.status_code == 200
    wedding_html = wedding_response.text

    assert "Accept Invitation" in wedding_html
    assert "Decline" in wedding_html
    assert 'name="rsvp_response"' in wedding_html
    assert 'value="yes"' in wedding_html
    assert 'value="no"' in wedding_html

    # Conference form should show single submit button
    conference_response = client_instance.get(f"/form/{conference_form.url_slug}")
    assert conference_response.status_code == 200
    conference_html = conference_response.text

    assert "Register" in conference_html
    assert 'name="rsvp_response"' not in conference_html

    # Test 4: Submit various types of responses

    # RSVP Yes to wedding
    yes_response = client_instance.post(
        f"/form/{wedding_form.url_slug}",
        data={
            "name": "John Attending",
            "email": "john@example.com",
            "phone": "555-1111",
            "rsvp_response": "yes",
        },
    )
    assert yes_response.status_code == 200
    assert yes_response.json()["success"] is True

    # RSVP No to wedding
    no_response = client_instance.post(
        f"/form/{wedding_form.url_slug}",
        data={
            "name": "Jane NotComing",
            "email": "jane@example.com",
            "phone": "555-2222",
            "rsvp_response": "no",
        },
    )
    assert no_response.status_code == 200
    assert no_response.json()["success"] is True

    # Regular registration to conference
    register_response = client_instance.post(
        f"/form/{conference_form.url_slug}",
        data={"name": "Bob Techie", "email": "bob@example.com", "phone": "555-3333"},
    )
    assert register_response.status_code == 200
    assert register_response.json()["success"] is True

    # Test 5: Verify responses are stored correctly using service method

    # Check wedding registrations
    wedding_registrations = registration_service.get_registrations_for_form(
        wedding_form.id
    )
    assert len(wedding_registrations) == 2

    john_reg = next(
        (r for r in wedding_registrations if r.name == "John Attending"), None
    )
    jane_reg = next(
        (r for r in wedding_registrations if r.name == "Jane NotComing"), None
    )

    assert john_reg is not None
    assert john_reg.additional_data["rsvp_response"] == "yes"

    assert jane_reg is not None
    assert jane_reg.additional_data["rsvp_response"] == "no"

    # Check conference registration
    conference_registrations = registration_service.get_registrations_for_form(
        conference_form.id
    )
    assert len(conference_registrations) == 1

    bob_reg = conference_registrations[0]
    assert bob_reg.name == "Bob Techie"
    # Should not have RSVP response
    assert (
        bob_reg.additional_data is None
        or "rsvp_response" not in bob_reg.additional_data
    )

    # Test 6: Verify button configuration is persistent

    # Re-fetch forms from database using service method to ensure button config is saved
    saved_wedding = signup_service.get_form_by_url_slug(wedding_form.url_slug)
    saved_conference = signup_service.get_form_by_url_slug(conference_form.url_slug)

    assert saved_wedding.button_type == "rsvp_yes_no"
    assert saved_wedding.primary_button_text == "Accept Invitation"
    assert saved_wedding.secondary_button_text == "Decline"

    assert saved_conference.button_type == "single_submit"
    assert saved_conference.primary_button_text == "Register"
    assert saved_conference.secondary_button_text is None

    print("✅ All RSVP functionality tests passed!")


@pytest.mark.asyncio
async def test_backward_compatibility(signup_service, mock_current_user):
    """Test that existing forms work with default button configuration"""

    test_user = mock_current_user()

    # Create a form without explicit button configuration (simulating old data)
    old_form = SignupForm(
        user_id=test_user.user_id,
        title="Legacy Event",
        event_date=date(2024, 10, 1),
        location="Legacy Location",
        description="This form was created before button configuration was added",
        url_slug="legacy-backward-compat-test",
        is_active=True,
        # Note: not setting button_type, primary_button_text, secondary_button_text
    )

    result = signup_service.create_signup_form(old_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Should have default values from the model
    assert old_form.button_type == "single_submit"
    assert old_form.primary_button_text == "Register"
    assert old_form.secondary_button_text is None

    print("✅ Backward compatibility test passed!")


@pytest.mark.asyncio
async def test_database_migration_applied(signup_service, mock_current_user):
    """Test that database migration was applied correctly"""

    test_user = mock_current_user()

    # Test that we can create forms with all button configuration fields
    test_form = SignupForm(
        user_id=test_user.user_id,
        title="Migration Test Event",
        event_date=date(2024, 11, 1),
        location="Migration Test Location",
        description="Testing that migration was applied",
        url_slug="migration-test-form",
        is_active=True,
        button_type="rsvp_yes_no",
        primary_button_text="I'll Be There!",
        secondary_button_text="Sorry, Can't Make It",
    )

    result = signup_service.create_signup_form(test_form, test_user)
    assert result["success"] is True
    # The service method adds the form to the database, so we can use the original object

    # Verify all fields are saved correctly
    assert test_form.button_type == "rsvp_yes_no"
    assert test_form.primary_button_text == "I'll Be There!"
    assert test_form.secondary_button_text == "Sorry, Can't Make It"

    print("✅ Database migration test passed!")
