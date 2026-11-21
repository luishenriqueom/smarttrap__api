"""camera frame size

Revision ID: 0003_frame_size
Revises: 0002_firmware
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_frame_size"
down_revision: str | None = "0002_firmware"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOKENS = "'qqvga', 'qvga', 'vga', 'svga', 'xga', 'sxga', 'uxga'"


def upgrade() -> None:
    op.add_column("devices", sa.Column("frame_size", sa.String(8), nullable=False, server_default="svga"))
    op.create_check_constraint("ck_devices_frame_size", "devices", f"frame_size IN ({_TOKENS})")
    op.add_column("captures", sa.Column("frame_size", sa.String(8), nullable=True))
    op.add_column("captures", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("captures", sa.Column("height", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_captures_frame_size",
        "captures",
        f"frame_size IS NULL OR frame_size IN ({_TOKENS})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_captures_frame_size", "captures", type_="check")
    op.drop_column("captures", "height")
    op.drop_column("captures", "width")
    op.drop_column("captures", "frame_size")
    op.drop_constraint("ck_devices_frame_size", "devices", type_="check")
    op.drop_column("devices", "frame_size")
