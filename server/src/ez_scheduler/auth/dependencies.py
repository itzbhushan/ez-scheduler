"""Authentication dependencies for FastAPI"""

from typing import Optional

from authlib.jose.errors import InvalidTokenError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ez_scheduler.auth.jwt_utils import jwt_utils
from ez_scheduler.auth.models import User

# Create HTTPBearer security scheme
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)  # Don't raise 401 if missing


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


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[User]:
    """
    FastAPI dependency for optional authentication.
    Returns authenticated User if token provided, None if no token.

    This is a non-enforcing variant of get_current_user that allows unauthenticated requests.
    Use get_current_user() for endpoints that require authentication (returns 401).

    Args:
        credentials: Optional HTTP Bearer token credentials from Authorization header

    Returns:
        - Authenticated User if valid token provided
        - None if no token provided

    Raises:
        HTTPException: 401 if token is provided but invalid/expired
    """
    if not credentials:
        return None

    # Token provided - reuse existing validation logic
    return await get_current_user(credentials)


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
        HTTPException: 307 redirect to /auth/login if not authenticated
    """
    user = request.session.get("user")
    if not user:
        # Not authenticated - redirect to login
        raise HTTPException(
            status_code=307,
            headers={"Location": f"/auth/login?returnTo={request.url.path}"},
        )
    return user
