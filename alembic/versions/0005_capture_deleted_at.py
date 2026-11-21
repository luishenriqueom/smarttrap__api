"""soft delete captures

Revision ID: 0005_capture_deleted_at
Revises: 0004_jpeg_quality
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_capture_deleted_at"
down_revision: str | None = "0004_jpeg_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "deleted_at")
