"""Authentication models for FastAPI"""

import uuid
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    claims: dict


def resolve_effective_user_id(
    auth_user: Optional[User], request_user_id: Optional[str] = None
) -> str:
    """
    Resolve effective user_id with security checks.

    Priority:
    1. Authenticated user (not None) → use token user_id (ignore request)
    2. Anonymous + request has anon| user_id → use request user_id
    3. Anonymous + no request user_id → generate new anon ID
    4. Anonymous + request has auth0| user_id → REJECT

    Args:
        auth_user: User from get_current_user_optional() (None if no token)
        request_user_id: Optional user_id from request body

    Returns:
        Effective user_id to use

    Raises:
        HTTPException 403: User impersonation attempt
    """
    # Authenticated - always use token
    if auth_user is not None:
        return auth_user.user_id

    # Not authenticated - check request
    if request_user_id:
        if not request_user_id.startswith("anon|"):
            raise HTTPException(
                status_code=403,
                detail="Cannot use authenticated user_id without authentication token",
            )
        return request_user_id

    # Generate new anonymous ID
    return f"anon|{uuid.uuid4()}"
