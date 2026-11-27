"""trap coordinates and training image window

Revision ID: 0009_place_and_window
Revises: 0008_operating_mode
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_place_and_window"
down_revision: str | None = "0008_operating_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("models", sa.Column("images_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("models", sa.Column("images_to", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("models", "images_to")
    op.drop_column("models", "images_from")
    op.drop_column("devices", "longitude")
    op.drop_column("devices", "latitude")
