"""Authentication models for FastAPI"""

from pydantic import BaseModel


class UserClaims(BaseModel):
    user_id: str
    claims: dict
