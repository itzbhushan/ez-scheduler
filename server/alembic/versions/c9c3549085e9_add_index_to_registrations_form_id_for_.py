"""Add index to registrations.form_id for improved query performance

Revision ID: c9c3549085e9
Revises: db918af13044
Create Date: 2025-07-28 17:14:02.582847

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9c3549085e9"
down_revision: Union[str, Sequence[str], None] = "db918af13044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add index to registrations.form_id for faster queries
    op.create_index(
        "ix_registrations_form_id", "registrations", ["form_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove index from registrations.form_id
    op.drop_index("ix_registrations_form_id", table_name="registrations")
