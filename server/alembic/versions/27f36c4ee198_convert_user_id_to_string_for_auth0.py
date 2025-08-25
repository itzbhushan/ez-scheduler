"""convert_user_id_to_string_for_auth0

Revision ID: 27f36c4ee198
Revises: c9c3549085e9
Create Date: 2025-08-24 21:25:19.603309

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27f36c4ee198"
down_revision: Union[str, Sequence[str], None] = "c9c3549085e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to use Auth0 string user_ids."""

    # Step 1: Drop foreign key constraints that reference users table
    op.drop_constraint("signup_forms_user_id_fkey", "signup_forms", type_="foreignkey")
    op.drop_constraint(
        "registrations_user_id_fkey", "registrations", type_="foreignkey"
    )

    # Step 2: Add temporary columns for new string user_id
    op.add_column("signup_forms", sa.Column("user_id_new", sa.String(), nullable=True))
    op.add_column("registrations", sa.Column("user_id_new", sa.String(), nullable=True))

    # Step 3: Convert existing UUID user_ids to strings (if any exist)
    # Note: This assumes we want to convert existing UUIDs to string format
    # If no data exists yet, this is safe
    op.execute(
        "UPDATE signup_forms SET user_id_new = user_id::text WHERE user_id IS NOT NULL"
    )
    op.execute(
        "UPDATE registrations SET user_id_new = user_id::text WHERE user_id IS NOT NULL"
    )

    # Step 4: Drop old UUID columns
    op.drop_column("signup_forms", "user_id")
    op.drop_column("registrations", "user_id")

    # Step 5: Rename new columns to user_id
    op.alter_column("signup_forms", "user_id_new", new_column_name="user_id")
    op.alter_column("registrations", "user_id_new", new_column_name="user_id")

    # Step 6: Make signup_forms.user_id NOT NULL (it's required)
    op.alter_column("signup_forms", "user_id", nullable=False)

    # Step 7: Add indexes for performance
    op.create_index("ix_signup_forms_user_id", "signup_forms", ["user_id"])
    op.create_index("ix_registrations_user_id", "registrations", ["user_id"])

    # Step 8: Drop the users table since we no longer need it
    op.drop_table("users")


def downgrade() -> None:
    """Downgrade schema back to UUID user_ids (WARNING: This will lose Auth0 user data)."""

    # Step 1: Recreate users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Step 2: Drop string user_id indexes
    op.drop_index("ix_signup_forms_user_id", "signup_forms")
    op.drop_index("ix_registrations_user_id", "registrations")

    # Step 3: Add temporary UUID columns
    op.add_column("signup_forms", sa.Column("user_id_uuid", sa.UUID(), nullable=True))
    op.add_column("registrations", sa.Column("user_id_uuid", sa.UUID(), nullable=True))

    # Step 4: WARNING: Convert string user_ids back to UUIDs
    # This will fail if Auth0 user_ids are not valid UUIDs
    # You may need to handle this conversion manually or create placeholder users

    # Step 5: Drop string user_id columns
    op.drop_column("signup_forms", "user_id")
    op.drop_column("registrations", "user_id")

    # Step 6: Rename UUID columns back
    op.alter_column("signup_forms", "user_id_uuid", new_column_name="user_id")
    op.alter_column("registrations", "user_id_uuid", new_column_name="user_id")

    # Step 7: Make signup_forms.user_id NOT NULL and add foreign keys
    op.alter_column("signup_forms", "user_id", nullable=False)
    op.create_foreign_key(
        "signup_forms_user_id_fkey", "signup_forms", "users", ["user_id"], ["id"]
    )
    op.create_foreign_key(
        "registrations_user_id_fkey", "registrations", "users", ["user_id"], ["id"]
    )
