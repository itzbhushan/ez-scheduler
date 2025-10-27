"""Authentication dependencies for FastAPI"""

from typing import Optional

from authlib.jose.errors import InvalidTokenError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ez_scheduler.auth.jwt_utils import jwt_utils
from ez_scheduler.auth.models import User
from ez_scheduler.logging_config import get_logger

# Create HTTPBearer security scheme
security = HTTPBearer()

logger = get_logger(__name__)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    FastAPI dependency to extract and validate user ID from Auth0 JWT Bearer token

    Args:
        credentials: HTTP Bearer token credentials from Authorization header

    Returns:
        User with user ID extracted from valid Auth0 JWT token

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        return await jwt_utils.extract_user(token)

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(request: Request) -> Optional[User]:
    """
    FastAPI dependency for optional authentication that doesn't appear in OpenAPI spec.

    This version manually extracts the Authorization header instead of using HTTPBearer,
    which means it won't add security requirements to the OpenAPI specification.
    Use this for endpoints that should accept both authenticated and anonymous requests
    without showing auth requirements in OpenAPI/Custom GPT specs.

    Args:
        request: FastAPI Request object

    Returns:
        - Authenticated User if valid Bearer token provided
        - None if no Authorization header or no Bearer token

    Raises:
        HTTPException: 401 if token is provided but invalid/expired
    """
    auth_header = request.headers.get("Authorization")

    # TODO: Remove this before merging.
    logger.info(f"Authorization header: {auth_header}")

    if not auth_header:
        return None

    # Check if it's a Bearer token
    if not auth_header.startswith("Bearer "):
        return None

    # Extract token
    token = auth_header[7:]  # Remove "Bearer " prefix

    try:
        return await jwt_utils.extract_user(token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_auth_session(request: Request) -> dict:
    """
    Require authentication via session (web flow).
    Redirects to login if not authenticated.

    Use this for web routes that need authentication (like /publish).
    For API routes, use get_current_user() instead.

    Args:
        request: FastAPI Request object with session

    Returns:
        dict: User info from session (userinfo from Auth0)

    Raises:
        HTTPException: 307 redirect to /oauth/authorize if not authenticated
    """
    user = request.session.get("user")
    if not user:
        # Not authenticated - redirect to login
        raise HTTPException(
            status_code=307,
            headers={"Location": f"/oauth/authorize?return_to={request.url.path}"},
        )
    return user
