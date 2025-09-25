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
    # Use explicit SQL to avoid transaction-aborting errors on missing objects
    op.execute("ALTER TABLE timeslots ALTER COLUMN capacity DROP NOT NULL")

    # Drop legacy constraints if present (safe with IF EXISTS)
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_capacity_ge_1"
    )
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_booked_le_capacity"
    )

    # Create new constraints tolerant of NULL capacity; guard against duplicates
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE timeslots
            ADD CONSTRAINT ck_timeslots_capacity_ge_1_or_null
            CHECK (capacity IS NULL OR capacity >= 1);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE timeslots
            ADD CONSTRAINT ck_timeslots_booked_le_capacity_or_null
            CHECK (capacity IS NULL OR booked_count <= capacity);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END$$;
        """
    )

    # Adjust availability index to include unlimited capacity
    op.execute("DROP INDEX IF EXISTS idx_timeslots_availability")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_timeslots_availability
        ON timeslots (form_id, start_at)
        WHERE (capacity IS NULL OR booked_count < capacity)
        """
    )


def downgrade() -> None:
    # Revert availability index
    op.execute("DROP INDEX IF EXISTS idx_timeslots_availability")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_timeslots_availability
        ON timeslots (form_id, start_at)
        WHERE (booked_count < capacity)
        """
    )

    # Revert constraints and column nullability
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_booked_le_capacity_or_null"
    )
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_capacity_ge_1_or_null"
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE timeslots
            ADD CONSTRAINT ck_timeslots_capacity_ge_1
            CHECK (capacity >= 1);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE timeslots
            ADD CONSTRAINT ck_timeslots_booked_le_capacity
            CHECK (booked_count <= capacity);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END$$;
        """
    )
    # Make capacity NOT NULL again
    op.execute("ALTER TABLE timeslots ALTER COLUMN capacity SET NOT NULL")
