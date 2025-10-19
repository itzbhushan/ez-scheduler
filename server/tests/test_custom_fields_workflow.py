"""Test for custom form fields end-to-end workflow"""

import logging
import re
from datetime import date, time

import pytest
from fastmcp.client import Client

from ez_scheduler.models.signup_form import FormStatus, SignupForm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_custom_fields_wedding_workflow(
    mcp_client, mock_current_user, signup_service, form_field_service
):
    """Test the complete custom fields workflow for a wedding RSVP"""
    test_user = mock_current_user()
    test_user_id = test_user.user_id

    async with Client(mcp_client) as client:
        # Step 1: Initial form request (should ask about custom fields)
        result1 = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": test_user_id,
                "message": "Create a signup form for Sarah and Michael's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown.",
            },
        )

        logger.info(f"Initial request result: {result1}")
        assert result1 is not None
        result1_str = str(result1)

        # Should ask about custom fields for a wedding
        assert (
            "additional" in result1_str.lower()
            or "custom" in result1_str.lower()
            or "meal" in result1_str.lower()
            or "guest" in result1_str.lower()
        )

        # Should NOT create the form yet - should be asking for more info
        assert (
            "form/" not in result1_str
        ), "Should ask for custom fields first, not create form immediately"

        # Step 2: User responds with custom field requirements in the same conversation
        result2 = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": test_user_id,
                "message": "Yes, I need to know how many guests they're bringing and their meal preferences. Meal options are Chicken, Beef, Vegetarian, and Vegan. No other information is needed.",
            },
        )

        logger.info(f"Custom fields request result: {result2}")
        assert result2 is not None
        result2_str = str(result2)

        # Should now create the form
        assert "form" in result2_str.lower()
        url_pattern = r"form/([a-zA-Z0-9-]+)"
        url_match = re.search(url_pattern, result2_str)
        assert url_match, "Should find form URL"
        url_slug = url_match.group(1)

        # Step 3: Verify form was created with custom fields using service
        created_form = signup_service.get_form_by_url_slug(url_slug)

        assert created_form is not None, "Form should exist in database"
        assert created_form.title and "sarah" in created_form.title.lower()
        assert created_form.event_date == date(2024, 6, 15)
        assert "grand ballroom" in created_form.location.lower()
        assert created_form.user_id == test_user_id

        # Step 4: Verify custom fields were created using service
        custom_fields = form_field_service.get_fields_by_form_id(created_form.id)

        logger.info(
            f"Retrieved {len(custom_fields) if custom_fields else 0} custom fields"
        )
        if custom_fields:
            for field in custom_fields:
                logger.info(
                    f"Field: {field.field_name} ({field.field_type}) - {field.label}"
                )

        assert (
            len(custom_fields) >= 2
        ), f"Should have at least 2 custom fields, got {len(custom_fields) if custom_fields else 0}"

        # Find guest count and meal preference fields
        guest_field = None
        meal_field = None

        for field in custom_fields:
            if "guest" in field.field_name.lower():
                guest_field = field
            elif "meal" in field.field_name.lower():
                meal_field = field

        assert guest_field is not None, "Should have guest count field"
        assert meal_field is not None, "Should have meal preference field"

        # Verify field properties
        assert guest_field.field_type == "number"
        assert guest_field.is_required is True
        assert "guest" in guest_field.label.lower()

        assert meal_field.field_type == "select"
        assert meal_field.is_required is True
        assert "meal" in meal_field.label.lower()
        assert meal_field.options is not None
        assert "Chicken" in meal_field.options
        assert "Vegetarian" in meal_field.options

        logger.info(
            f"Created form {created_form.id} with {len(custom_fields)} custom fields"
        )
        logger.info(f"Guest field: {guest_field.field_name} ({guest_field.field_type})")
        logger.info(
            f"Meal field: {meal_field.field_name} ({meal_field.field_type}) with options {meal_field.options}"
        )


@pytest.mark.asyncio
async def test_custom_fields_registration_workflow(
    mcp_client,
    mock_current_user,
    signup_service,
    form_field_service,
    registration_service,
):
    """Test form registration with custom fields"""
    # Create a test form with custom fields using service
    test_user = mock_current_user()
    test_user_id = test_user.user_id

    signup_form = SignupForm(
        user_id=test_user_id,
        title="Test Conference Registration",
        event_date=date(2024, 8, 15),
        start_time=time(9, 0),
        end_time=time(17, 0),
        location="Tech Center",
        description="Annual tech conference",
        url_slug="test-conference-12345",
        status=FormStatus.PUBLISHED,
    )

    result = signup_service.create_signup_form(signup_form, test_user)
    assert result["success"] is True

    # Add custom fields using service
    custom_fields_data = [
        {
            "field_name": "company",
            "field_type": "text",
            "label": "Company Name",
            "placeholder": "Enter your company",
            "is_required": True,
            "options": None,
            "field_order": 0,
        },
        {
            "field_name": "experience_level",
            "field_type": "select",
            "label": "Experience Level",
            "placeholder": None,
            "is_required": True,
            "options": ["Beginner", "Intermediate", "Advanced"],
            "field_order": 1,
        },
        {
            "field_name": "newsletter",
            "field_type": "checkbox",
            "label": "Subscribe to newsletter",
            "placeholder": None,
            "is_required": False,
            "options": None,
            "field_order": 2,
        },
    ]

    form_field_service.create_form_fields(signup_form.id, custom_fields_data)

    # Test registration with custom fields using service

    additional_data = {
        "company": "Tech Solutions Inc",
        "experience_level": "Advanced",
        "newsletter": True,
    }

    registration = registration_service.create_registration(
        form_id=signup_form.id,
        name="John Developer",
        email="john@techsolutions.com",
        phone="555-0123",
        additional_data=additional_data,
    )

    # Verify registration was created with custom data
    assert registration is not None
    assert registration.name == "John Developer"
    assert registration.additional_data is not None
    assert registration.additional_data["company"] == "Tech Solutions Inc"
    assert registration.additional_data["experience_level"] == "Advanced"
    assert registration.additional_data["newsletter"] is True

    logger.info(
        f"Created registration {registration.id} with additional_data: {registration.additional_data}"
    )


@pytest.mark.asyncio
async def test_custom_fields_analytics_queries(mcp_client, mock_current_user):
    """Test analytics queries with custom fields"""
    # This test would verify that the analytics system can query custom field data
    # We'll test this by using the get_form_analytics MCP tool with custom field queries

    test_user = mock_current_user()
    test_user_id = test_user.user_id

    async with Client(mcp_client) as client:
        # Test a query that involves custom fields
        result = await client.call_tool(
            "get_form_analytics",
            {
                "user_id": test_user_id,
                "analytics_query": "How many people registered with vegetarian meal preferences?",
            },
        )

        logger.info(f"Analytics query result: {result}")
        assert result is not None

        # The query should be handled gracefully even if no data exists
        result_str = str(result)
        assert "vegetarian" in result_str.lower() or "meal" in result_str.lower()


@pytest.mark.asyncio
async def test_form_creation_without_custom_fields(mcp_client, mock_current_user):
    """Test that forms can still be created without custom fields"""
    test_user = mock_current_user()
    test_user_id = test_user.user_id

    async with Client(mcp_client) as client:
        # Create a simple form without custom fields
        result = await client.call_tool(
            "create_or_update_form",
            {
                "user_id": test_user_id,
                "message": "Create a simple signup form for Team Meeting on July 10th, 2024 at Conference Room A. Just need basic contact info.",
            },
        )

        logger.info(f"Simple form result: {result}")
        assert result is not None

        # Should still create a form, might ask about custom fields but user can decline
        result_str = str(result)

        # Either creates form immediately or asks about custom fields
        assert "form" in result_str.lower() or "additional" in result_str.lower()
