"""Add field type validation constraints

Revision ID: 6c4ebf505614
Revises: 32b86e3e1ca5
Create Date: 2025-09-09 17:14:10.347509

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c4ebf505614"
down_revision: Union[str, Sequence[str], None] = "32b86e3e1ca5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add field type validation constraints."""
    # Add check constraint for valid field types
    op.create_check_constraint(
        "valid_field_type",
        "form_fields",
        "field_type IN ('text', 'number', 'select', 'checkbox')",
    )


def downgrade() -> None:
    """Remove field type validation constraints."""
    # Drop check constraint
    op.drop_constraint("valid_field_type", "form_fields", type_="check")
