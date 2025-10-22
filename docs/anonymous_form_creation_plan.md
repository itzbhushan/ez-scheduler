# Anonymous Form Creation Plan

**Last Updated**: 2025-10-21
**Status**: Planning Complete - Web-Based Publish Flow

---

## Overview

This plan removes the login requirement for creating draft forms, allowing users to start building forms immediately without authentication. Users must log in only when they want to publish the form **via the web browser**.

### Previous Behavior
- Login required for both draft creation and publishing
- Publishing happens in client apps via `/gpt/publish-form` or MCP `publish_form` tool

### New Behavior
- **Draft Creation**: Login optional (in any client - Claude Desktop, ChatGPT, browser)
  - Authenticated users: Forms created with their `user_id` (e.g., `auth0|123`)
  - Anonymous users: Forms created with anonymous `user_id` (e.g., `anon|{uuid}`)
- **Draft Iteration**: Can be modified via conversation OR by viewing draft in browser
- **Publishing**: Login required, **browser-only**
  - User navigates to draft form URL in web browser
  - Clicks "Publish" button on web page
  - If not logged in: Auth0 redirects to login page
  - After login: Returns to publish endpoint, form auto-publishes
  - Ownership transfers from `anon|` to `auth0|` automatically

### Key Architectural Decision
**Publishing is web-only** - No conversation state needed for publish. User explicitly navigates to draft URL and clicks publish button. This eliminates the problem of maintaining conversation context across login sessions.

---

## User Experience Flows

### Flow 1: Authenticated User (Logged In)

```
1. User (auth0|xyz789) in Claude Desktop: "Create a birthday party form for Dec 15"
   → Form created with user_id="auth0|xyz789", status=DRAFT
   → Response: "Preview at https://app.com/form/birthday-party-abc123"

2. User opens URL in browser
   → Sees draft form with "Preview Mode" banner
   → "Publish Form" button visible
   → Registration form is disabled (can't submit registrations)

3. User clicks "Publish Form"
   → HTML form submits POST /publish/birthday-party-abc123
   → Already logged in (browser has auth session)
   → Form publishes immediately
   → Redirected to published form (303)
   → Form accepts registrations
```

**Key Points**:
- User ID tracked from the start in client
- No ownership changes needed
- One-click publish (already authenticated in browser)
- Simple HTML form submission, no JavaScript required

### Flow 2: Anonymous User (Not Logged In)

```
1. User (not logged in) in ChatGPT: "Create a birthday party form for Dec 15"
   → Form created with user_id="anon|550e8400...", status=DRAFT
   → Response: "Preview at https://app.com/form/birthday-party-abc123"

2. User opens URL in browser
   → Sees draft form with "Preview Mode" banner
   → "Publish Form" button visible
   → Registration form is disabled (can't submit registrations)

3. User clicks "Publish Form"
   → HTML form submits POST /publish/birthday-party-abc123
   → Not logged in → Auth0 redirects to login page
   → User logs in as "auth0|xyz789"
   → Auth0 redirects back to GET /publish/birthday-party-abc123
   → Backend receives authenticated GET request

4. Backend processes publish:
   → Validates user is authenticated
   → Transfers ownership: user_id="anon|550e..." → "auth0|xyz789"
   → Updates status: DRAFT → PUBLISHED
   → Returns 303 redirect to /form/birthday-party-abc123
   → Browser navigates to published form

5. Form now live:
   → No preview banner
   → Accepts registrations
   → Owned by auth0|xyz789
```

**Key Points**:
- User can create and preview without login
- Publish requires authentication (enforced by Auth0 redirect)
- Ownership transfers seamlessly when publishing
- No conversation state needed - form identified by URL slug
- Clean separation: draft creation in client, publishing in browser
- One-click publish flow (no JavaScript required for core functionality)

### Flow 3: Iterative Draft Editing (Cross-Platform)

```
1. User creates draft in Claude Desktop
   → Draft saved with URL: /form/party-abc123

2. User opens draft in browser
   → Sees preview, notices typo

3. User returns to Claude Desktop: "Change the location to Central Park"
   → Draft updated in database
   → Same URL, updated content

4. User refreshes browser
   → Sees updated draft with corrected location

5. User satisfied → clicks "Publish" in browser
   → Login flow (if needed)
   → Form published
```

---

## Technical Architecture

### 1. Anonymous User ID Format

**Format**: `anon|{uuid}`

**Examples**:
- `anon|550e8400-e29b-41d4-a716-446655440000`
- `anon|7c9e6679-7425-40de-944b-e07fc1f90ae7`

**Properties**:
- Easily distinguishable from authenticated IDs (`auth0|...`)
- Compatible with existing `user_id` string field (no schema changes)
- Globally unique (UUID v4)
- Cannot collide with Auth0 user IDs

### 2. Optional Authentication Dependency

**New Dependency**: `get_optional_auth()`

```python
# auth/dependencies.py
async def get_optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> User:
    """Returns authenticated User if token provided, otherwise anonymous User"""
    if credentials:
        return await get_current_user(credentials)

    # Generate anonymous user
    return User(user_id=f"anon|{uuid.uuid4()}", claims={})
```

**Behavior**:
- If `Authorization` header present: Validates token, returns authenticated User
- If `Authorization` header missing: Returns anonymous User with `anon|{uuid}` ID
- No exceptions thrown for missing auth (unlike `get_current_user`)

### 3. Web-Based Publish Endpoint

**New Endpoint**: `POST /publish/{url_slug}` (also accepts GET for Auth0 callback)

```python
# routers/publishing.py (NEW FILE)
@router.get("/publish/{url_slug}")  # For Auth0 callback after login
@router.post("/publish/{url_slug}")  # For HTML form submission
async def publish_form_by_slug(
    url_slug: str,
    user: User = Depends(get_current_user),  # Auth0 enforces login
    db: Session = Depends(get_db),
):
    """
    Publish a draft form (web-only endpoint).

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
    """
    signup_form_service = SignupFormService(db)

    # Get form by URL slug
    form = signup_form_service.get_form_by_url_slug(url_slug)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Verify form is a draft
    if form.status == FormStatus.PUBLISHED:
        # Already published - redirect to form
        return RedirectResponse(url=f"/form/{url_slug}", status_code=303)

    if form.status == FormStatus.ARCHIVED:
        raise HTTPException(status_code=410, detail="Form has been archived")

    # Prepare updates
    updates = {"status": FormStatus.PUBLISHED}

    # Transfer ownership if form was created anonymously
    if form.user_id.startswith("anon|"):
        updates["user_id"] = user.user_id
        logger.info(
            f"Publishing form {form.id}: transferring ownership from {form.user_id} to {user.user_id}"
        )
    elif form.user_id != user.user_id:
        # Form owned by different authenticated user - permission denied
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to publish this form"
        )

    # Publish the form
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

**Key Features**:
- Uses POST for form submission (RESTful, standard HTML forms)
- Also accepts GET for Auth0 callback (enables one-click flow)
- Auth0 redirects back to `/publish/{url_slug}` after login
- **No JavaScript required** - pure HTML form submission
- Both methods idempotent (safe to call multiple times)
- Transfers ownership from anonymous to authenticated user
- Returns 303 redirect to published form
- **No conversation state needed** - form identified by URL slug in path

### 4. Draft Form Template Updates

**Template Changes**: Add "Publish" button using simple HTML form (no JavaScript required)

```html
<!-- In templates/form.html and templates/themes/golu_form.html -->

{% if form.status.value == 'draft' %}
  <!-- Preview Mode Banner -->
  <div class="preview-banner" style="background: #fff3cd; padding: 1rem; margin-bottom: 1rem; border-radius: 4px; border: 1px solid #ffc107; text-align: center;">
    <strong>📋 Preview Mode</strong> - This form is not yet published and doesn't accept registrations.

    <!-- Simple HTML form - works without JavaScript -->
    <form action="/publish/{{ form.url_slug }}" method="POST" style="display: inline; margin-left: 1rem;">
      <button type="submit" class="btn-publish" style="padding: 0.5rem 1rem; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
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

### 5. Deprecating Old Publish Tools

**After web publish flow is tested and working**:
- ❌ Remove `/gpt/publish-form` endpoint from `routers/gpt_actions.py`
- ❌ Remove `publish_form` MCP tool from `routers/mcp_server.py`
- ✅ Keep `create_or_update_form` in both (still useful for draft creation/editing)
- ✅ Keep `archive_form` in both (archiving doesn't need web UI)
- ✅ Publishing **only** happens via browser `/publish/{url_slug}`

---

## Implementation Details

### Files to Create

#### 1. `server/src/ez_scheduler/routers/publishing.py` (NEW)
**Purpose**: Dedicated router for web-based publishing

**Complete Implementation**: See section 3 above

#### 2. `server/tests/test_web_publishing.py` (NEW)
**Purpose**: Test web-based publish flow

```python
"""Tests for web-based form publishing"""

import uuid
import pytest
from fastapi.testclient import TestClient

from ez_scheduler.models.signup_form import SignupForm, FormStatus


def test_publish_anonymous_draft_requires_login(client):
    """Publishing without auth returns 401"""
    response = client.get("/publish/some-form-slug")
    assert response.status_code == 401


def test_publish_anonymous_draft_with_auth(authenticated_client, signup_service):
    """Publishing anonymous draft transfers ownership"""
    client, user = authenticated_client

    # Create anonymous draft
    anon_form = SignupForm(
        user_id=f"anon|{uuid.uuid4()}",
        title="Test Party",
        event_date="2025-12-15",
        location="Park",
        description="Test",
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


def test_publish_already_published_form_redirects(authenticated_client, signup_service):
    """Publishing already-published form just redirects"""
    client, user = authenticated_client

    # Create published form
    published_form = SignupForm(
        user_id=user.user_id,
        title="Published Party",
        event_date="2025-12-30",
        location="Location",
        description="Test",
        url_slug=f"test-{uuid.uuid4().hex[:8]}",
        status=FormStatus.PUBLISHED  # Already published
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
**Change**: Include new publishing router

```python
from ez_scheduler.routers import publishing

# Add after other router includes
app.include_router(publishing.router)
```

#### 2. `server/src/ez_scheduler/auth/dependencies.py`
**Change**: Add `get_optional_auth()` function

```python
from typing import Optional
from uuid import uuid4

async def get_optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> User:
    """
    FastAPI dependency for optional authentication.
    Returns authenticated User if token provided, otherwise anonymous User.
    """
    if credentials:
        return await get_current_user(credentials)

    # No auth provided - create anonymous user
    return User(user_id=f"anon|{uuid4()}", claims={})
```

#### 3. `server/src/ez_scheduler/auth/models.py`
**Change**: Add utility functions

```python
import uuid

def is_anonymous_user(user: User) -> bool:
    """Check if user has anonymous ID"""
    return user.user_id.startswith("anon|")


def create_anonymous_user() -> User:
    """Create a User with anonymous ID"""
    return User(user_id=f"anon|{uuid.uuid4()}", claims={})
```

#### 4. `server/src/ez_scheduler/routers/mcp_server.py`
**Changes**:

1. Make `user_id` optional in `create_or_update_form`:
```python
@mcp.tool()
async def create_or_update_form(user_id: str | None = None, message: str) -> str:
    """Create or update a form (login optional for drafts)"""

    # Use provided user_id, or generate anonymous if not provided
    if user_id is None:
        user_id = f"anon|{uuid.uuid4()}"

    user = User(user_id=user_id, claims={})
    # ... rest of implementation unchanged
```

2. **Remove `publish_form` tool** after web publish is tested (Phase 3)

#### 5. `server/src/ez_scheduler/routers/gpt_actions.py`
**Changes**:

1. Use optional auth for create endpoint:
```python
from ez_scheduler.auth.dependencies import User, get_current_user, get_optional_auth

@router.post("/create-or-update-form")
async def gpt_create_or_update_form(
    request: GPTConversationRequest,
    user: User = Depends(get_optional_auth),  # Changed from get_current_user
    db_session=Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    redis_client=Depends(get_redis),
) -> GPTResponse:
    # user.user_id will be either "auth0|..." or "anon|..."
    # ... rest of implementation unchanged
```

2. **Remove `/gpt/publish-form` endpoint** after web publish is tested (Phase 3)

#### 6. `server/src/ez_scheduler/templates/form.html`
**Change**: Add preview banner and publish button using simple HTML form

```html
<!-- Add near top of template, after header -->
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

#### 7. `server/src/ez_scheduler/templates/themes/golu_form.html`
**Change**: Add same preview banner and publish button using simple HTML form (styled for Golu theme)

```html
<!-- Add with Golu theme styling -->
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

---

## Security Considerations

### 1. Anonymous User Isolation
- Each anonymous session gets unique `anon|{uuid}` ID
- Forms identified by public URL slug (anyone with URL can view draft)
- **Privacy consideration**: Draft URLs are guessable only if slug generation is predictable (we use UUID, so very low risk)

### 2. Publishing Authorization
- Only authenticated users can publish forms
- Auth0 enforces authentication via `get_current_user` dependency on `/publish/{url_slug}`
- Both POST and GET methods accept authentication, enabling one-click flow
- Auth0 automatically redirects unauthenticated requests to login page
- After login, Auth0 redirects back to GET `/publish/{url_slug}` with auth token
- Anonymous forms: **Any authenticated user** can publish (ownership transfer)
  - Rationale: If you have the URL and can log in, you can claim it
  - Alternative: Require auth during creation to prevent "URL sniping" (future enhancement)
- Authenticated forms: **Only owner** can publish (permission check enforced)

### 3. Ownership Transfer Validation
- Transfer only happens when:
  1. Form has anonymous `user_id` (starts with `anon|`)
  2. User is authenticated (has `auth0|` ID from `get_current_user`)
  3. Form is in DRAFT status
- Once transferred, ownership is permanent
- Logged for audit trail: `logger.info(f"Transferring form {form.id} ownership from {anon_id} to {auth_id}")`

### 4. Auth0 Configuration
- Callback URL must include `/publish/*` pattern
- After login, Auth0 redirects back to original `/publish/{url_slug}` URL
- Token managed via Auth0 SDK (session cookie or Bearer token)

### 5. Form URL Security
- URL slugs generated with UUID suffix (8 chars): `birthday-party-a1b2c3d4`
- Very low probability of collision or guessing
- Drafts are publicly viewable if URL is known (by design - for sharing/preview)

---

## Database Considerations

### Schema Changes
**None required**

The existing `user_id` field on `signup_forms` table is already a `VARCHAR/TEXT` field that accepts any string format. Both `auth0|...` and `anon|...` formats work without changes.

### Indexes
**No changes needed**

Existing indexes work with both formats:
- `ix_signup_forms_user_id` - Ownership lookups (works with both auth0| and anon| prefixes)
- `ix_signup_forms_url_slug` - Primary lookup method for web publishing endpoint

### Queries
All existing queries work unchanged:
```sql
-- Works for both anonymous and authenticated users
SELECT * FROM signup_forms WHERE user_id = 'anon|550e8400-...';
SELECT * FROM signup_forms WHERE user_id = 'auth0|123456';

-- Primary lookup for publishing
SELECT * FROM signup_forms WHERE url_slug = 'birthday-party-abc123';
```

---

## Testing Strategy

### Unit Tests

**File**: `server/tests/test_anonymous_form_flow.py`

1. Anonymous draft creation via MCP
2. Anonymous draft creation via GPT
3. Authenticated draft creation (backward compatibility)

### Integration Tests

**File**: `server/tests/test_web_publishing.py` (see "Files to Create" section above)

1. Publish requires authentication (401 without login)
2. Publish anonymous draft transfers ownership
3. Publish own authenticated draft (no transfer)
4. Publish someone else's draft (403 forbidden)
5. Publish already-published form (idempotent redirect)
6. Publish archived form (410 gone)

### End-to-End Testing

**Manual Test Checklist**:

1. ✅ Create form in Claude Desktop without login
   - Verify form created with `anon|` user_id
   - Receive preview URL in response

2. ✅ Open draft URL in browser
   - See yellow "Preview Mode" banner
   - See "Publish Form" button
   - Try to submit registration → blocked with alert

3. ✅ Click "Publish Form" (not logged in)
   - Redirected to Auth0 login page
   - URL in address bar is login page

4. ✅ Log in via Auth0
   - Complete Auth0 login flow
   - Redirected back to `/publish/{url_slug}`
   - Form auto-publishes
   - Redirected to `/form/{url_slug}` (published)

5. ✅ Verify published form
   - No preview banner visible
   - Can submit registrations
   - Check database: `user_id` changed from `anon|...` to `auth0|...`
   - `status` changed from `DRAFT` to `PUBLISHED`

6. ✅ Create form while already logged in
   - Form created with `auth0|` user_id (not anonymous)
   - Open in browser → see publish button
   - Click publish → immediate (no login redirect)

---

## Deployment Plan

### Phase 1: Add Anonymous User Support
**Goal**: Allow draft creation without login (backward compatible)

**Files**:
- `server/src/ez_scheduler/auth/dependencies.py` - Add `get_optional_auth()`
- `server/src/ez_scheduler/auth/models.py` - Add utility functions
- `server/src/ez_scheduler/routers/mcp_server.py` - Make `user_id` optional
- `server/src/ez_scheduler/routers/gpt_actions.py` - Use `get_optional_auth`
- `server/tests/test_anonymous_form_flow.py` - Test anonymous creation

**Deployment Verification**:
```bash
# Test anonymous creation
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -d '{"message": "Create test form on Dec 25 at Test Location"}'
# Expected: 200 OK, form created with anon| user_id

# Test authenticated creation (backward compat)
curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{"message": "Create test form on Dec 25 at Test Location"}'
# Expected: 200 OK, form created with auth0| user_id

# Run tests
uv run pytest server/tests/test_anonymous_form_flow.py -v
```

**Rollback**: `git revert <phase1-commit>`

### Phase 2: Add Web Publishing Endpoint
**Goal**: Enable browser-based publishing with ownership transfer

**Files**:
- `server/src/ez_scheduler/routers/publishing.py` - New router
- `server/src/ez_scheduler/main.py` - Include publishing router
- `server/src/ez_scheduler/templates/form.html` - Add preview banner + button
- `server/src/ez_scheduler/templates/themes/golu_form.html` - Add preview banner + button
- `server/tests/test_web_publishing.py` - Test web publish flow

**Deployment Verification**:
```bash
# Create anonymous draft
DRAFT_URL=$(curl -X POST http://localhost:8000/gpt/create-or-update-form \
  -H "Content-Type: application/json" \
  -d '{"message": "Create test form on Dec 25 at Test Location"}' \
  | grep -o 'form/[a-z0-9-]*' | head -1)

# Open in browser and verify preview banner
open "http://localhost:8000/$DRAFT_URL"

# Test publish endpoint (should redirect to login)
curl -I "http://localhost:8000/publish/$(echo $DRAFT_URL | cut -d'/' -f2)"
# Expected: 401 Unauthorized or redirect to Auth0

# Test publish with auth
curl -I -H "Authorization: Bearer $AUTH_TOKEN" \
  "http://localhost:8000/publish/$(echo $DRAFT_URL | cut -d'/' -f2)"
# Expected: 303 redirect to /form/{url_slug}

# Run tests
uv run pytest server/tests/test_web_publishing.py -v
```

**Rollback**: `git revert <phase2-commit>`

### Phase 3: Remove Old Publish Tools (Breaking Change)
**Goal**: Clean up deprecated programmatic publish endpoints

**Files**:
- `server/src/ez_scheduler/routers/mcp_server.py` - Remove `publish_form` tool
- `server/src/ez_scheduler/routers/gpt_actions.py` - Remove `/gpt/publish-form` endpoint

**Pre-Deployment**:
1. Announce deprecation to users
2. Update client docs to use web publishing
3. Monitor usage of old endpoints (should be zero)

**Deployment Verification**:
```bash
# Verify MCP tool removed
# (From MCP client) - publish_form should not be in list_tools()

# Verify GPT endpoint removed
curl -X POST http://localhost:8000/gpt/publish-form
# Expected: 404 Not Found

# Verify web publish still works
uv run pytest server/tests/test_web_publishing.py -v
```

**Rollback**: `git revert <phase3-commit>`

---

## Migration and Backward Compatibility

### Backward Compatibility (Phases 1 & 2)
✅ **Fully backward compatible**

- Existing authenticated flows unchanged
- Existing forms retain their `auth0|...` user IDs
- Old publish endpoints still work until Phase 3
- Draft creation works with or without auth

### Breaking Changes (Phase 3 Only)
⚠️ **Removes programmatic publish**:
- MCP `publish_form` tool no longer available
- `/gpt/publish-form` endpoint returns 404

**Migration Path**:
1. Deploy Phases 1 & 2 first
2. Monitor old publish endpoint usage → should be zero
3. Update user docs: "Publishing moved to web interface"
4. Deploy Phase 3 after confirmation

### Existing Data
**No migration needed** - all existing forms work as-is

---

## Auth0 Configuration

### Required Settings

**Allowed Callback URLs**: Add publish endpoints
```
http://localhost:8000/publish/*
https://your-domain.com/publish/*
```

**Allowed Web Origins**: Same as current
```
http://localhost:8000
https://your-domain.com
```

**Login Flow**:
1. User clicks "Publish" → HTML form submits POST `/publish/{url_slug}`
2. `get_current_user` dependency checks for auth
3. If no auth: FastAPI/Auth0 SDK redirects to Auth0 login page
4. User logs in at Auth0
5. Auth0 redirects back to GET `/publish/{url_slug}` with token
6. `get_current_user` validates token, returns User object
7. Publish handler runs, transfers ownership, publishes form
8. Redirect to `/form/{url_slug}` (now published)

---

## Future Enhancements

### 1. Protected Draft URLs
- Require Auth0 login to view drafts (not just publish)
- Add `/draft/{url_slug}` endpoint (auth required)
- Public preview requires explicit "share" action

### 2. Draft Claiming UI
- After login, show "Your Drafts" page listing all `anon|` forms in browser session
- Allow explicit "Claim Draft" action before publishing
- Prevent accidental claiming of others' anonymous drafts

### 3. Session-Based Draft Linking
- Store anonymous draft URLs in browser localStorage
- Link localStorage to user account after login
- Auto-list all session drafts on "Your Forms" page

### 4. Draft Expiration
- Auto-delete unpublished drafts after 30 days
- Show "Expires in X days" warning on draft preview
- Send email reminder if email address collected

### 5. Collaborative Drafts
- Allow sharing draft URL with others for feedback
- "Suggest Edits" mode for non-owners
- Owner approves changes before publishing

---

## Success Metrics

### Primary Metrics
- **Anonymous form creation rate**: % of drafts created without login
- **Publish conversion**: % of drafts that get published
- **Time to first draft**: Reduced friction from idea to preview
- **Login abandonment**: % who create draft but abandon at login screen

### Secondary Metrics
- **Cross-platform usage**: % who create in app, publish in browser
- **Draft iteration count**: Average edits before publishing
- **Anonymous vs authenticated creation**: User preference patterns

---

## References

- [Incremental Tasks](./tasks/anonymous-form-creation-tasks.md) - Step-by-step implementation guide
- [Preview/Publish Plan](./preview_publish_plan.md) - Original draft/publish lifecycle
- [Registration Router](../server/src/ez_scheduler/routers/registration.py) - Current form serving logic
- [Auth Dependencies](../server/src/ez_scheduler/auth/dependencies.py) - Authentication utilities
- [MCP Server](../server/src/ez_scheduler/routers/mcp_server.py) - MCP tools
- [GPT Actions](../server/src/ez_scheduler/routers/gpt_actions.py) - GPT endpoints
