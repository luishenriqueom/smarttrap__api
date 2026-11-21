"""species, annotations, models and sleep interval

Revision ID: 0006_fomo
Revises: 0005_capture_deleted_at
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_fomo"
down_revision: str | None = "0005_capture_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "species",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="idle", nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("class_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("input_size", sa.Integer(), server_default="96", nullable=False),
        sa.Column("window", sa.Integer(), server_default="96", nullable=False),
        sa.Column("stride", sa.Integer(), server_default="64", nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("devices", sa.Column("sleep_seconds", sa.Integer(), server_default="300", nullable=False))
    op.create_check_constraint("ck_devices_sleep_seconds", "devices", "sleep_seconds BETWEEN 60 AND 86400")
    op.add_column("devices", sa.Column("model_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_devices_model_id", "devices", "models", ["model_id"], ["id"])
    op.create_table(
        "capture_annotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("species_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.ForeignKeyConstraint(["species_id"], ["species.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capture_annotations_capture_id", "capture_annotations", ["capture_id"])
    op.create_index("ix_capture_annotations_species_id", "capture_annotations", ["species_id"])
    op.create_check_constraint(
        "ck_capture_annotations_box",
        "capture_annotations",
        "x >= 0 AND y >= 0 AND width >= 1 AND height >= 1 AND source IN ('human', 'device')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_capture_annotations_box", "capture_annotations", type_="check")
    op.drop_index("ix_capture_annotations_species_id", table_name="capture_annotations")
    op.drop_index("ix_capture_annotations_capture_id", table_name="capture_annotations")
    op.drop_table("capture_annotations")
    op.drop_constraint("fk_devices_model_id", "devices", type_="foreignkey")
    op.drop_column("devices", "model_id")
    op.drop_constraint("ck_devices_sleep_seconds", "devices", type_="check")
    op.drop_column("devices", "sleep_seconds")
    op.drop_table("models")
    op.drop_table("species")
