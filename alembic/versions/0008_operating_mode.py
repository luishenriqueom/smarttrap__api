"""device operating mode

Revision ID: 0008_operating_mode
Revises: 0007_device_clock
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_operating_mode"
down_revision: str | None = "0007_device_clock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("operating_mode", sa.String(length=16), nullable=False, server_default="collect"))
    op.add_column("devices", sa.Column("reported_mode", sa.String(length=16), nullable=True))
    op.create_check_constraint("ck_devices_operating_mode", "devices", "operating_mode IN ('collect', 'infer')")
    op.create_check_constraint(
        "ck_devices_reported_mode",
        "devices",
        "reported_mode IS NULL OR reported_mode IN ('collect', 'infer')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_devices_reported_mode", "devices", type_="check")
    op.drop_constraint("ck_devices_operating_mode", "devices", type_="check")
    op.drop_column("devices", "reported_mode")
    op.drop_column("devices", "operating_mode")
