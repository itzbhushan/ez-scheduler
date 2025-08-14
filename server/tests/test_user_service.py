"""Tests for UserService"""

import uuid

import pytest

from ez_scheduler.models.user import User


@pytest.mark.asyncio
async def test_create_user_with_auto_uuid(user_service):
    """Test creating a user with auto-generated UUID"""
    # Create user - UUID will be auto-generated

    user = user_service.create_user(email="auto@example.com", name="Auto UUID User")

    # Verify user object is returned
    assert isinstance(user, User)
    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.email == "auto@example.com"
    assert user.name == "Auto UUID User"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


@pytest.mark.asyncio
async def test_create_user_duplicate_email_fails(user_service):
    """Test that creating user with duplicate email fails"""
    # Create first user
    user1 = user_service.create_user(email="duplicate@example.com", name="First User")
    assert isinstance(user1, User)

    # Try to create second user with same email - should fail
    with pytest.raises(Exception) as exc_info:
        user_service.create_user(email="duplicate@example.com", name="Second User")

    assert "Failed to create user" in str(exc_info.value)
