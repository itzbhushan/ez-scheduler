"""Test for GPT Actions HTTP endpoints"""

import logging
import re
from datetime import date

import pytest
from sqlmodel import Session, select

from ez_scheduler.models.signup_form import SignupForm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_gpt_create_form_success(test_db_session: Session, authenticated_client):
    """Test GPT create form endpoint with complete information"""
    client, user = authenticated_client

    # user already has a proper Auth0 user ID from the fixture

    try:
        # Test the GPT create form endpoint
        response = client.post(
            "/gpt/create-form",
            json={
                "description": "Create a signup form for John's Birthday Party on December 25th, 2024 at Central Park. We're celebrating John's 30th birthday with cake, games, and fun activities. Please include name, email, and phone fields.",
            },
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
            created_form.user_id == user.user_id
        ), f"Form should belong to test user {user.user_id}"
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


def test_gpt_analytics_success(authenticated_client):
    """Test GPT analytics endpoint with various query types including date-based queries"""
    client, user = authenticated_client

    # Test queries: basic and date-based analytics queries that previously could cause errors
    test_queries = [
        "How many active forms do I have?",  # Basic query (always test this)
        "Show my events happening this week",  # Date range query - tests PostgreSQL date functions
        "How many forms did I create this month?",  # Date extraction query - tests EXTRACT functions
    ]

    for query in test_queries:
        try:
            # Test the GPT analytics endpoint
            response = client.post("/gpt/analytics", json={"query": query})

            logger.info(f"Analytics query '{query}' - Status: {response.status_code}")

            # Verify response status (should not fail with date parameter errors)
            assert (
                response.status_code == 200
            ), f"Query '{query}' failed with status {response.status_code}: {response.text}"

            # Verify response structure
            response_data = response.json()
            assert (
                "response" in response_data
            ), f"Query '{query}' missing 'response' field"

            # Verify response content
            result_str = response_data["response"]
            assert (
                len(result_str) > 0
            ), f"Analytics response for '{query}' should not be empty"

            logger.info(f"✅ Analytics query '{query}' succeeded")

        except Exception as e:
            logger.error(f"❌ Analytics query '{query}' failed: {e}")
            raise

    logger.info("✅ GPT analytics test passed - All query types succeeded")


def test_gpt_endpoints_require_authentication():
    """Test that GPT endpoints return 401 when no authentication is provided"""
    from fastapi.testclient import TestClient

    from ez_scheduler.main import app

    # Create a client without authentication override
    client = TestClient(app)

    try:
        # Test create-form endpoint without authentication
        response = client.post(
            "/gpt/create-form",
            json={"description": "Test form without auth"},
        )

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        assert (
            "Not authenticated" in response.text
        ), f"Expected 'Not authenticated' in response: {response.text}"

        # Test analytics endpoint without authentication
        response = client.post(
            "/gpt/analytics",
            json={"query": "Test analytics without auth"},
        )

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        assert (
            "Not authenticated" in response.text
        ), f"Expected 'Not authenticated' in response: {response.text}"

        logger.info(
            "✅ Authentication requirement test passed - Unauthenticated requests properly rejected"
        )

    except Exception as e:
        logger.error(f"❌ Authentication requirement test failed: {e}")
        raise
