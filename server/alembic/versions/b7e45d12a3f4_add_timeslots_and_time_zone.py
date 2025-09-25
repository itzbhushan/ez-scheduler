"""Add timeslots tables and time_zone to signup_forms

Revision ID: b7e45d12a3f4
Revises: 8c1b0a1c1b6e, 27f36c4ee198
Create Date: 2025-09-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e45d12a3f4"
down_revision: Union[str, Sequence[str], None] = ("8c1b0a1c1b6e", "27f36c4ee198")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add time_zone, timeslots, and registration_timeslots."""
    # Add time_zone to signup_forms (IANA timezone string)
    op.add_column(
        "signup_forms",
        sa.Column("time_zone", sa.String(), nullable=True),
    )

    # Create timeslots table
    op.create_table(
        "timeslots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["form_id"], ["signup_forms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "form_id", "start_at", "end_at", name="uq_timeslots_form_start_end"
        ),
        sa.CheckConstraint("capacity >= 1", name="ck_timeslots_capacity_ge_1"),
        sa.CheckConstraint("booked_count >= 0", name="ck_timeslots_booked_ge_0"),
        sa.CheckConstraint(
            "booked_count <= capacity", name="ck_timeslots_booked_le_capacity"
        ),
        sa.CheckConstraint("start_at < end_at", name="ck_timeslots_start_before_end"),
    )

    # Indexes for timeslots
    op.create_index(
        "idx_timeslots_form_start", "timeslots", ["form_id", "start_at"], unique=False
    )
    # Partial index to speed availability queries
    try:
        op.create_index(
            "idx_timeslots_availability",
            "timeslots",
            ["form_id", "start_at"],
            unique=False,
            postgresql_where=sa.text("booked_count < capacity"),
        )
    except Exception:
        # Some engines may not support partial indexes (e.g., sqlite in dev)
        pass

    # Create registration_timeslots join table
    op.create_table(
        "registration_timeslots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("registration_id", sa.Uuid(), nullable=False),
        sa.Column("timeslot_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registration_id"], ["registrations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["timeslot_id"], ["timeslots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "registration_id", "timeslot_id", name="uq_registration_timeslot_unique"
        ),
    )

    # Indexes for registration_timeslots
    op.create_index(
        "ix_registration_timeslots_registration_id",
        "registration_timeslots",
        ["registration_id"],
        unique=False,
    )
    op.create_index(
        "ix_registration_timeslots_timeslot_id",
        "registration_timeslots",
        ["timeslot_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema: drop join table, timeslots, and time_zone column."""
    # Drop registration_timeslots indexes and table
    try:
        op.drop_index(
            "ix_registration_timeslots_timeslot_id",
            table_name="registration_timeslots",
        )
    except Exception:
        pass
    try:
        op.drop_index(
            "ix_registration_timeslots_registration_id",
            table_name="registration_timeslots",
        )
    except Exception:
        pass
    op.drop_table("registration_timeslots")

    # Drop timeslots indexes and table
    try:
        op.drop_index("idx_timeslots_form_start", table_name="timeslots")
    except Exception:
        pass
    try:
        op.drop_index("idx_timeslots_availability", table_name="timeslots")
    except Exception:
        pass
    op.drop_table("timeslots")

    # Drop time_zone column
    with op.batch_alter_table("signup_forms") as batch_op:
        try:
            batch_op.drop_column("time_zone")
        except Exception:
            pass
