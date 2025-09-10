"""Test RSVP button functionality via MCP integration"""

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import SignupForm


@pytest.mark.asyncio
async def test_end_to_end_rsvp_via_mcp(
    mcp_client, authenticated_client, signup_service, registration_service
):
    """Test complete RSVP workflow: MCP form creation, button detection, and response recording"""

    client_instance, test_user = authenticated_client

    # Test 1: Create RSVP form via MCP (wedding reception - should get RSVP yes/no buttons)
    async with Client(mcp_client) as mcp:
        # Create wedding reception form that should trigger RSVP buttons
        form_response = await mcp.call_tool(
            "create_form",
            {
                "user_id": test_user.user_id,
                "initial_request": "Create a form for Sarah and Michael's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown. This is an intimate celebration with dinner and dancing. I need RSVP yes/no buttons and want to collect guest count and meal preferences (Chicken, Beef, Vegetarian). No additional information is needed.",
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
                    "initial_request": "Create a form for Sarah and Michael's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown. Yes, include guest count and meal preferences with options: Chicken, Beef, Vegetarian, Vegan.",
                },
            )

    # Verify form was created successfully
    response_text = form_response.content[0].text
    assert (
        "form/" in response_text.lower() or "created" in response_text.lower()
    ), f"Expected form to be created, got: {response_text[:200]}..."

    # Test 2: Extract URL slug from response and get form via service
    # Extract URL slug from the response (format: "form/url-slug")
    import re

    url_match = re.search(r"form/([a-zA-Z0-9\-]+)", response_text)
    assert url_match, f"Could not find form URL in response: {response_text[:200]}..."
    url_slug = url_match.group(1)

    # Get the created form using service method
    form = signup_service.get_form_by_url_slug(url_slug)
    assert form is not None, f"Form should exist with URL slug: {url_slug}"

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

    # Test 3: Verify template renders RSVP buttons correctly
    template_response = client_instance.get(f"/form/{form.url_slug}")
    assert template_response.status_code == 200

    html_content = template_response.text
    assert form.primary_button_text in html_content
    assert form.secondary_button_text in html_content
    assert 'name="rsvp_response"' in html_content
    assert 'value="yes"' in html_content
    assert 'value="no"' in html_content

    # Test 4: Submit RSVP "Yes" response
    yes_form_data = {
        "name": "John Doe",
        "phone": "555-1234",
        "rsvp_response": "yes",
        "guest_count": "2",
        "meal_preference": "Chicken",
    }

    yes_response = client_instance.post(f"/form/{form.url_slug}", data=yes_form_data)
    assert yes_response.status_code == 200
    assert yes_response.json()["success"] is True

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
    assert no_response.json()["success"] is True

    # Test 6: Verify RSVP responses were recorded correctly using service method
    registrations = registration_service.get_registrations_for_form(form.id)

    assert len(registrations) >= 2, "Should have at least 2 registrations (yes and no)"

    yes_registration = next((r for r in registrations if r.name == "John Doe"), None)
    no_registration = next((r for r in registrations if r.name == "Jane Smith"), None)

    assert yes_registration is not None, "RSVP Yes registration should exist"
    assert yes_registration.additional_data is not None
    assert yes_registration.additional_data.get("rsvp_response") == "yes"

    assert no_registration is not None, "RSVP No registration should exist"
    assert no_registration.additional_data is not None
    assert no_registration.additional_data.get("rsvp_response") == "no"

    # Test 7: Test single submit form creation via MCP
    async with Client(mcp_client) as mcp:
        conference_response = await mcp.call_tool(
            "create_form",
            {
                "user_id": test_user.user_id,
                "initial_request": "Create a form for Tech Conference 2024 on September 20th at Convention Center. Keep it simple - just basic registration info, no custom fields needed.",
            },
        )

        conference_text = conference_response.content[0].text.lower()

    # Verify conference form was created
    assert (
        "form/" in conference_text.lower() or "created" in conference_text.lower()
    ), f"Expected conference form to be created, got: {conference_text[:200]}..."

    # Extract conference form URL slug and get form
    conference_match = re.search(
        r"form/([a-zA-Z0-9\-]+)", conference_response.content[0].text
    )
    assert (
        conference_match
    ), f"Could not find conference form URL in response: {conference_text[:200]}..."
    conference_slug = conference_match.group(1)

    conference_form = signup_service.get_form_by_url_slug(conference_slug)
    assert conference_form is not None

    # Verify this is a single submit form
    assert (
        conference_form.button_type == "single_submit"
    ), f"Conference should use single submit button, got {conference_form.button_type}"
    assert conference_form.primary_button_text is not None
    assert conference_form.secondary_button_text is None

    # Test single submit template rendering
    conference_html_response = client_instance.get(f"/form/{conference_form.url_slug}")
    assert conference_html_response.status_code == 200

    conference_html = conference_html_response.text
    assert conference_form.primary_button_text in conference_html
    # Should not have RSVP response inputs
    assert 'name="rsvp_response"' not in conference_html
    assert 'value="yes"' not in conference_html
    assert 'value="no"' not in conference_html


@pytest.mark.asyncio
async def test_rsvp_analytics_query(
    mcp_client, authenticated_client, signup_service, registration_service
):
    """Test that RSVP responses can be queried through analytics"""

    _, test_user = authenticated_client

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

    # Create registrations with different RSVP responses
    # RSVP Yes responses
    registration_service.create_registration(
        form_id=form.id,
        name="Yes Person 1",
        email=None,
        phone="555-0001",
        additional_data={"rsvp_response": "yes"},
    )

    registration_service.create_registration(
        form_id=form.id,
        name="Yes Person 2",
        email=None,
        phone="555-0002",
        additional_data={"rsvp_response": "yes"},
    )

    # RSVP No response
    registration_service.create_registration(
        form_id=form.id,
        name="No Person 1",
        email=None,
        phone="555-0003",
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
