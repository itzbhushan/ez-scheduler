"""Test GET /form endpoint works correctly"""

import logging
import uuid
from datetime import date, time

import pytest

from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.utils.address_utils import generate_google_maps_url

logger = logging.getLogger(__name__)


class TestFormGetEndpoint:
    """Test GET form endpoint"""

    @pytest.mark.asyncio
    async def test_get_form_endpoint(self, signup_service, authenticated_client):
        """Test that GET /form/{url_slug} works correctly"""
        client, test_user = authenticated_client

        test_form = SignupForm(
            id=uuid.uuid4(),
            user_id=test_user.user_id,
            title="Test Event Get",
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Golden Gate Bridge, San Francisco, CA",
            description="A test event for GET testing",
            url_slug="test-get-123",
            status=FormStatus.PUBLISHED,
        )

        signup_service.create_signup_form(test_form)

        # Test GET request
        response = client.get(f"/form/{test_form.url_slug}")

        logger.info(f"GET Response status: {response.status_code}")
        logger.info(f"GET Response content length: {len(response.text)}")

        # Verify the response
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert test_form.title in response.text

        expected_maps_url = generate_google_maps_url(test_form.location)
        # Check for the unescaped URL since we use |safe filter in template
        assert expected_maps_url in response.text
