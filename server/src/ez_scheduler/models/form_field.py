"""SQLModel FormField model for custom form fields"""

import uuid
from typing import List, Optional

from sqlalchemy import JSON, Column
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from ez_scheduler.models.field_type import FieldType


class FormField(SQLModel, table=True):
    """Model for custom form fields"""

    __tablename__ = "form_fields"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    form_id: uuid.UUID = Field(
        foreign_key="signup_forms.id", ondelete="CASCADE", index=True
    )
    field_name: str = Field(index=True)  # Internal field name (e.g., 'guest_count')
    field_type: FieldType = Field(
        sa_column=Column(
            SQLEnum(FieldType, values_callable=lambda x: [e.value for e in x])
        )
    )
    label: str  # Display label (e.g., 'Number of guests')
    placeholder: Optional[str] = None  # Input placeholder text
    is_required: bool = Field(default=False)
    options: Optional[List[str]] = Field(
        default=None, sa_column=Column(JSON)
    )  # For select fields
    field_order: int = Field(default=0)  # Display order
