from enum import Enum
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ez_scheduler.auth.oauth_client import get_auth0_client
from ez_scheduler.config import config
from ez_scheduler.logging_config import get_logger

router = APIRouter(prefix="/oauth", tags=["Authentication"], include_in_schema=False)

logger = get_logger(__name__)


class ResponseType(Enum):
    CODE = "code"


class AuthorizeRequest(BaseModel):
    response_type: ResponseType | None = ResponseType.CODE
    client_id: str | None = None
    redirect_uri: str | None = None
    scope: str | None = None
    state: str | None = None
    audience: str | None = None
    return_to: str | None = None


def _safe_return_path(raw_value: str | None) -> str:
    """
    Ensure the post-login redirect stays on this origin.

    Reject absolute URLs, protocol-relative URLs, and empty values.
    """
    if not raw_value:
        return "/"

    if raw_value.startswith("//"):
        return "/"

    from urllib.parse import urlparse

    parsed = urlparse(raw_value)
    if parsed.scheme or parsed.netloc:
        return "/"

    if not raw_value.startswith("/"):
        return "/"

    return raw_value


@router.get("/authorize")
async def authorize(
    request: Request, authorize_request: Annotated[AuthorizeRequest, Query()]
):
    # If return_to is present, treat this as the browser-based Auth0 login flow.
    if authorize_request.return_to is not None:
        request.session["return_to"] = _safe_return_path(authorize_request.return_to)

        oauth = get_auth0_client(request)
        redirect_uri = authorize_request.redirect_uri or str(
            request.url_for("oauth_callback")
        )
        scope = authorize_request.scope or "openid profile email"

        extra_kwargs = {}
        if authorize_request.audience:
            extra_kwargs["audience"] = authorize_request.audience
        if authorize_request.state:
            extra_kwargs["state"] = authorize_request.state

        return await oauth.auth0.authorize_redirect(
            request, redirect_uri, scope=scope, **extra_kwargs
        )

    # Fallback: GPT/custom clients (existing behaviour)
    if (
        not authorize_request.response_type
        or not authorize_request.client_id
        or not authorize_request.redirect_uri
        or not authorize_request.scope
        or not authorize_request.state
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required OAuth parameters",
        )

    default_audience = None
    app_base_url = config.get("app_base_url")
    if app_base_url:
        default_audience = app_base_url.rstrip("/") + "/gpt"

    audience = authorize_request.audience or default_audience

    params = {
        "response_type": authorize_request.response_type.value,
        "client_id": authorize_request.client_id,
        "redirect_uri": authorize_request.redirect_uri,
        "scope": authorize_request.scope,
        "state": authorize_request.state,
    }
    if audience:
        params["audience"] = audience

    uri = f"https://{config['auth0_domain']}/authorize?{urlencode(params)}"
    logger.info(f"Redirecting to {uri}")
    return RedirectResponse(uri)


class GrantType(Enum):
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH = "refresh_token"


class TokenRequest(BaseModel):
    grant_type: GrantType
    client_id: str
    client_secret: str
    # Authorization code flow fields
    code: str | None = None
    redirect_uri: str | None = None
    # Refresh token flow fields
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    token_type: str


@router.post("/token", response_model=TokenResponse)
async def post_token(token_request: Annotated[TokenRequest, Form()]) -> TokenResponse:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # Build payload based on grant type
    payload_parts = [
        f"grant_type={token_request.grant_type.value}",
        f"client_id={token_request.client_id}",
        f"client_secret={token_request.client_secret}",
    ]

    if token_request.grant_type == GrantType.AUTHORIZATION_CODE:
        if not token_request.code or not token_request.redirect_uri:
            raise ValueError(
                "code and redirect_uri required for authorization_code flow"
            )
        payload_parts.extend(
            [f"code={token_request.code}", f"redirect_uri={token_request.redirect_uri}"]
        )
    elif token_request.grant_type == GrantType.REFRESH:
        if not token_request.refresh_token:
            raise ValueError("refresh_token required for refresh_token flow")
        payload_parts.append(f"refresh_token={token_request.refresh_token}")

    payload = "&".join(payload_parts)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{config['auth0_domain']}/oauth/token",
            data=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


@router.get("/callback", name="oauth_callback")
async def oauth_callback(request: Request):
    oauth = get_auth0_client(request)
    token = await oauth.auth0.authorize_access_token(request)

    request.session["user"] = token.get("userinfo")
    request.session["id_token"] = token.get("id_token")

    return_to = _safe_return_path(request.session.pop("return_to", None))
    return RedirectResponse(url=return_to)


@router.get("/logout")
async def oauth_logout(request: Request):
    request.session.clear()
    logout_url = (
        f'https://{config["auth0_domain"]}/v2/logout?'
        f'client_id={config["auth0_client_id"]}&'
        f"returnTo={request.base_url}"
    )
    return RedirectResponse(url=logout_url)
