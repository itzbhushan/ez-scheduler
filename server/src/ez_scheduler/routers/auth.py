"""Auth0 web authentication routes for browser-based login"""

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ez_scheduler.config import config

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
async def login(request: Request):
    """Redirect to Auth0 login page"""
    oauth: OAuth = request.app.state.oauth
    redirect_uri = request.url_for("auth_callback")

    # Get returnTo from query params (where to go after login)
    return_to = request.query_params.get("returnTo", "/")
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
    return_to = request.session.pop("returnTo", "/")
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
