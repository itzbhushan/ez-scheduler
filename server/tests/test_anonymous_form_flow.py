"""Test anonymous form creation and publishing flow"""

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from ez_scheduler.main import app
from ez_scheduler.models.database import get_db, get_redis
from ez_scheduler.models.signup_form import FormStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def unauthenticated_client(_db_session, redis_client):
    """Create a test client without authentication, using test database and Redis"""

    # Override the database and Redis dependencies
    def get_test_db():
        return _db_session

    def get_test_redis():
        return redis_client

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_redis] = get_test_redis

    client = TestClient(app)

    yield client

    # Clean up
    app.dependency_overrides.clear()


def test_anonymous_form_creation_no_user_id(unauthenticated_client, signup_service):
    """Anonymous user creates form without providing user_id - system should generate one"""
    client = unauthenticated_client

    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for John's Birthday Party on December 15th at Central Park. "
            "Please include name, email, and phone fields. No other custom fields needed.",
        },
    )

    logger.info(f"Response status: {response.status_code}")
    logger.info(f"Response: {response.text}")

    assert (
        response.status_code == 200
    ), f"Expected 200, got {response.status_code}: {response.text}"

    response_json = response.json()
    assert "response" in response_json
    assert "user_id" in response_json

    # Verify user_id is anonymous format
    user_id = response_json["user_id"]
    assert user_id.startswith(
        "anon|"
    ), f"user_id should start with 'anon|', got {user_id}"

    # Extract form URL from response (may require follow-up if LLM asks questions)
    url_pattern = r"form/([a-zA-Z0-9-]+)"
    url_match = re.search(url_pattern, response_json["response"])

    if not url_match:
        # LLM might be asking follow-up questions, which is valid behavior
        # Just verify we got a user_id back for conversation continuity
        logger.info("LLM asking follow-up questions, which is expected behavior")
        assert user_id is not None
        return

    url_slug = url_match.group(1)
    created_form = signup_service.get_form_by_url_slug(url_slug)

    assert created_form is not None
    assert created_form.user_id == user_id
    assert created_form.status == FormStatus.DRAFT


def test_anonymous_form_creation_with_user_id(unauthenticated_client):
    """Anonymous user provides their user_id from previous response to continue conversation"""
    client = unauthenticated_client

    # First request - no user_id
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for my birthday party",
        },
    )

    assert response1.status_code == 200
    response1_json = response1.json()
    user_id = response1_json["user_id"]

    # Second request - provide user_id to continue conversation
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={
            "user_id": user_id,
            "message": "It's on December 15th at Central Park from 2-5pm",
        },
    )

    assert response2.status_code == 200
    response2_json = response2.json()

    # Verify same user_id is returned
    assert response2_json["user_id"] == user_id


def test_anonymous_user_cannot_use_authenticated_id(unauthenticated_client):
    """Anonymous user cannot use auth0| user_id without authentication"""
    client = unauthenticated_client

    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "user_id": "auth0|123456789",
            "message": "Create a form for my birthday party",
        },
    )

    logger.info(f"Response status: {response.status_code}")
    logger.info(f"Response: {response.text}")

    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    assert "authentication token" in response.text.lower()


def test_authenticated_user_overrides_anonymous_id(
    authenticated_client, signup_service
):
    """Authenticated user's token user_id always wins over request user_id"""
    client, user = authenticated_client

    # Try to provide anonymous user_id in request
    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "user_id": "anon|123-fake-id",
            "message": "Create a form for my birthday party on December 15th at Central Park",
        },
    )

    assert response.status_code == 200
    response_json = response.json()

    # Authenticated users should get user_id=None (identity comes from token)
    assert response_json["user_id"] is None

    # Verify form is created with authenticated user's ID (not the requested anon ID)
    url_pattern = r"form/([a-zA-Z0-9-]+)"
    url_match = re.search(url_pattern, response_json["response"])
    if url_match:
        url_slug = url_match.group(1)
        created_form = signup_service.get_form_by_url_slug(url_slug)
        assert created_form.user_id == user.user_id
        assert not created_form.user_id.startswith("anon|")


def test_publish_form_requires_auth(unauthenticated_client):
    """Publishing a form redirects to Auth0 login when not authenticated"""
    client = unauthenticated_client

    # Create a draft form anonymously
    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form for John's Birthday Party on December 15th from 5-7pm at Central Park. "
            "Please include name, email, and phone fields and the number of guests they are planning to bring (no max limit). "
            "No need to collect any other information.",
        },
    )

    logger.info(f"Form creation response status: {response.json()}")

    assert response.status_code == 200
    response_json = response.json()

    # Extract form URL
    url_pattern = r"form/([a-zA-Z0-9-]+)"
    url_match = re.search(url_pattern, response_json["response"])

    url_slug = url_match.group(1)

    # Load draft form preview to obtain CSRF cookie
    form_preview = client.get(f"/form/{url_slug}")
    assert form_preview.status_code == 200
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token, "Expected csrftoken cookie to be set"

    # Try to publish without authentication - should redirect to login
    publish_response = client.post(
        f"/publish/{url_slug}",
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    logger.info(f"Publish response status: {publish_response.status_code}")
    logger.info(f"Publish response headers: {publish_response.headers}")

    # Should get 307 redirect to login
    assert publish_response.status_code == 307
    assert "location" in publish_response.headers
    assert "/oauth/authorize" in publish_response.headers["location"]
