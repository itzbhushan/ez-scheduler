"""Test for complete form creation with database integration"""

import logging
import re
from datetime import date, time

import pytest
from fastmcp.client import Client
from sqlmodel import Session, select

from ez_scheduler.models.signup_form import SignupForm

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
            url_pattern = r"form/([a-zA-Z0-9-]+)"
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


async def test_create_form_with_end_time(
    mcp_client, test_db_session: Session, user_service
):
    """Test form creation with end time specified"""
    # Create a test user
    test_user = user_service.create_user(
        email="conference_organizer@example.com", name="Conference Organizer"
    )

    try:
        async with Client(mcp_client) as client:
            # Call the create_form tool with end time
            result = await client.call_tool(
                "create_form",
                {
                    "user_id": test_user.id,
                    "initial_request": "Create a signup form for Tech Conference 2024 on September 20th, 2024 at Convention Center. The event ends at 5:00 PM. We're hosting a tech conference with speakers and networking.",
                },
            )

            logger.info(f"Create form with end time result: {result}")

            # Verify we got a response
            assert result is not None, "Should receive a response"

            result_str = str(result)

            # Extract form ID from URL pattern
            url_pattern = r"form/([a-zA-Z0-9-]+)"
            url_match = re.search(url_pattern, result_str)

            url_slug = None
            if url_match:
                url_slug = url_match.group(1)
            else:
                pytest.fail(f"Could not find form URL pattern in response")

            # Query database using the extracted URL slug
            statement = select(SignupForm).where(SignupForm.url_slug == url_slug)
            db_result = test_db_session.exec(statement)
            created_form = db_result.first()

            # Verify form was created with correct details
            assert created_form is not None, f"Form should exist in database"
            logger.info(
                f"Created form details: start_time={created_form.start_time}, end_time={created_form.end_time}"
            )
            assert "tech" in created_form.title.lower(), f"Title should contain 'tech'"
            assert created_form.event_date == date(
                2024, 9, 20
            ), f"Event date should be September 20, 2024"
            assert (
                "convention center" in created_form.location.lower()
            ), f"Location should contain 'convention center'"
            assert (
                created_form.start_time is None
            ), "Start time should be None when not specified"
            assert created_form.end_time == time(
                17, 0, 0
            ), f"End time should be 17:00 (5:00 PM), but was {created_form.end_time}"
            assert created_form.is_active is True, "Form should be active"

    except Exception as e:
        pytest.fail(f"Failed to create form with end time: {e}")


async def test_create_form_with_start_and_end_time(
    mcp_client, test_db_session: Session, user_service
):
    """Test form creation with both start and end time specified"""
    # Create a test user
    test_user = user_service.create_user(
        email="workshop_organizer@example.com", name="Workshop Organizer"
    )

    try:
        async with Client(mcp_client) as client:
            # Call the create_form tool with both start and end time
            result = await client.call_tool(
                "create_form",
                {
                    "user_id": test_user.id,
                    "initial_request": "Create a signup form for Python Workshop on October 10th, 2024 at Tech Hub from 9:00 AM to 4:30 PM. We're teaching Python programming fundamentals with hands-on coding exercises.",
                },
            )

            logger.info(f"Create form with start and end time result: {result}")

            # Verify we got a response
            assert result is not None, "Should receive a response"

            result_str = str(result)

            # Extract form ID from URL pattern
            url_pattern = r"form/([a-zA-Z0-9-]+)"
            url_match = re.search(url_pattern, result_str)

            url_slug = None
            if url_match:
                url_slug = url_match.group(1)
            else:
                pytest.fail(f"Could not find form URL pattern in response")

            # Query database using the extracted URL slug
            statement = select(SignupForm).where(SignupForm.url_slug == url_slug)
            db_result = test_db_session.exec(statement)
            created_form = db_result.first()

            # Verify form was created with correct details
            assert created_form is not None, f"Form should exist in database"
            logger.info(
                f"Created form details: start_time={created_form.start_time}, end_time={created_form.end_time}"
            )
            assert (
                "python" in created_form.title.lower()
            ), f"Title should contain 'python'"
            assert created_form.event_date == date(
                2024, 10, 10
            ), f"Event date should be October 10, 2024"
            assert (
                "tech hub" in created_form.location.lower()
            ), f"Location should contain 'tech hub'"

            # Debug output for time values
            logger.info(
                f"Expected start_time: {time(9, 0, 0)}, actual: {created_form.start_time}"
            )
            logger.info(
                f"Expected end_time: {time(16, 30, 0)}, actual: {created_form.end_time}"
            )

            # Assert time values
            assert created_form.start_time == time(
                9, 0, 0
            ), f"Start time should be 09:00 (9:00 AM), but was {created_form.start_time}"
            assert created_form.end_time == time(
                16, 30, 0
            ), f"End time should be 16:30 (4:30 PM), but was {created_form.end_time}"
            assert created_form.is_active is True, "Form should be active"

    except Exception as e:
        pytest.fail(f"Failed to create form with start and end time: {e}")
