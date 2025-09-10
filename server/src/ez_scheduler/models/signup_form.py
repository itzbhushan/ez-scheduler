"""SQLModel SignupForm model"""

import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class SignupForm(SQLModel, table=True):
    """Signup form model"""

    __tablename__ = "signup_forms"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(index=True)  # Auth0 user ID as string
    title: str
    event_date: date = Field(index=True)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    location: str
    description: str
    url_slug: str = Field(unique=True, index=True)
    is_active: bool = Field(default=True, index=True)
    button_type: str = Field(
        default="single_submit"
    )  # "rsvp_yes_no" or "single_submit"
    primary_button_text: str = Field(default="Register", max_length=20)
    secondary_button_text: Optional[str] = Field(default=None, max_length=20)
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
