"""Test registration form serving"""

import logging
import uuid
from datetime import date, time

import pytest

from ez_scheduler.models.signup_form import FormStatus, SignupForm

logger = logging.getLogger(__name__)


class TestRegistrationForm:
    """Test registration form serving functionality"""

    @pytest.mark.asyncio
    async def test_serve_registration_form(self, signup_service, authenticated_client):
        """Test that a registration form can be served via HTTP"""
        client, test_user = authenticated_client

        # Create a test signup form
        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Test Location",
            description="A test event for testing purposes",
            url_slug="test-event-123",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test that the form can be served
        response = client.get(f"/form/{test_form.url_slug}")

        logger.info(f"Response message: {response.text}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check that the response contains expected form elements
        html_content = response.text
        logger.info(f"Response HTML length: {len(html_content)}")
        assert test_form.title in html_content
        assert test_form.location in html_content
        assert test_form.description in html_content
        assert "December 25, 2024" in html_content  # Formatted date
        assert "02:00 PM" in html_content  # Formatted start time
        assert "04:00 PM" in html_content  # Formatted end time

        # Check for required form fields
        assert 'name="name"' in html_content
        assert 'name="email"' in html_content
        assert 'name="phone"' in html_content
        assert 'type="submit"' in html_content

    @pytest.mark.asyncio
    async def test_serve_nonexistent_form(self, authenticated_client):
        """Test that requesting a non-existent form returns 404"""
        client, __ = authenticated_client

        # Test with a non-existent URL slug
        response = client.get("/form/nonexistent-form")

        print(f"Status code: {response.status_code}")
        print(f"Response text: {response.text}")

        assert response.status_code == 404
        data = response.json()
        assert "Form not found" in data["detail"]

    @pytest.mark.asyncio
    async def test_serve_inactive_form(self, signup_service, authenticated_client):
        """Test that requesting an inactive form returns 404"""
        client, test_user = authenticated_client

        # Create an archived test signup form
        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Inactive Event",
            event_date=date(2024, 12, 31),
            location="Test Location",
            description="An inactive test event",
            url_slug="inactive-event-456",
            status=FormStatus.ARCHIVED,  # Form is archived
        )

        signup_service.create_signup_form(test_form)

        # Test that the inactive form returns 404
        response = client.get(f"/form/{test_form.url_slug}")

        assert response.status_code == 404
        data = response.json()
        assert "Form not found" in data["detail"]
