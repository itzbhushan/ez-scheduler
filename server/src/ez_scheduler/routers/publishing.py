"""Web-based form publishing endpoint with Auth0 session authentication"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ez_scheduler.auth.models import is_anonymous_user_id
from ez_scheduler.logging_config import get_logger
from ez_scheduler.models.database import get_db
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.services.signup_form_service import SignupFormService

router = APIRouter(tags=["Publishing"])
logger = get_logger(__name__)


def _publish_form(
    *,
    url_slug: str,
    user_info: dict,
    signup_form_service: SignupFormService,
):
    """Shared implementation that performs the publish transition."""
    form = signup_form_service.get_form_by_url_slug(url_slug)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    if form.status == FormStatus.PUBLISHED:
        return RedirectResponse(url=f"/form/{url_slug}", status_code=303)

    if form.status == FormStatus.ARCHIVED:
        raise HTTPException(status_code=410, detail="Form has been archived")

    authenticated_user_id = user_info.get("sub")
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="Session missing Auth0 user")

    updates = {"status": FormStatus.PUBLISHED}

    if is_anonymous_user_id(form.user_id):
        updates["user_id"] = authenticated_user_id
        logger.info(
            "Publishing form %s (%s): transferring ownership from %s to %s",
            form.id,
            url_slug,
            form.user_id,
            authenticated_user_id,
        )
    elif form.user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403, detail="You don't have permission to publish this form"
        )

    result = signup_form_service.update_signup_form(form.id, updates)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish form: {result.get('error', 'Unknown error')}",
        )

    logger.info("Successfully published form %s (%s)", form.id, url_slug)
    return RedirectResponse(url=f"/form/{url_slug}", status_code=303)


@router.post("/publish/{url_slug}")
async def publish_form_by_slug_post(
    url_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Publish action triggered by the Publish button (POST only)."""
    user_info = request.session.get("user")
    if not user_info:
        # Store intent so the follow-up GET (after login redirect) can complete safely.
        request.session["pending_publish_slug"] = url_slug
        return RedirectResponse(
            url=f"/oauth/authorize?return_to=/publish/{url_slug}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    signup_form_service = SignupFormService(db)
    return _publish_form(
        url_slug=url_slug, user_info=user_info, signup_form_service=signup_form_service
    )


@router.get("/publish/{url_slug}")
async def publish_form_by_slug_get(
    url_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Handle the post-login redirect.

    The publish action only proceeds if a prior POST stored the intent in the session.
    """
    pending_slug = request.session.pop("pending_publish_slug", None)
    if pending_slug != url_slug:
        raise HTTPException(status_code=403, detail="Publish request not authorized")

    user_info = request.session.get("user")
    if not user_info:
        return RedirectResponse(
            url=f"/oauth/authorize?return_to=/publish/{url_slug}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    signup_form_service = SignupFormService(db)
    return _publish_form(
        url_slug=url_slug, user_info=user_info, signup_form_service=signup_form_service
    )
