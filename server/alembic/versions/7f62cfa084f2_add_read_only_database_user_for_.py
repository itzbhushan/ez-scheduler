"""Add read-only database user for analytics

Revision ID: 7f62cfa084f2
Revises: 27f36c4ee198
Create Date: 2025-08-27 18:11:05.057749

"""

import os
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f62cfa084f2"
down_revision: Union[str, Sequence[str], None] = "27f36c4ee198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create read-only user for analytics queries
    analytics_password = os.getenv("ANALYTICS_DB_PASSWORD")
    op.execute(
        f"CREATE USER ez_analytics_readonly WITH PASSWORD '{analytics_password}';"
    )

    # Grant SELECT permissions on existing core tables
    op.execute("GRANT SELECT ON signup_forms TO ez_analytics_readonly;")
    op.execute("GRANT SELECT ON registrations TO ez_analytics_readonly;")

    # Grant SELECT on future tables in public schema
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ez_analytics_readonly;"
    )

    # Grant USAGE on schema
    op.execute("GRANT USAGE ON SCHEMA public TO ez_analytics_readonly;")


def downgrade() -> None:
    """Downgrade schema."""
    # Revoke permissions
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM ez_analytics_readonly;"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM ez_analytics_readonly;")

    # Drop user
    op.execute("DROP USER IF EXISTS ez_analytics_readonly;")
