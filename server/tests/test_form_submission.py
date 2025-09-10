"""Test form submission end-to-end functionality"""

import logging
import uuid
from datetime import date, time

import pytest

from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.utils.address_utils import generate_google_maps_url

logger = logging.getLogger(__name__)


class TestFormSubmission:
    """Test form submission functionality"""

    @pytest.mark.asyncio
    async def test_form_submission_endpoint(self, signup_service, authenticated_client):
        """Test that POST /form/{url_slug} processes form submission correctly"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event Submission",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Golden Gate Bridge, San Francisco, CA",
            description="A test event for testing form submission",
            url_slug="test-submission-123",
            is_active=True,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with POST request
        form_data = {
            "name": "John Doe",
            "email": "vb@signuppro.ai",  # Using real email to verify if email sending works
            "phone": "555-1234",
        }

        response = client.post(
            f"/form/{test_form.url_slug}",
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
    async def test_form_submission_invalid_form(self, authenticated_client):
        """Test form submission with non-existent form returns 404"""
        client, __ = authenticated_client

        form_data = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "555-1234",
        }

        response = client.post(
            "/form/nonexistent-form",
            data=form_data,
        )

        assert response.status_code == 404
        result = response.json()
        assert "Form not found or inactive" in result["detail"]

    @pytest.mark.asyncio
    async def test_form_submission_missing_fields(
        self, signup_service, authenticated_client
    ):
        """Test form submission with missing required fields returns 400"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
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

        response = client.post(
            f"/form/{test_form.url_slug}",
            data=form_data,
        )

        assert response.status_code == 400  # Unprocessable Entity for validation error
