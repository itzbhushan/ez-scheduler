# Anonymous Form Creation - Implementation Tasks

**Last Updated**: 2025-10-21
**Status**: Ready for Implementation - Web-Based Publish Flow

---

## Overview

This document breaks down the anonymous form creation feature into **5 incremental tasks** that can each be deployed independently. Each task is self-contained, backward compatible (except Task 5), and includes verification steps.

**Key Change**: Publishing moved to web-only flow. Users click "Publish" button on draft form page in browser instead of using MCP/GPT tools.

See [../anonymous_form_creation_plan.md](../anonymous_form_creation_plan.md) for full technical details.

---

## Task 1: Add Anonymous User Utilities

**Goal**: Add helper functions and dependencies without changing any behavior
**Deployment Risk**: Very Low (no behavior changes)
**Time Estimate**: 1-2 hours

### Files to Modify

#### 1. `server/src/ez_scheduler/auth/models.py`

Add utility functions after the existing `User` class:

```python
import uuid

def is_anonymous_user(user: User) -> bool:
    """
    Check if user has anonymous ID.

    Args:
        user: User object to check

    Returns:
        True if user_id starts with 'anon|', False otherwise

    Examples:
        >>> is_anonymous_user(User(user_id="anon|123"))
        True
        >>> is_anonymous_user(User(user_id="auth0|xyz"))
        False
    """
    return user.user_id.startswith("anon|")


def create_anonymous_user() -> User:
    """
    Create a User object with anonymous ID.

    Returns:
        User with user_id in format 'anon|{uuid4}'

    Example:
        >>> user = create_anonymous_user()
        >>> user.user_id
        'anon|550e8400-e29b-41d4-a716-446655440000'
    """
    return User(user_id=f"anon|{uuid.uuid4()}", claims={})
```

#### 2. `server/src/ez_scheduler/auth/dependencies.py`

Add new dependency after `get_current_user`:

```python
from typing import Optional

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)  # Don't raise 401 if missing
    )
) -> User | None:
    """
    FastAPI dependency for optional authentication.
    Returns authenticated User if token provided, None if no token.

    This is a non-enforcing variant of get_current_user that allows unauthenticated requests.
    Use get_current_user() for endpoints that require authentication (returns 401).

    Args:
        credentials: Optional HTTP Bearer token credentials from Authorization header

    Returns:
        - Authenticated User if valid token provided
        - None if no token provided

    Raises:
        HTTPException: 401 if token is provided but invalid/expired

    Usage:
        @router.post("/endpoint")
        async def endpoint(user: User | None = Depends(get_current_user_optional)):
            if user is None:
                # Handle anonymous user
                user_id = f"anon|{uuid4()}"
            else:
                # Handle authenticated user
                user_id = user.user_id
    """
    if not credentials:
        return None

    # Token provided - reuse existing validation logic
    return await get_current_user(credentials)
```

### Testing

Create test file: `server/tests/test_anonymous_user_utilities.py`

```python
"""Tests for anonymous user utilities"""

import pytest
from ez_scheduler.auth.models import User, create_anonymous_user, is_anonymous_user


def test_create_anonymous_user():
    """Test creating anonymous user generates correct format"""
    user = create_anonymous_user()

    assert user.user_id.startswith("anon|")
    assert len(user.user_id) > 5  # anon| + uuid
    assert user.claims == {}


def test_is_anonymous_user_with_anon_id():
    """Test is_anonymous_user returns True for anon| IDs"""
    user = User(user_id="anon|550e8400-e29b-41d4-a716-446655440000", claims={})
    assert is_anonymous_user(user) is True


def test_is_anonymous_user_with_auth0_id():
    """Test is_anonymous_user returns False for auth0| IDs"""
    user = User(user_id="auth0|123456", claims={})
    assert is_anonymous_user(user) is False


def test_anonymous_users_have_unique_ids():
    """Test each anonymous user gets unique ID"""
    user1 = create_anonymous_user()
    user2 = create_anonymous_user()

    assert user1.user_id != user2.user_id
    assert user1.user_id.startswith("anon|")
    assert user2.user_id.startswith("anon|")
```

### Deployment Verification

```bash
# 1. Run new tests
uv run pytest server/tests/test_anonymous_user_utilities.py -v

# 2. Run all tests to ensure no regressions
uv run pytest server/tests/ -v

# 3. Start server and verify health
uv run python run_server.py
# Server should start without errors

# 4. Verify utilities are importable
python3 -c "from ez_scheduler.auth.models import create_anonymous_user, is_anonymous_user; print('✓ Utilities imported successfully')"
```

### Rollback

```bash
git revert <commit-hash>
```

---

## Task 2: Make Form Creation Authentication Optional

**Goal**: Allow draft creation without login (backward compatible)
**Deployment Risk**: Low (changes are additive)
**Time Estimate**: 2-3 hours

### Files to Modify

#### 1. `server/src/ez_scheduler/routers/mcp_server.py`

Update `create_or_update_form` tool (around line 206):

**Before**:
```python
@mcp.tool()
async def create_or_update_form(user_id: str, message: str) -> str:
    """Create or update a form through natural conversation."""
    llm_client = get_llm_client()
    user = User(user_id=user_id, claims={})
```

**After**:
```python
from uuid import uuid4  # Add import at top

@mcp.tool()
async def create_or_update_form(user_id: str | None = None, message: str) -> str:
    """Create or update a form through natural conversation.

    Authentication is optional for draft creation. If user_id is not provided,
    an anonymous user ID will be generated.

    Args:
        user_id: Auth0 user identifier (optional - generates anonymous ID if None)
        message: User's natural language message
    ...
    """
    llm_client = get_llm_client()

    # Use provided user_id or generate anonymous one
    if user_id is None:
        user_id = f"anon|{uuid4()}"

    user = User(user_id=user_id, claims={})
    # ... rest unchanged
```

#### 2. `server/src/ez_scheduler/routers/gpt_actions.py`

Update `/gpt/create-or-update-form` endpoint (around line 228):

**Before**:
```python
from ez_scheduler.auth.dependencies import User, get_current_user

@router.post("/create-or-update-form", ...)
async def gpt_create_or_update_form(
    request: GPTConversationRequest,
    user: User = Depends(get_current_user),  # Requires authentication
    db_session=Depends(get_db),
    ...
):
```

**After**:
```python
from ez_scheduler.auth.dependencies import User, get_current_user, get_current_user_optional
from ez_scheduler.auth.models import resolve_effective_user_id

# Update request model to include user_id
class GPTConversationRequest(BaseModel):
    message: str
    user_id: Optional[str] = None  # For Custom GPTs to maintain conversation

# Update response model to return user_id
class GPTResponse(BaseModel):
    response: str
    user_id: str  # Custom GPTs will remember and pass back

@router.post("/create-or-update-form", ...)
async def gpt_create_or_update_form(
    request: GPTConversationRequest,
    auth_user: User | None = Depends(get_current_user_optional),  # Authentication optional
    db_session=Depends(get_db),
    ...
):
    # Resolve effective user_id with security checks
    effective_user_id = resolve_effective_user_id(
        auth_user=auth_user,
        request_user_id=request.user_id
    )

    user = User(
        user_id=effective_user_id,
        claims=auth_user.claims if auth_user else {}
    )

    # ... process conversation ...

    # Return user_id for Custom GPTs to remember
    return GPTResponse(response=response_text, user_id=user.user_id)
```

### Testing

Add to `server/tests/test_anonymous_form_flow.py` (new file):

```python
"""Tests for anonymous form creation flow"""

import uuid
import pytest


@pytest.mark.asyncio
async def test_mcp_create_form_without_user_id(mcp_client):
    """Test creating form via MCP without providing user_id"""
    from fastmcp.client import Client

    message = "Create a birthday party form on Dec 15, 2025 at Central Park"

    async with Client(mcp_client) as client:
        result = await client.call_tool(
            "create_or_update_form",
            {"message": message}  # No user_id provided
        )

    result_text = result if isinstance(result, str) else str(result)
    assert len(result_text) > 0
    assert "form/" in result_text.lower()  # Should contain form URL


def test_gpt_create_form_without_auth(client):
    """Test creating form via GPT endpoint without authentication"""
    # Make request without Authorization header
    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a workshop form on Jan 20, 2025 at Tech Hub"
        }
    )

    # Should succeed (not 401)
    assert response.status_code == 200

    result = response.json()
    assert "response" in result
    assert len(result["response"]) > 0


def test_gpt_create_form_with_auth_still_works(authenticated_client, signup_service):
    """Test that authenticated form creation still works (backward compatibility)"""
    client, user = authenticated_client

    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a meeting form on Feb 1, 2025 at Conference Room A"
        }
    )

    assert response.status_code == 200

    # Find the created form
    draft_form = signup_service.get_latest_draft_form_for_user(user.user_id)
    assert draft_form is not None
    assert draft_form.user_id == user.user_id  # Should use authenticated user_id
    assert draft_form.user_id.startswith("auth0|")  # Not anonymous


def test_gpt_conversation_continuity_anonymous(client):
    """Test Custom GPT conversation continuity with anonymous user_id"""
    # First request - no user_id
    response1 = client.post(
        "/gpt/create-or-update-form",
        json={"message": "Create a party form"}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert "user_id" in data1
    assert data1["user_id"].startswith("anon|")

    user_id = data1["user_id"]

    # Second request - pass user_id from first response
    response2 = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "December 15th",
            "user_id": user_id  # Custom GPT passes this back
        }
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["user_id"] == user_id  # Same user_id returned


def test_gpt_security_cannot_impersonate_authenticated_user(client):
    """Test that anonymous requests cannot use auth0| user_ids"""
    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form",
            "user_id": "auth0|victim123"  # Attempt to impersonate
        }
    )

    # Should be rejected
    assert response.status_code == 403
    assert "impersonate" in response.json()["detail"].lower()


def test_gpt_security_authenticated_token_wins(authenticated_client):
    """Test that authenticated token always takes precedence over request user_id"""
    client, user = authenticated_client

    response = client.post(
        "/gpt/create-or-update-form",
        json={
            "message": "Create a form",
            "user_id": "anon|attempt-to-override"  # Should be ignored
        }
    )

    assert response.status_code == 200
    data = response.json()
    # Should use token user_id, not request user_id
    assert data["user_id"] == user.user_id
    assert data["user_id"].startswith("auth0|")
```

### Deployment Verification

```bash
# 1. Run new tests
uv run pytest server/tests/test_anonymous_form_flow.py -v

# 2. Run all tests
uv run pytest server/tests/ -v

# 3. Manual verification - MCP without user_id
# (From MCP client or Claude Desktop)
# Call: create_or_update_form with message only, no user_id
# Expected: Draft form created successfully

# 4. Manual verification - GPT without auth
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a test form on Dec 25 at Test Location"}'
# Expected: 200 OK with form creation response

# 5. Manual verification - GPT with auth (backward compat)
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{"message": "Create a test form on Dec 25 at Test Location"}'
# Expected: 200 OK with form created under authenticated user
```

### Rollback

```bash
git revert <commit-hash>
```

---

## Task 3: Add Web Publishing Endpoint

**Goal**: Enable browser-based publishing with ownership transfer
**Deployment Risk**: Low (new endpoint, doesn't affect existing flows)
**Time Estimate**: 3-4 hours

### Files to Create

#### 1. `server/src/ez_scheduler/routers/publishing.py` (NEW FILE)

```python
"""Web-based form publishing endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ez_scheduler.auth.dependencies import User, get_current_user
from ez_scheduler.logging_config import get_logger
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services.signup_form_service import SignupFormService

router = APIRouter(tags=["Publishing"])
logger = get_logger(__name__)


@router.get("/publish/{url_slug}")  # For Auth0 callback after login
@router.post("/publish/{url_slug}")  # For HTML form submission
async def publish_form_by_slug(
    url_slug: str,
    user: User = Depends(get_current_user),  # Auth0 enforces login
    db: Session = Depends(get_db),
):
    """
    Publish a draft form identified by URL slug.

    Accepts both GET and POST for one-click publish flow:
    - POST: Used by HTML form submission (primary method)
    - GET: Used by Auth0 callback after login redirect

    Both methods are idempotent (safe to call multiple times).

    Flow (one click, no JavaScript required):
    1. User clicks "Publish" button → HTML form submits POST /publish/{url_slug}
    2. If not authenticated: Auth0 redirects to login
    3. After login: Auth0 redirects to GET /publish/{url_slug}
    4. This handler runs with authenticated user
    5. Transfer ownership if anonymous + publish
    6. Redirect to published form (303)

    Ownership Transfer:
    - If form has anonymous user_id (anon|*): transfer to authenticated user
    - If form already owned by authenticated user: no transfer needed
    - If form owned by different user: permission denied (403)
    """
    signup_form_service = SignupFormService(db)

    # Get form
    form = signup_form_service.get_form_by_url_slug(url_slug)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Check if already published
    if form.status == FormStatus.PUBLISHED:
        return RedirectResponse(url=f"/form/{url_slug}", status_code=303)

    # Check if archived
    if form.status == FormStatus.ARCHIVED:
        raise HTTPException(status_code=410, detail="Form has been archived")

    # Prepare updates
    updates = {"status": FormStatus.PUBLISHED}

    # Transfer ownership if anonymous
    if form.user_id.startswith("anon|"):
        updates["user_id"] = user.user_id
        logger.info(
            f"Publishing form {form.id}: transferring ownership from {form.user_id} to {user.user_id}"
        )
    elif form.user_id != user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to publish this form"
        )

    # Publish
    result = signup_form_service.update_signup_form(form.id, updates)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish form: {result.get('error', 'Unknown error')}"
        )

    logger.info(f"Successfully published form {form.id} ({url_slug})")

    # Redirect to published form
    return RedirectResponse(url=f"/form/{url_slug}", status_code=303)
```

#### 2. `server/tests/test_web_publishing.py` (NEW FILE)

```python
"""Tests for web-based form publishing"""

import uuid
import pytest

from ez_scheduler.models.signup_form import SignupForm, FormStatus


def test_publish_requires_authentication(client):
    """Publishing without auth returns 401"""
    response = client.get("/publish/some-form-slug")
    assert response.status_code == 401


def test_publish_anonymous_draft_transfers_ownership(authenticated_client, signup_service):
    """Publishing anonymous draft transfers ownership to authenticated user"""
    client, user = authenticated_client

    # Create anonymous draft
    anon_form = SignupForm(
        user_id=f"anon|{uuid.uuid4()}",
        title="Test Party",
        event_date="2025-12-15",
        location="Park",
        description="Test event",
        url_slug=f"test-{uuid.uuid4().hex[:8]}",
        status=FormStatus.DRAFT
    )

    created_form = signup_service.create_signup_form_with_details(
        anon_form, custom_fields=[], timeslot_schedule=None
    )

    # Publish via web endpoint
    response = client.get(f"/publish/{created_form.url_slug}", follow_redirects=False)

    # Should redirect to published form
    assert response.status_code == 303
    assert response.headers["location"] == f"/form/{created_form.url_slug}"

    # Verify ownership transferred
    published_form = signup_service.reload_form(created_form.id)
    assert published_form.user_id == user.user_id
    assert published_form.status == FormStatus.PUBLISHED


def test_publish_own_draft_succeeds(authenticated_client, signup_service):
    """Publishing own authenticated draft succeeds"""
    client, user = authenticated_client

    # Create authenticated draft
    draft = SignupForm(
        user_id=user.user_id,
        title="My Party",
        event_date="2025-12-20",
        location="Home",
        description="Test",
        url_slug=f"test-{uuid.uuid4().hex[:8]}",
        status=FormStatus.DRAFT
    )

    created_form = signup_service.create_signup_form_with_details(
        draft, custom_fields=[], timeslot_schedule=None
    )

    # Publish
    response = client.get(f"/publish/{created_form.url_slug}", follow_redirects=False)
    assert response.status_code == 303

    # Verify published
    published_form = signup_service.reload_form(created_form.id)
    assert published_form.user_id == user.user_id  # Unchanged
    assert published_form.status == FormStatus.PUBLISHED


def test_publish_others_draft_fails(authenticated_client, signup_service):
    """Publishing another user's draft returns 403"""
    client, user = authenticated_client

    # Create draft owned by different user
    other_user_id = f"auth0|{uuid.uuid4()}"
    draft = SignupForm(
        user_id=other_user_id,
        title="Other's Party",
        event_date="2025-12-25",
        location="Location",
        description="Test",
        url_slug=f"test-{uuid.uuid4().hex[:8]}",
        status=FormStatus.DRAFT
    )

    created_form = signup_service.create_signup_form_with_details(
        draft, custom_fields=[], timeslot_schedule=None
    )

    # Try to publish
    response = client.get(f"/publish/{created_form.url_slug}")
    assert response.status_code == 403


def test_publish_already_published_is_idempotent(authenticated_client, signup_service):
    """Publishing already-published form just redirects (idempotent)"""
    client, user = authenticated_client

    # Create published form
    published_form = SignupForm(
        user_id=user.user_id,
        title="Published Party",
        event_date="2025-12-30",
        location="Location",
        description="Test",
        url_slug=f"test-{uuid.uuid4().hex[:8]}",
        status=FormStatus.PUBLISHED
    )

    created_form = signup_service.create_signup_form_with_details(
        published_form, custom_fields=[], timeslot_schedule=None
    )

    # Try to publish again
    response = client.get(f"/publish/{created_form.url_slug}", follow_redirects=False)

    # Should redirect (idempotent)
    assert response.status_code == 303
    assert response.headers["location"] == f"/form/{created_form.url_slug}"
```

### Files to Modify

#### 1. `server/src/ez_scheduler/main.py`

Add new router import and include:

```python
from ez_scheduler.routers import publishing

# Add after other router includes
app.include_router(publishing.router)
```

#### 2. `server/src/ez_scheduler/templates/form.html`

Add preview banner with simple HTML form (no JavaScript required):

```html
<!-- Add near top of template, before main content -->
{% if form.status.value == 'draft' %}
<div class="preview-banner" style="background: #fff3cd; padding: 1rem; margin-bottom: 1.5rem; border-radius: 4px; border: 1px solid #ffc107; text-align: center;">
  <strong style="font-size: 1.1em;">📋 Preview Mode</strong>
  <p style="margin: 0.5rem 0;">This form is not yet published and doesn't accept registrations.</p>

  <!-- Simple HTML form - works without JavaScript -->
  <form action="/publish/{{ form.url_slug }}" method="POST" style="display: inline; margin-top: 0.5rem;">
    <button type="submit" class="btn-publish" style="padding: 0.6rem 1.5rem; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
      Publish Form
    </button>
  </form>
</div>

<script>
// Disable registration form submission for drafts
(function() {
  const registrationForm = document.querySelector('form.registration-form');
  if (registrationForm) {
    registrationForm.addEventListener('submit', function(e) {
      e.preventDefault();
      alert('This form is in preview mode. Click "Publish Form" at the top to make it live and accept registrations.');
    });
  }
})();
</script>
{% endif %}
```

#### 3. `server/src/ez_scheduler/templates/themes/golu_form.html`

Add styled preview banner with simple HTML form (match Golu theme):

```html
<!-- Add near top of template -->
{% if form.status.value == 'draft' %}
<div class="preview-banner golu-preview" style="background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); padding: 1.5rem; margin-bottom: 2rem; border-radius: 8px; border: 2px solid #ffc107; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
  <strong style="font-size: 1.2em; color: #856404;">📋 Preview Mode</strong>
  <p style="margin: 0.5rem 0; color: #856404;">This invitation is not yet live and doesn't accept RSVPs.</p>

  <!-- Simple HTML form - works without JavaScript -->
  <form action="/publish/{{ form.url_slug }}" method="POST" style="display: inline; margin-top: 0.8rem;">
    <button type="submit" class="btn-publish golu-btn" style="padding: 0.8rem 2rem; background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; box-shadow: 0 4px 12px rgba(0,123,255,0.3); transition: all 0.3s;">
      Publish Form
    </button>
  </form>
</div>

<script>
// Disable registration form submission for drafts (Golu theme version)
(function() {
  const registrationForm = document.querySelector('form:not([action*="publish"])');
  if (registrationForm) {
    registrationForm.addEventListener('submit', function(e) {
      e.preventDefault();
      alert('This invitation is in preview mode. Click "Publish Form" to make it live and accept RSVPs.');
    });
  }
})();
</script>
{% endif %}
```

### Deployment Verification

```bash
# 1. Run new tests
uv run pytest server/tests/test_web_publishing.py -v

# 2. Create anonymous draft via API
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -d '{"message": "Create test form on Dec 25, 2025 at Test Location"}' \
  | grep -o 'form/[a-z0-9-]*' | head -1
# Save the form URL slug

# 3. Open draft in browser
open "http://localhost:8000/form/<url-slug>"
# Should see yellow preview banner with "Publish Form" button

# 4. Click "Publish Form" button
# Should redirect to Auth0 login (if not logged in)

# 5. After login, verify form published
# Should redirect to /form/<url-slug> with no banner

# 6. Check database
# SELECT user_id, status FROM signup_forms WHERE url_slug = '<url-slug>';
# Should show auth0|... user_id and status='published'
```

### Rollback

```bash
git revert <commit-hash>
```

---

## Task 4: Update Auth0 Configuration

**Goal**: Configure Auth0 to allow publish endpoint callbacks
**Deployment Risk**: Low (configuration change only)
**Time Estimate**: 30 minutes

### Auth0 Settings to Update

1. **Log in to Auth0 Dashboard**
   - Go to Applications → Your Application

2. **Add Callback URLs**
   - Navigate to "Settings" tab
   - Find "Allowed Callback URLs" field
   - Add (comma-separated):
     ```
     http://localhost:8000/publish/*,
     https://your-staging-domain.com/publish/*,
     https://your-production-domain.com/publish/*
     ```

3. **Verify Web Origins**
   - Ensure "Allowed Web Origins" includes:
     ```
     http://localhost:8000,
     https://your-staging-domain.com,
     https://your-production-domain.com
     ```

4. **Save Changes**

### Verification

```bash
# Test login redirect flow
# 1. Create anonymous draft (get URL slug)
# 2. Navigate to /publish/<url-slug> in browser (not logged in)
# 3. Should redirect to Auth0 login page
# 4. Log in
# 5. Should redirect back to /publish/<url-slug>
# 6. Should auto-publish and redirect to /form/<url-slug>
```

### Rollback

- Remove `/publish/*` from Allowed Callback URLs in Auth0 dashboard

---

## Task 5: Remove Old Publish Tools (Breaking Change)

**Goal**: Clean up deprecated programmatic publish endpoints
**Deployment Risk**: High (breaking change - removes existing tools)
**Time Estimate**: 1 hour

⚠️ **WARNING**: This is a breaking change. Deploy only after:
1. Tasks 1-4 deployed and verified
2. Users notified of change
3. Confirmed no usage of old publish endpoints

### Pre-Deployment Checklist

- [ ] Tasks 1-4 deployed to production
- [ ] Web publishing tested and working
- [ ] Users notified publish moved to web
- [ ] Monitor logs: confirm zero usage of `/gpt/publish-form` and MCP `publish_form`
- [ ] Documentation updated

### Files to Modify

#### 1. `server/src/ez_scheduler/routers/mcp_server.py`

Remove the entire `publish_form` tool (around lines 58-146):

```python
# DELETE THIS ENTIRE FUNCTION:
@mcp.tool()
async def publish_form(user_id: str) -> str:
    """Publish the draft form from the active conversational context."""
    # ... entire function body ...
```

#### 2. `server/src/ez_scheduler/routers/gpt_actions.py`

Remove the entire `/gpt/publish-form` endpoint (around lines 78-163):

```python
# DELETE THIS ENTIRE FUNCTION:
@router.post(
    "/publish-form",
    summary="Publish the draft form from current conversation",
    response_model=GPTResponse,
    openapi_extra={"x-openai-isConsequential": True},
)
async def gpt_publish_form(
    user: User = Depends(get_current_user),
    db_session=Depends(get_db),
    redis_client=Depends(get_redis),
) -> GPTResponse:
    # ... entire function body ...
```

### Deployment Verification

```bash
# 1. Verify MCP tool removed
# From MCP client: list_tools()
# Expected: publish_form not in list

# 2. Verify GPT endpoint removed
curl -X POST http://localhost:8000/gpt/publish-form
# Expected: 404 Not Found

# 3. Verify web publish still works
uv run pytest server/tests/test_web_publishing.py -v

# 4. Verify form creation still works
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -d '{"message": "Create test form on Dec 31, 2025 at Location"}'
# Expected: 200 OK
```

### Rollback

```bash
git revert <commit-hash>
```

---

## Summary

### Deployment Order

1. **Task 1** → Deploy → Verify (no behavior changes)
2. **Task 2** → Deploy → Verify (anonymous creation enabled)
3. **Task 3** → Deploy → Verify (web publish enabled)
4. **Task 4** → Configure Auth0 (callback URLs)
5. **Pause** → Monitor usage → Notify users
6. **Task 5** → Deploy (remove old tools)

### Total Implementation Time

- Task 1: 1-2 hours (utilities)
- Task 2: 2-3 hours (optional auth)
- Task 3: 3-4 hours (web publish)
- Task 4: 30 minutes (Auth0 config)
- Task 5: 1 hour (cleanup)

**Total**: 7.5-10.5 hours

### Verification Checklist

After each deployment:

- [ ] App starts without errors
- [ ] Health check passes (`curl http://localhost:8000/health`)
- [ ] All tests pass
- [ ] No errors in logs
- [ ] Manual testing successful

### Risk Mitigation

- Tasks 1-4 are fully backward compatible
- Each task can be independently rolled back
- Task 5 requires coordination and monitoring
- Gradual rollout minimizes risk

---

## References

- [Full Technical Plan](../anonymous_form_creation_plan.md)
- [MCP Server](../../server/src/ez_scheduler/routers/mcp_server.py)
- [GPT Actions](../../server/src/ez_scheduler/routers/gpt_actions.py)
- [Auth Dependencies](../../server/src/ez_scheduler/auth/dependencies.py)
- [Form Templates](../../server/src/ez_scheduler/templates/)
