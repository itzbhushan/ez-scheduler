"""Allow unlimited capacity in timeslots (nullable capacity) and adjust availability index

Revision ID: e1a2b3c4d5e6
Revises: b7e45d12a3f4
Create Date: 2025-09-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "b7e45d12a3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make capacity nullable to indicate unlimited when NULL
    with op.batch_alter_table("timeslots") as batch_op:
        try:
            batch_op.alter_column("capacity", existing_type=sa.Integer(), nullable=True)
        except Exception:
            pass

        # Drop old constraints if present
        for cname in (
            "ck_timeslots_capacity_ge_1",
            "ck_timeslots_booked_le_capacity",
        ):
            try:
                batch_op.drop_constraint(cname, type_="check")
            except Exception:
                pass

        # Create new constraints tolerant of NULL capacity
        try:
            batch_op.create_check_constraint(
                "ck_timeslots_capacity_ge_1_or_null",
                "capacity IS NULL OR capacity >= 1",
            )
        except Exception:
            pass
        try:
            batch_op.create_check_constraint(
                "ck_timeslots_booked_le_capacity_or_null",
                "capacity IS NULL OR booked_count <= capacity",
            )
        except Exception:
            pass

    # Adjust availability index to include unlimited capacity
    try:
        op.drop_index("idx_timeslots_availability", table_name="timeslots")
    except Exception:
        pass
    try:
        op.create_index(
            "idx_timeslots_availability",
            "timeslots",
            ["form_id", "start_at"],
            unique=False,
            postgresql_where=sa.text("capacity IS NULL OR booked_count < capacity"),
        )
    except Exception:
        pass


def downgrade() -> None:
    # Revert availability index
    try:
        op.drop_index("idx_timeslots_availability", table_name="timeslots")
    except Exception:
        pass
    try:
        op.create_index(
            "idx_timeslots_availability",
            "timeslots",
            ["form_id", "start_at"],
            unique=False,
            postgresql_where=sa.text("booked_count < capacity"),
        )
    except Exception:
        pass

    # Revert constraints and column nullability
    with op.batch_alter_table("timeslots") as batch_op:
        for cname in (
            "ck_timeslots_booked_le_capacity_or_null",
            "ck_timeslots_capacity_ge_1_or_null",
        ):
            try:
                batch_op.drop_constraint(cname, type_="check")
            except Exception:
                pass
        try:
            batch_op.create_check_constraint(
                "ck_timeslots_capacity_ge_1", "capacity >= 1"
            )
        except Exception:
            pass
        try:
            batch_op.create_check_constraint(
                "ck_timeslots_booked_le_capacity", "booked_count <= capacity"
            )
        except Exception:
            pass
        try:
            batch_op.alter_column(
                "capacity", existing_type=sa.Integer(), nullable=False
            )
        except Exception:
            pass
