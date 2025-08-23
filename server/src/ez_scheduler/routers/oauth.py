import logging
from enum import Enum

import requests
from fastapi import APIRouter, Depends, HTTPException, status
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
    audience: str = "https://ez-scheduler-staging.up.railway.app/gpt"


@router.get("/authorize")
async def authorize(authorizeRequest: AuthorizeRequest):
    uri = (
        f"https://{config['auth0_domain']}/authorize"
        f"?response_type={authorizeRequest.response_type.value}"
        f"&client_id={authorizeRequest.client_id}"
        f"&redirect_uri={authorizeRequest.redirect_uri}"
        f"&scope={authorizeRequest.scope}"
        f"&audience={authorizeRequest.audience}"
    )
    logger.info(f"Redirecting to {uri}")
    return RedirectResponse(uri)


@router.get("/token")
async def get_token(code: str):
    payload = (
        "grant_type=authorization_code"
        f"&client_id={config['auth0_client_id']}"
        f"&code={code}"
        f"&redirect_uri={config['redirect_uri']}"
        f"&client_secret={config['auth0_client_secret']}"
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logger.info(f"Exchanging code for token with payload: {payload}")

    response = requests.post(
        f"https://{config['auth0_domain']}/oauth/token", payload, headers=headers
    )

    return response.json()


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
async def post_token(tokenRequest: TokenRequest) -> TokenResponse:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = (
        f"grant_type={tokenRequest.grant_type.value}"
        f"&client_id={tokenRequest.client_id}"
        f"&code={tokenRequest.code}"
        f"&redirect_uri={tokenRequest.redirect_uri}"
        f"&client_secret={tokenRequest.client_secret}"
    )

    logger.info(f"Token request: {payload}")

    response = requests.post(
        f"https://{config['auth0_domain']}/oauth/token", payload, headers=headers
    )
    logger.info(f"Token response: {response.status_code} {response.json()}")
    return response.json()
