"""Test for complete form creation with database integration"""

import logging
import re
from datetime import date, time

import pytest
from fastmcp.client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_create_form_simple_meeting(mcp_client, signup_service):
    """Test form creation for simple meeting that doesn't trigger custom field questions"""
    # Note: user_id is now extracted from authentication context

    try:
        async with Client(mcp_client) as client:
            # Call the create_form tool with a simple meeting (shouldn't ask about custom fields)
            result = await client.call_tool(
                "create_form",
                {
                    "initial_request": "Create a signup form for Team Stand-up Meeting on September 20th, 2024 at Conference Room A. The meeting ends at 10:00 AM. Quick daily standup meeting.",
                },
            )

            logger.info(f"Create form result: {result}")

            # Verify we got a response
            assert result is not None, "Should receive a response"

            result_str = str(result)

            # For simple meetings, it might create directly or ask briefly, but should contain form URL
            url_pattern = r"form/([a-zA-Z0-9-]+)"
            url_match = re.search(url_pattern, result_str)

            url_slug = None
            if url_match:
                url_slug = url_match.group(1)
                # If form was created directly, verify it
                created_form = signup_service.get_form_by_url_slug(url_slug)

                # Verify form was created with correct details
                assert created_form is not None, f"Form should exist in database"
                logger.info(
                    f"Created form details: start_time={created_form.start_time}, end_time={created_form.end_time}"
                )
                assert (
                    "stand-up" in created_form.title.lower()
                    or "standup" in created_form.title.lower()
                    or "meeting" in created_form.title.lower()
                ), f"Title should contain meeting reference"
                assert created_form.event_date == date(
                    2024, 9, 20
                ), f"Event date should be September 20, 2024"
                assert (
                    "conference room" in created_form.location.lower()
                ), f"Location should contain 'conference room'"
                assert (
                    created_form.start_time is None
                ), "Start time should be None when not specified"
                assert created_form.end_time == time(
                    10, 0, 0
                ), f"End time should be 10:00 AM, but was {created_form.end_time}"
                assert created_form.is_active is True, "Form should be active"
                assert created_form.user_id is not None, "Form should have a user_id"
            else:
                # If no form URL found, it means LLM is asking for clarification
                # This is acceptable behavior - just verify we got a reasonable response
                assert len(result_str) > 20, "Should get a meaningful response"
                logger.info(
                    "LLM asked for clarification instead of creating form immediately"
                )

    except Exception as e:
        pytest.fail(f"Failed to create form: {e}")


@pytest.mark.asyncio
async def test_create_form_with_start_and_end_time(mcp_client, signup_service):
    """Test form creation with both start and end time specified"""
    # Note: user_id is now extracted from authentication context

    try:
        async with Client(mcp_client) as client:
            # Call the create_form tool with both start and end time
            result = await client.call_tool(
                "create_form",
                {
                    "initial_request": "Create a signup form for Python Workshop on October 10th, 2024 at Tech Hub from 9:00 AM to 4:30 PM. We're teaching Python programming fundamentals with hands-on coding exercises. Do not ask for any additional details from registering users.",
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

            # Query database using the extracted URL slug via service
            created_form = signup_service.get_form_by_url_slug(url_slug)

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
            assert created_form.start_time == time(
                9, 0, 0
            ), f"Start time should be 09:00 (9:00 AM), but was {created_form.start_time}"
            assert created_form.end_time == time(
                16, 30, 0
            ), f"End time should be 16:30 (4:30 PM), but was {created_form.end_time}"
            assert created_form.is_active is True, "Form should be active"
            assert created_form.user_id is not None, "Form should have a user_id"

    except Exception as e:
        pytest.fail(f"Failed to create form with start and end time: {e}")
