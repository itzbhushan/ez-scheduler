"""Test form submission end-to-end functionality"""

import logging
import uuid
from datetime import date, time

import pytest

from ez_scheduler.models.signup_form import FormStatus, SignupForm
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
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with POST request
        form_data = {
            "name": "John Doe",
            "email": "vb@signuppro.ai",  # Using real email to verify if email sending works
            "phone": "555-1234",
        }

        client.get(f"/form/{test_form.url_slug}")  # Prime CSRF cookie
        csrf_token = client.cookies.get("csrftoken")
        assert csrf_token, "Expected csrftoken cookie before submission"

        response = client.post(
            f"/form/{test_form.url_slug}",
            data=form_data,
            headers={"X-CSRFToken": csrf_token},
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
    async def test_form_submission_invalid_form(
        self, signup_service, authenticated_client
    ):
        """Test form submission with non-existent form returns 404"""
        client, test_user = authenticated_client

        form_data = {
            "name": "John Doe",
            "phone": "555-1234",
        }

        prime_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Prime Form",
            event_date=date(2024, 1, 1),
            location="Nowhere",
            description="Prime form to obtain CSRF cookie",
            url_slug="prime-form-for-csrf",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(prime_form)

        client.get(f"/form/{prime_form.url_slug}")
        csrf_token = client.cookies.get("csrftoken")
        assert csrf_token, "Expected csrftoken cookie before submission"

        response = client.post(
            "/form/nonexistent-form",
            data=form_data,
            headers={"X-CSRFToken": csrf_token},
        )

        assert response.status_code == 404
        result = response.json()
        assert "Form not found" in result["detail"]

    @pytest.mark.asyncio
    async def test_form_submission_email_only(
        self, signup_service, authenticated_client
    ):
        """Test form submission with email only (no phone) succeeds"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event Email Only",
            event_date=date(2024, 12, 25),
            location="Test Location",
            description="A test event for testing email-only submission",
            url_slug="test-email-only-456",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with email only
        form_data = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            # No phone field
        }

        client.get(f"/form/{test_form.url_slug}")
        csrf_token = client.cookies.get("csrftoken")
        assert csrf_token, "Expected csrftoken cookie before submission"

        response = client.post(
            f"/form/{test_form.url_slug}",
            data=form_data,
            headers={"X-CSRFToken": csrf_token},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_form_submission_phone_only(
        self, signup_service, authenticated_client
    ):
        """Test form submission with phone only (no email) succeeds"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event Phone Only",
            event_date=date(2024, 12, 25),
            location="Test Location",
            description="A test event for testing phone-only submission",
            url_slug="test-phone-only-789",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with phone only
        form_data = {
            "name": "Jane Smith",
            "phone": "555-9876",
            # No email field
        }

        client.get(f"/form/{test_form.url_slug}")
        csrf_token = client.cookies.get("csrftoken")
        assert csrf_token, "Expected csrftoken cookie before submission"

        response = client.post(
            f"/form/{test_form.url_slug}",
            data=form_data,
            headers={"X-CSRFToken": csrf_token},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_form_submission_missing_both_contact_fields(
        self, signup_service, authenticated_client
    ):
        """Test form submission with missing both email and phone returns 400"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event Missing Contact",
            event_date=date(2024, 12, 25),
            location="Test Location",
            description="A test event for testing missing contact fields",
            url_slug="test-missing-contact-999",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test form submission with missing both email and phone
        form_data = {
            "name": "John Doe",
            # Missing both email and phone
        }

        client.get(f"/form/{test_form.url_slug}")
        csrf_token = client.cookies.get("csrftoken")
        assert csrf_token, "Expected csrftoken cookie before submission"

        response = client.post(
            f"/form/{test_form.url_slug}",
            data=form_data,
            headers={"X-CSRFToken": csrf_token},
        )

        assert response.status_code == 400
        result = response.json()
        assert "email address or phone number" in result["detail"]
