"""firmware releases

Revision ID: 0002_firmware
Revises: 0001_initial
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_firmware"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "firmware",
        sa.Column("target", sa.String(16), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("md5", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("target IN ('smarttrap', 'heltec')", name="ck_firmware_target"),
        sa.CheckConstraint("version >= 1 AND version <= 65535", name="ck_firmware_version"),
        sa.CheckConstraint("size_bytes > 0", name="ck_firmware_size"),
    )


def downgrade() -> None:
    op.drop_table("firmware")
