"""Test form submission end-to-end functionality"""

import asyncio
import logging
import uuid
from datetime import date, time

import pytest
import requests

from ez_scheduler.models.signup_form import SignupForm
from tests.config import test_config

logger = logging.getLogger(__name__)


class TestFormSubmission:
    """Test form submission functionality"""

    @pytest.mark.asyncio
    async def test_form_submission_endpoint(self, user_service, signup_service):
        """Test that POST /form/{url_slug} processes form submission correctly"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Create a test user and form
        test_user = user_service.create_user(
            email="test1@example.com", name="Test User"
        )

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Test Event Submission",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Test Location",
            description="A test event for testing form submission",
            url_slug="test-submission-123",
            is_active=True,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with POST request
        form_data = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "555-1234",
        }

        response = requests.post(
            f"{test_config['app_base_url']}/form/{test_form.url_slug}",
            data=form_data,
        )

        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response content: {response.text}")

        # Verify the response
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

        result = response.json()
        assert result["success"] is True
        assert "registration_id" in result
        # Check that we got a personalized message containing the event name and registrant name
        message = result["message"]
        # The LLM may use variations of the event name, so check for key components
        assert "John" in message  # Registrant name (LLM may use first name)
        assert len(message) > 30  # Should be a substantial personalized message

    @pytest.mark.asyncio
    async def test_form_submission_invalid_form(self):
        """Test form submission with non-existent form returns 404"""
        # Wait for server to start
        await asyncio.sleep(2)

        form_data = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "555-1234",
        }

        response = requests.post(
            f"{test_config['app_base_url']}/form/nonexistent-form",
            data=form_data,
        )

        assert response.status_code == 404
        result = response.json()
        assert "Form not found or inactive" in result["detail"]

    @pytest.mark.asyncio
    async def test_form_submission_missing_fields(self, user_service, signup_service):
        """Test form submission with missing required fields returns 422"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Create a test form
        test_user = user_service.create_user(
            email="test4@example.com", name="Test User 2"
        )

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Test Event Missing Fields",
            event_date=date(2024, 12, 25),
            location="Test Location",
            description="A test event for testing missing fields",
            url_slug="test-missing-fields-456",
            is_active=True,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with missing email field
        form_data = {
            "name": "John Doe",
            "phone": "555-1234",
            # Missing email field
        }

        response = requests.post(
            f"{test_config['app_base_url']}/form/{test_form.url_slug}",
            data=form_data,
        )

        assert response.status_code == 422  # Unprocessable Entity for validation error
