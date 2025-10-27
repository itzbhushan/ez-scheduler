"""Auth0 web authentication routes for browser-based login"""

from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ez_scheduler.config import config

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _safe_return_path(raw_value: str | None) -> str:
    """
    Ensure the post-login redirect stays on this origin.

    Reject absolute URLs, protocol-relative URLs, and empty values.
    """
    if not raw_value:
        return "/"

    # Disallow protocol-relative or malformed values (e.g. begin with //)
    if raw_value.startswith("//"):
        return "/"

    parsed = urlparse(raw_value)

    # Reject any value that includes scheme or host components
    if parsed.scheme or parsed.netloc:
        return "/"

    # Only allow paths that start with a single /
    if not raw_value.startswith("/"):
        return "/"

    return raw_value


@router.get("/login")
@router.post("/login")
async def login(request: Request):
    """Redirect to Auth0 login page"""
    oauth: OAuth = request.app.state.oauth
    redirect_uri = request.url_for("auth_callback")

    # Get returnTo from query params (where to go after login)
    return_to = _safe_return_path(request.query_params.get("returnTo"))
    request.session["returnTo"] = return_to

    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    """Handle Auth0 callback after login"""
    oauth: OAuth = request.app.state.oauth
    token = await oauth.auth0.authorize_access_token(request)

    # Store user info in session
    request.session["user"] = token.get("userinfo")
    request.session["id_token"] = token.get("id_token")

    # Redirect to original destination
    return_to = _safe_return_path(request.session.pop("returnTo", None))
    return RedirectResponse(url=return_to)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to Auth0 logout"""
    request.session.clear()

    # Redirect to Auth0 logout endpoint
    logout_url = (
        f'https://{config["auth0_domain"]}/v2/logout?'
        f'client_id={config["auth0_client_id"]}&'
        f"returnTo={request.base_url}"
    )
    return RedirectResponse(url=logout_url)
