"""Test health endpoint connectivity"""

import asyncio

import pytest
import requests
from tests.config import test_config


class TestHealthEndpoint:
    """Test health endpoint is accessible"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test that the health endpoint is accessible"""
        # Wait for server to start
        await asyncio.sleep(2)

        # Test health endpoint
        response = requests.get(f"{test_config['app_base_url']}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
