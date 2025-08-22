"""Test for Admin endpoints"""

import logging
import uuid

import pytest
import requests

from tests.config import test_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_admin_endpoint_requires_api_key():
    """Test that admin endpoint requires API key"""
    test_user_id = str(uuid.uuid4())

    try:
        # Test admin endpoint without API key
        response = requests.post(
            f"{test_config['app_base_url']}/admin/generate-token",
            json={"user_id": test_user_id},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

        # Test admin endpoint with wrong API key
        response = requests.post(
            f"{test_config['app_base_url']}/admin/generate-token",
            json={"user_id": test_user_id},
            headers={"Content-Type": "application/json", "X-Admin-Key": "wrong-key"},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        assert "Invalid admin API key" in response.text

        # Test admin endpoint with correct API key
        response = requests.post(
            f"{test_config['app_base_url']}/admin/generate-token",
            json={"user_id": test_user_id},
            headers={
                "Content-Type": "application/json",
                "X-Admin-Key": test_config["admin_api_key"],
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        response_json = response.json()
        assert "access_token" in response_json
        assert "user_id" in response_json

        logger.info("✅ Admin endpoint security test passed - API key required")

    except Exception as e:
        logger.error(f"❌ Admin endpoint security test failed: {e}")
        raise
