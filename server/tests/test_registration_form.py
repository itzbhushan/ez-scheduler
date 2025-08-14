"""Test registration form serving"""

import asyncio
import logging
import uuid
from datetime import date, time

import pytest
import requests

from ez_scheduler.models.signup_form import SignupForm

from .config import test_config

logger = logging.getLogger(__name__)


class TestRegistrationForm:
    """Test registration form serving functionality"""

    @pytest.mark.asyncio
    async def test_serve_registration_form(self, user_service, signup_service):
        """Test that a registration form can be served via HTTP"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Create a test user using the user service
        test_user = user_service.create_user(
            email="test2@example.com", name="Test User"
        )

        # Create a test signup form
        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Test Event",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Test Location",
            description="A test event for testing purposes",
            url_slug="test-event-123",
            is_active=True,
        )

        signup_service.create_signup_form(test_form)

        # Test that the form can be served
        response = requests.get(
            f"http://localhost:{test_config['mcp_port']}/form/{test_form.url_slug}"
        )

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
    async def test_serve_nonexistent_form(self):
        """Test that requesting a non-existent form returns 404"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Test with a non-existent URL slug
        response = requests.get(
            f"http://localhost:{test_config['mcp_port']}/form/nonexistent-form"
        )

        print(f"Status code: {response.status_code}")
        print(f"Response text: {response.text}")

        assert response.status_code == 404
        data = response.json()
        assert "Form not found or inactive" in data["detail"]

    @pytest.mark.asyncio
    async def test_serve_inactive_form(self, user_service, signup_service):
        """Test that requesting an inactive form returns 404"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Create a test user using the user service
        test_user = user_service.create_user(
            email="test5@example.com", name="Test User 5"
        )

        # Create an inactive test signup form
        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Inactive Event",
            event_date=date(2024, 12, 31),
            location="Test Location",
            description="An inactive test event",
            url_slug="inactive-event-456",
            is_active=False,  # Form is inactive
        )

        signup_service.create_signup_form(test_form)

        # Test that the inactive form returns 404
        response = requests.get(
            f"http://localhost:{test_config['mcp_port']}/form/{test_form.url_slug}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "Form not found or inactive" in data["detail"]
