"""Timeslot-related SQLModel models"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class Timeslot(SQLModel, table=True):
    """Bookable timeslot attached to a signup form.

    All times are stored in UTC.
    """

    __tablename__ = "timeslots"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    form_id: uuid.UUID = Field(foreign_key="signup_forms.id", index=True)

    # Store timezone-aware timestamps in UTC
    start_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    end_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    capacity: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    booked_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "form_id", "start_at", "end_at", name="uq_timeslots_form_start_end"
        ),
        CheckConstraint("capacity >= 1", name="ck_timeslots_capacity_ge_1"),
        CheckConstraint("booked_count >= 0", name="ck_timeslots_booked_ge_0"),
        CheckConstraint(
            "booked_count <= capacity", name="ck_timeslots_booked_le_capacity"
        ),
        CheckConstraint("start_at < end_at", name="ck_timeslots_start_before_end"),
        Index("idx_timeslots_form_start", "form_id", "start_at"),
    )


class RegistrationTimeslot(SQLModel, table=True):
    """Join table connecting registrations to the timeslots they selected."""

    __tablename__ = "registration_timeslots"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    registration_id: uuid.UUID = Field(foreign_key="registrations.id", index=True)
    timeslot_id: uuid.UUID = Field(foreign_key="timeslots.id", index=True)

    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "timeslot_id",
            name="uq_registration_timeslot_unique",
        ),
    )
