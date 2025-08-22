"""Admin router for testing and development utilities"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ez_scheduler.auth.jwt_utils import jwt_utils

router = APIRouter(prefix="/admin", tags=["Admin"])


class TokenRequest(BaseModel):
    user_id: uuid.UUID = Field(
        ...,
        description="User ID to create token for",
        example="123e4567-e89b-12d3-a456-426614174000",
    )


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User ID encoded in token")


@router.post(
    "/generate-token",
    summary="Generate JWT Token",
    response_model=TokenResponse,
    description="Development endpoint to generate JWT tokens for testing",
)
async def generate_token(request: TokenRequest):
    """
    Generate a JWT token for testing purposes.

    This is a temporary endpoint for Phase 1 testing.
    In production, tokens will be generated through OAuth flow.
    """
    try:
        # Generate JWT token
        access_token = jwt_utils.create_access_token(request.user_id)

        return TokenResponse(
            access_token=access_token, token_type="bearer", user_id=str(request.user_id)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate token: {str(e)}"
        )
