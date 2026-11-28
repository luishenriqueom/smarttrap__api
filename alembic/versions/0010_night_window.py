"""night pause window

Revision ID: 0010_night_window
Revises: 0009_place_and_window
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_night_window"
down_revision: str | None = "0009_place_and_window"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("night_start_minute", sa.Integer(), nullable=False, server_default="1050"))
    op.add_column("devices", sa.Column("night_end_minute", sa.Integer(), nullable=False, server_default="390"))
    op.create_check_constraint("ck_devices_night_start", "devices", "night_start_minute BETWEEN 0 AND 1439")
    op.create_check_constraint("ck_devices_night_end", "devices", "night_end_minute BETWEEN 0 AND 1439")


def downgrade() -> None:
    op.drop_constraint("ck_devices_night_end", "devices", type_="check")
    op.drop_constraint("ck_devices_night_start", "devices", type_="check")
    op.drop_column("devices", "night_end_minute")
    op.drop_column("devices", "night_start_minute")
