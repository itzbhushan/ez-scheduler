"""Utilities for retrieving the Auth0 OAuth client registered on the app"""

from authlib.integrations.starlette_client import OAuth
from fastapi import Request


def get_auth0_client(request: Request) -> OAuth:
    """
    Fetch the Auth0 OAuth client stored on the FastAPI application state.

    Raises:
        RuntimeError: if the OAuth client has not been registered.
    """
    oauth = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise RuntimeError("Auth0 OAuth client is not configured on the application.")
    return oauth
