import logging
from enum import Enum
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ez_scheduler.config import config

router = APIRouter(prefix="/oauth", tags=["Authentication"], include_in_schema=False)

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


class ResponseType(Enum):
    CODE = "code"


class AuthorizeRequest(BaseModel):
    response_type: ResponseType
    client_id: str
    redirect_uri: str = config["redirect_uri"]
    scope: str = "offline_access"
    state: str
    audience: str = "https://ez-scheduler-staging.up.railway.app/gpt"


@router.get("/authorize")
async def authorize(authorize_request: Annotated[AuthorizeRequest, Query()]):
    params = {
        "response_type": authorize_request.response_type.value,
        "client_id": authorize_request.client_id,
        "redirect_uri": authorize_request.redirect_uri,
        "scope": authorize_request.scope,
        "state": authorize_request.state,
        "audience": authorize_request.audience,
    }
    uri = f"https://{config['auth0_domain']}/authorize?{urlencode(params)}"
    logger.info(f"Redirecting to {uri}")
    return RedirectResponse(uri)


class GrantType(Enum):
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH = "refresh_token"


class TokenRequest(BaseModel):
    grant_type: GrantType
    client_id: str
    code: str
    redirect_uri: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = None
    expires_in: int
    token_type: str


@router.post("/token", response_model=TokenResponse)
async def post_token(token_request: Annotated[TokenRequest, Form()]) -> TokenResponse:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = (
        f"grant_type={token_request.grant_type.value}"
        f"&client_id={token_request.client_id}"
        f"&code={token_request.code}"
        f"&redirect_uri={token_request.redirect_uri}"
        f"&client_secret={token_request.client_secret}"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{config['auth0_domain']}/oauth/token",
            data=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
