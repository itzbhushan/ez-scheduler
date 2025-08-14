"""Init DB

Revision ID: 041ca3de6870
Revises:
Create Date: 2025-07-14 21:19:21.872992

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "041ca3de6870"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create initial signup_forms table (before user model was added)
    op.create_table(
        "signup_forms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.VARCHAR(), nullable=False),
        sa.Column("event_date", sa.VARCHAR(), nullable=False),
        sa.Column("location", sa.VARCHAR(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=True),
        sa.Column("url_slug", sa.VARCHAR(), nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_slug"),
    )

    # Create other tables that existed before
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.VARCHAR(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("message_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "form_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=True),
        sa.Column("field_name", sa.VARCHAR(), nullable=False),
        sa.Column("field_type", sa.VARCHAR(), nullable=False),
        sa.Column("label", sa.VARCHAR(), nullable=False),
        sa.Column("required", sa.BOOLEAN(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("order", sa.INTEGER(), nullable=True),
        sa.ForeignKeyConstraint(
            ["form_id"],
            ["signup_forms.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("email", sa.VARCHAR(), nullable=False),
        sa.Column("phone", sa.VARCHAR(), nullable=False),
        sa.Column("additional_data", sa.JSON(), nullable=True),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["form_id"],
            ["signup_forms.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add foreign key constraint for signup_forms -> conversations
    op.create_foreign_key(
        None, "signup_forms", "conversations", ["conversation_id"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("registrations")
    op.drop_table("form_fields")
    op.drop_table("messages")
    op.drop_table("signup_forms")
    op.drop_table("conversations")
