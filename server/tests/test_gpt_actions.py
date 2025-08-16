"""Test for GPT Actions HTTP endpoints"""

import asyncio
import logging
import re
import uuid
from datetime import date

import pytest
import requests
from sqlmodel import Session, select

from ez_scheduler.models.signup_form import SignupForm
from tests.config import test_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_gpt_create_form_success(test_db_session: Session, user_service):
    """Test GPT create form endpoint with complete information"""
    # Create a test user
    test_user = user_service.create_user(
        email="party_planner@example.com", name="Party Planner"
    )

    try:
        # Wait for server to start
        await asyncio.sleep(2)

        # Test the GPT create form endpoint
        response = requests.post(
            f"{test_config['app_base_url']}/gpt/create-form",
            json={
                "user_id": str(test_user.id),
                "description": "Create a signup form for John's Birthday Party on December 25th, 2024 at Central Park. We're celebrating John's 30th birthday with cake, games, and fun activities. Please include name, email, and phone fields.",
            },
            headers={"Content-Type": "application/json"},
        )

        logger.info(f"GPT create form response status: {response.status_code}")
        logger.info(f"GPT create form response: {response.text}")

        # Verify response status
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"

        # Parse JSON response
        response_json = response.json()
        assert (
            "response" in response_json
        ), f"Expected 'response' field in JSON: {response_json}"
        result_str = response_json["response"]

        # Extract form URL slug from response
        url_pattern = r"form/([a-zA-Z0-9-]+)"
        url_match = re.search(url_pattern, result_str)

        assert url_match, f"Could not find form URL pattern in response: {result_str}"
        url_slug = url_match.group(1)

        # Query database to verify form was created
        statement = select(SignupForm).where(SignupForm.url_slug == url_slug)
        db_result = test_db_session.exec(statement)
        created_form = db_result.first()

        # Verify form was created in database with correct details
        assert (
            created_form is not None
        ), f"Form with slug '{url_slug}' should exist in database"
        assert (
            created_form.user_id == test_user.id
        ), f"Form should belong to test user {test_user.id}"
        assert (
            "john" in created_form.title.lower()
        ), f"Title '{created_form.title}' should contain 'John'"
        assert (
            "birthday" in created_form.title.lower()
        ), f"Title '{created_form.title}' should contain 'birthday'"
        assert created_form.event_date == date(
            2024, 12, 25
        ), f"Event date should be December 25, 2024 but was {created_form.event_date}"
        assert (
            "central park" in created_form.location.lower()
        ), f"Location '{created_form.location}' should contain 'Central Park'"
        assert (
            "birthday" in created_form.description.lower()
        ), f"Description should mention birthday"
        assert created_form.is_active is True, "Form should be active"

        logger.info(
            f"✅ GPT form creation test passed - Form {url_slug} created successfully"
        )

    except Exception as e:
        logger.error(f"❌ GPT form creation test failed: {e}")
        raise


@pytest.mark.asyncio
async def test_gpt_analytics_success(test_db_session: Session, user_service):
    """Test GPT analytics endpoint"""
    # Create a test user
    test_user = user_service.create_user(
        email="analytics_user@example.com", name="Analytics User"
    )

    try:
        # Test the GPT analytics endpoint
        response = requests.post(
            f"{test_config['app_base_url']}/gpt/analytics",
            json={
                "user_id": str(test_user.id),
                "query": "How many active forms do I have?",
            },
            headers={"Content-Type": "application/json"},
        )

        logger.info(f"GPT analytics response status: {response.status_code}")
        logger.info(f"GPT analytics response: {response.text}")

        # Verify response status
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"

        # Parse JSON response
        response_json = response.json()
        assert (
            "response" in response_json
        ), f"Expected 'response' field in JSON: {response_json}"
        result_str = response_json["response"]

        # Verify we got a meaningful response (should contain analytics information or error message)
        assert len(result_str) > 0, "Analytics response should not be empty"

        logger.info(f"✅ GPT analytics test passed - Got analytics response")

    except Exception as e:
        logger.error(f"❌ GPT analytics test failed: {e}")
        raise
