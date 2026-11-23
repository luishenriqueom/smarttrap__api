"""device clock report and sync request

Revision ID: 0007_device_clock
Revises: 0006_fomo
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_device_clock"
down_revision: str | None = "0006_fomo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("last_clock_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("last_clock_received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "devices",
        sa.Column("clock_sync_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("devices", "clock_sync_requested")
    op.drop_column("devices", "last_clock_received_at")
    op.drop_column("devices", "last_clock_at")
