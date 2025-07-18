"""Tests for create_form tool validation"""

import logging

import pytest
from fastmcp.client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_user_id",
    [
        "c42e84d6-cac9-4440-af73-7fdacd94478r",  # Invalid character 'r'
        "not-a-valid-uuid",  # Completely invalid format
        "",  # Empty string
        "123",  # Too short
        "c42e84d6-cac9-4440-af73-7fdacd94478g-extra",  # Too long
    ],
)
async def test_create_form_fails_with_invalid_UUID(mcp_client, invalid_user_id):
    """Test that create_form tool fails with various invalid user_id values"""
    async with Client(mcp_client) as client:
        # Try to call create_form with invalid user_id - should fail
        with pytest.raises(Exception):
            await client.call_tool(
                "create_form",
                {
                    "user_id": invalid_user_id,
                    "initial_request": "Create a test form",
                },
            )
