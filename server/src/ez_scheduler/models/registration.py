"""SQLModel Registration model"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Registration(SQLModel, table=True):
    """Registration model for form submissions"""

    __tablename__ = "registrations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    form_id: uuid.UUID = Field(foreign_key="signup_forms.id")
    user_id: Optional[str] = Field(default=None, index=True)  # Auth0 user ID as string
    name: str
    email: Optional[str] = Field(default="")
    phone: Optional[str] = Field(default="")
    additional_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    registered_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
