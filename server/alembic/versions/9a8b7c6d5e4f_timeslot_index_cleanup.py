"""Cleanup redundant timeslot availability index

Revision ID: 9a8b7c6d5e4f
Revises: b7e45d12a3f4
Create Date: 2025-09-26

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
# Chain after the latest timeslot migration to avoid multiple heads
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop redundant availability index if present.

    We keep a single canonical composite index on (form_id, start_at):
    - idx_timeslots_form_start

    This migration removes idx_timeslots_availability when it duplicates the
    same column set (with or without a partial predicate), to avoid planner
    confusion and reduce maintenance overhead.
    """
    try:
        op.execute("DROP INDEX IF EXISTS idx_timeslots_availability")
    except Exception:
        # Some engines (e.g., sqlite) may not support this form or the index
        # may never have been created in that environment. Best-effort only.
        pass


def downgrade() -> None:
    """Recreate the availability index as a non-partial index if needed.

    We recreate it as a plain composite index on (form_id, start_at) to
    maintain compatibility across environments that do not support partial
    indexes. Note this will coexist with idx_timeslots_form_start if both
    exist after downgrade.
    """
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeslots_availability ON timeslots (form_id, start_at)"
        )
    except Exception:
        pass
