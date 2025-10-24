"""Web-based form publishing endpoint with Auth0 session authentication"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ez_scheduler.auth.dependencies import require_auth_session
from ez_scheduler.logging_config import get_logger
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services.signup_form_service import SignupFormService

router = APIRouter(tags=["Publishing"])
logger = get_logger(__name__)


@router.get("/publish/{url_slug}")
@router.post("/publish/{url_slug}")
async def publish_form_by_slug(
    url_slug: str,
    request: Request,
    user_info: dict = Depends(require_auth_session),  # Session-based auth with redirect
    db: Session = Depends(get_db),
):
    """
    Publish a draft form (web-only endpoint).

    Accepts both GET and POST for one-click publish flow:
    - POST: Used by HTML form submission (primary method)
    - GET: Handles direct URL access after Auth0 callback

    Both methods are idempotent (safe to call multiple times).

    Flow (one click, no JavaScript required):
    1. User clicks "Publish" button → HTML form submits POST /publish/{url_slug}
    2. If not authenticated: require_auth_session raises 307 redirect to /auth/login
    3. Auth0 login page
    4. After login: Auth0 redirects to /auth/callback
    5. Callback redirects back to /publish/{url_slug}
    6. This handler runs with authenticated user (session populated)
    7. Transfer ownership if anonymous + publish
    8. Redirect to published form (303)
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

    # Get user_id from session (Auth0 'sub' claim)
    authenticated_user_id = user_info.get("sub")  # e.g., "auth0|123456"

    # Prepare updates
    updates = {"status": FormStatus.PUBLISHED}

    # Transfer ownership if form was created anonymously
    if form.user_id.startswith("anon|"):
        updates["user_id"] = authenticated_user_id
        logger.info(
            f"Publishing form {form.id}: transferring ownership from {form.user_id} to {authenticated_user_id}"
        )
    elif form.user_id != authenticated_user_id:
        # Form owned by different authenticated user - permission denied
        raise HTTPException(
            status_code=403, detail="You don't have permission to publish this form"
        )

    # Publish the form
    result = signup_form_service.update_signup_form(form.id, updates)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish form: {result.get('error', 'Unknown error')}",
        )

    logger.info(f"Successfully published form {form.id} ({url_slug})")

    # Redirect to published form
    return RedirectResponse(url=f"/form/{url_slug}", status_code=303)
