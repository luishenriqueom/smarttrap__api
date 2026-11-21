"""jpeg quality

Revision ID: 0004_jpeg_quality
Revises: 0003_frame_size
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_jpeg_quality"
down_revision: str | None = "0003_frame_size"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("jpeg_quality", sa.Integer(), nullable=False, server_default="12"))
    op.create_check_constraint("ck_devices_jpeg_quality", "devices", "jpeg_quality BETWEEN 4 AND 63")
    op.add_column("captures", sa.Column("jpeg_quality", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_captures_jpeg_quality",
        "captures",
        "jpeg_quality IS NULL OR jpeg_quality BETWEEN 4 AND 63",
    )


def downgrade() -> None:
    op.drop_constraint("ck_captures_jpeg_quality", "captures", type_="check")
    op.drop_column("captures", "jpeg_quality")
    op.drop_constraint("ck_devices_jpeg_quality", "devices", type_="check")
    op.drop_column("devices", "jpeg_quality")
