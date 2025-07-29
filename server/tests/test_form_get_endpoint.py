"""Test GET /form endpoint works correctly"""

import asyncio
import logging
import uuid
from datetime import date, time

import pytest
import requests
from ez_scheduler.models.signup_form import SignupForm

from .config import test_config

logger = logging.getLogger(__name__)


class TestFormGetEndpoint:
    """Test GET form endpoint"""

    @pytest.mark.asyncio
    async def test_get_form_endpoint(self, user_service, signup_service):
        """Test that GET /form/{url_slug} works correctly"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Create a test user and form
        test_user = user_service.create_user(
            email="test3@example.com", name="Test User"
        )

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title="Test Event Get",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Test Location",
            description="A test event for GET testing",
            url_slug="test-get-123",
            is_active=True,
        )

        signup_service.create_signup_form(test_form)

        # Test GET request
        response = requests.get(
            f"http://localhost:{test_config['mcp_port']}/form/{test_form.url_slug}"
        )

        logger.info(f"GET Response status: {response.status_code}")
        logger.info(f"GET Response content length: {len(response.text)}")

        # Verify the response
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert test_form.title in response.text
