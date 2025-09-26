"""Hardening: ensure nullable capacity + availability index are consistent

Revision ID: f6a7b8c9d0e1
Revises: e1a2b3c4d5e6
Create Date: 2025-09-25

This migration is intentionally idempotent and resilient. It:
- Makes capacity nullable (unlimited when NULL)
- Ensures NULL-tolerant check constraints exist
- Ensures availability partial index includes unlimited capacity

Safe to run multiple times; no-ops if objects already match.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make capacity nullable (if not already)
    op.execute("ALTER TABLE timeslots ALTER COLUMN capacity DROP NOT NULL")

    # Drop legacy strict constraints if present
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_capacity_ge_1"
    )
    op.execute(
        "ALTER TABLE timeslots DROP CONSTRAINT IF EXISTS ck_timeslots_booked_le_capacity"
    )

    # Add NULL-tolerant constraints; ignore if already exist
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

    # Ensure availability index includes unlimited capacity
    op.execute("DROP INDEX IF EXISTS idx_timeslots_availability")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_timeslots_availability
        ON timeslots (form_id, start_at)
        WHERE (capacity IS NULL OR booked_count < capacity)
        """
    )


def downgrade() -> None:
    # Revert index
    op.execute("DROP INDEX IF EXISTS idx_timeslots_availability")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_timeslots_availability
        ON timeslots (form_id, start_at)
        WHERE (booked_count < capacity)
        """
    )

    # Drop NULL-tolerant constraints; recreate strict ones
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
