"""Authentication models for FastAPI"""

from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    claims: dict
