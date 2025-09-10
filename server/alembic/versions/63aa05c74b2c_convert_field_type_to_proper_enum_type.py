"""Convert field_type to proper enum type

Revision ID: 63aa05c74b2c
Revises: 6c4ebf505614
Create Date: 2025-09-09 17:48:03.917952

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "63aa05c74b2c"
down_revision: Union[str, Sequence[str], None] = "6c4ebf505614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert field_type from varchar to proper enum type."""
    # Create the enum type
    fieldtype_enum = sa.Enum(
        "text", "number", "select", "checkbox", name="fieldtype", create_type=False
    )
    fieldtype_enum.create(op.get_bind(), checkfirst=True)

    # Convert the column to use the enum
    op.alter_column(
        "form_fields",
        "field_type",
        type_=fieldtype_enum,
        postgresql_using="field_type::fieldtype",
    )


def downgrade() -> None:
    """Convert field_type back to varchar."""
    # Convert back to varchar
    op.alter_column(
        "form_fields",
        "field_type",
        type_=sa.VARCHAR(),
        postgresql_using="field_type::varchar",
    )

    # Drop the enum type
    sa.Enum(name="fieldtype").drop(op.get_bind(), checkfirst=True)
