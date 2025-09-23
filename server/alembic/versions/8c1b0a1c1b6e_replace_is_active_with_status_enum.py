"""Replace is_active with status enum on signup_forms

Revision ID: 8c1b0a1c1b6e
Revises: 7f62cfa084f2
Create Date: 2025-09-22
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "8c1b0a1c1b6e"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type
    status_enum = sa.Enum("draft", "published", "archived", name="signup_form_status")
    status_enum.create(op.get_bind(), checkfirst=True)

    # Add column with server default
    op.add_column(
        "signup_forms",
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="draft",
        ),
    )

    # Backfill existing rows to published
    op.execute("UPDATE signup_forms SET status = 'published' WHERE status IS NULL")

    # Drop old index on is_active if present
    try:
        op.drop_index(op.f("ix_signup_forms_is_active"), table_name="signup_forms")
    except Exception:
        pass

    # Drop is_active column if present
    with op.batch_alter_table("signup_forms") as batch_op:
        try:
            batch_op.drop_column("is_active")
        except Exception:
            pass

    # Add indexes on status and composite (url_slug, status)
    op.create_index(
        op.f("ix_signup_forms_status"), "signup_forms", ["status"], unique=False
    )
    op.create_index(
        "idx_signup_forms_url_slug_status",
        "signup_forms",
        ["url_slug", "status"],
        unique=False,
    )


def downgrade() -> None:
    # Recreate is_active column
    with op.batch_alter_table("signup_forms") as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=True))

    # Backfill: published/draft -> True, archived -> False
    op.execute(
        "UPDATE signup_forms SET is_active = CASE WHEN status = 'archived' THEN FALSE ELSE TRUE END"
    )

    # Drop indexes
    try:
        op.drop_index("idx_signup_forms_url_slug_status", table_name="signup_forms")
    except Exception:
        pass
    try:
        op.drop_index(op.f("ix_signup_forms_status"), table_name="signup_forms")
    except Exception:
        pass

    # Drop status column
    with op.batch_alter_table("signup_forms") as batch_op:
        batch_op.drop_column("status")

    # Drop enum type
    status_enum = sa.Enum("draft", "published", "archived", name="signup_form_status")
    status_enum.drop(op.get_bind(), checkfirst=True)

    # Recreate old index
    op.create_index(
        op.f("ix_signup_forms_is_active"), "signup_forms", ["is_active"], unique=False
    )
