"""SQLModel SignupForm model"""

import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class SignupForm(SQLModel, table=True):
    """Signup form model"""

    __tablename__ = "signup_forms"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    title: str
    event_date: date = Field(index=True)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    location: str
    description: str
    url_slug: str = Field(unique=True, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
