"""OAuth 2.0 discovery endpoints for MCP authentication (RFC 9728)"""

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ez_scheduler.config import config

router = APIRouter(tags=["OAuth Discovery"])


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata():
    """
    OAuth 2.0 Protected Resource Metadata (RFC 9728)

    This endpoint provides metadata about the protected MCP resource,
    including which authorization servers can issue tokens for it.
    """
    metadata = {
        "resource": f"{config['app_base_url']}/mcp",
        "authorization_servers": [f"https://{config['auth0_domain']}"],
    }

    return JSONResponse(content=metadata)


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_proxy():
    """
    Proxy to Auth0's OAuth authorization server metadata

    This proxies requests to Auth0's discovery endpoint to provide
    authorization server metadata for OAuth clients.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{config['auth0_domain']}/.well-known/oauth-authorization-server"
            )
            response.raise_for_status()
            return JSONResponse(content=response.json())
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch authorization server metadata: {e}",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Authorization server returned error: {e}",
        )


@router.get("/.well-known/openid-configuration")
async def openid_configuration_proxy():
    """
    Proxy to Auth0's OpenID Connect configuration

    This proxies requests to Auth0's OpenID Connect discovery endpoint.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{config['auth0_domain']}/.well-known/openid-configuration"
            )
            response.raise_for_status()
            return JSONResponse(content=response.json())
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch OpenID configuration: {e}"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Authorization server returned error: {e}",
        )


@router.post("/register")
async def oauth_dynamic_client_registration():
    """
    OAuth 2.0 Dynamic Client Registration endpoint

    For now, this returns a 501 Not Implemented since we don't support
    dynamic client registration yet. This prevents 404s in logs.
    """
    raise HTTPException(
        status_code=501,
        detail="Dynamic Client Registration not implemented. Please use pre-configured Auth0 application.",
    )
