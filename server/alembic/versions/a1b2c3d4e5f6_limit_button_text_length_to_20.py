"""Limit button text length to 20 characters

Revision ID: a1b2c3d4e5f6
Revises: 1a0c426a5532
Create Date: 2025-09-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "1a0c426a5532"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Constrain button text columns to VARCHAR(20)."""
    op.alter_column(
        "signup_forms",
        "primary_button_text",
        existing_type=sa.String(),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "signup_forms",
        "secondary_button_text",
        existing_type=sa.String(),
        type_=sa.String(length=20),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Revert button text columns back to unconstrained VARCHAR."""
    op.alter_column(
        "signup_forms",
        "secondary_button_text",
        existing_type=sa.String(length=20),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "signup_forms",
        "primary_button_text",
        existing_type=sa.String(length=20),
        type_=sa.String(),
        existing_nullable=False,
    )
