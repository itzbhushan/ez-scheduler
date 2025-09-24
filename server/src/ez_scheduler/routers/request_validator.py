"""Shared request validation and form resolution helpers.

These utilities consolidate logic used by both REST (GPT) endpoints and
MCP tools to avoid duplication and drift.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from ez_scheduler.models.signup_form import FormStatus, SignupForm


def resolve_form_or_ask(
    signup_form_service,
    user,
    form_id: Optional[str] = None,
    url_slug: Optional[str] = None,
    title_contains: Optional[str] = None,
    fallback_latest: bool = True,
) -> Optional[SignupForm]:
    """Resolve a target form by id/slug/title or fallback to latest draft.

    Returns the form if found, otherwise None. Callers should handle
    error messaging (e.g., "Form not found").
    """
    # Direct lookups first
    if form_id:
        try:
            form = signup_form_service.get_form_by_id(UUID(form_id))
            return form
        except Exception:
            return None

    if url_slug:
        form = signup_form_service.get_form_by_url_slug(url_slug)
        return form

    # Title based search among drafts
    if title_contains:
        matches = signup_form_service.search_draft_forms_by_title(
            user.user_id, title_contains
        )
        if not matches:
            return None
        if len(matches) > 1:
            return None
        return matches[0]

    # Fallback: latest draft currently being designed
    if fallback_latest:
        latest = signup_form_service.get_latest_draft_form_for_user(user.user_id)
        return latest

    return None


def validate_publish_allowed(form: SignupForm, user) -> Optional[str]:
    """Validate publish preconditions.

    Returns error message if not allowed, else None.
    """
    if form.user_id != user.user_id:
        return "You do not own this form"
    if form.status == FormStatus.ARCHIVED:
        return "Archived forms cannot be published"
    return None
