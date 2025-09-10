"""Make email and phone optional in registrations

Revision ID: 94182d3ada51
Revises: 63aa05c74b2c
Create Date: 2025-09-09 18:43:30.755790

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94182d3ada51"
down_revision: Union[str, Sequence[str], None] = "63aa05c74b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make email and phone fields nullable."""
    # Allow email and phone to be nullable
    op.alter_column("registrations", "email", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column("registrations", "phone", existing_type=sa.VARCHAR(), nullable=True)


def downgrade() -> None:
    """Make email and phone fields required again."""
    # Make email and phone non-nullable again
    op.alter_column(
        "registrations", "email", existing_type=sa.VARCHAR(), nullable=False
    )
    op.alter_column(
        "registrations", "phone", existing_type=sa.VARCHAR(), nullable=False
    )
