"""Test for complete form creation with database integration"""

import logging
import re
from datetime import date

import pytest
from ez_scheduler.models.signup_form import SignupForm
from fastmcp.client import Client
from sqlmodel import Session, select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_create_form_complete_success(
    mcp_client, test_db_session: Session, user_service
):
    """Test complete form creation when user provides all required information"""
    # Create a test user at the start of the test
    test_user = user_service.create_user(
        email="wedding_organizer@example.com", name="Wedding Organizer"
    )

    try:
        async with Client(mcp_client) as client:
            # Call the create_form tool with complete information using the test user's UUID
            result = await client.call_tool(
                "create_form",
                {
                    "user_id": test_user.id,
                    "initial_request": "Create a signup form for Sarah's Wedding Reception on June 15th, 2024 at Grand Ballroom downtown. We're celebrating Sarah and Mike's wedding with dinner, dancing, and celebration. Please include name, email, and phone fields.",
                },
            )

            logger.info(f"Create form result: {result}")

            # Verify we got a response
            assert result is not None, "Should receive a response"

            result_str = str(result)

            # Try to extract form ID from URL pattern first
            url_pattern = r"forms/([a-zA-Z0-9-]+)"
            url_match = re.search(url_pattern, result_str)

            url_slug = None
            if url_match:
                url_slug = url_match.group(1)
            else:
                pytest.fail(f"Could not find form URL pattern or url_slug in response")
            # Query database using the extracted URL slug
            statement = select(SignupForm).where(SignupForm.url_slug == url_slug)

            # Execute the database query
            db_result = test_db_session.exec(statement)
            created_form = db_result.first()

            # Verify form was created in database with correct details
            assert (
                created_form is not None
            ), f"Form with identifier '{url_slug}' should exist in database"
            assert (
                "sarah" in created_form.title.lower()
            ), f"Title '{created_form.title}' should contain 'Sarah'"
            assert (
                "wedding" in created_form.title.lower()
            ), f"Title '{created_form.title}' should contain 'wedding'"
            assert created_form.event_date == date(
                2024, 6, 15
            ), f"Event date should be June 15, 2024 but was {created_form.event_date}"
            assert (
                "grand ballroom" in created_form.location.lower()
            ), f"Location '{created_form.location}' should contain 'Grand Ballroom'"
            assert (
                "wedding" in created_form.description.lower()
            ), f"Description should mention wedding"
            assert created_form.is_active is True, "Form should be active"
            assert (
                created_form.created_at is not None
            ), "Created timestamp should be set"
            assert (
                created_form.updated_at is not None
            ), "Updated timestamp should be set"

    except Exception as e:
        pytest.fail(f"Failed to create complete form: {e}")
