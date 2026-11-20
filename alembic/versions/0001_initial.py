"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('common', 'superadmin')", name="ck_users_role"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index(
        "uq_users_single_demo",
        "users",
        ["is_demo"],
        unique=True,
        postgresql_where=sa.text("is_demo"),
    )
    op.create_table(
        "gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("code", name="uq_devices_code"),
    )
    op.create_index("ix_devices_code", "devices", ["code"], unique=True)
    op.create_index("ix_devices_owner_id", "devices", ["owner_id"])
    op.create_table(
        "captures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("manual_count", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(20), nullable=False, server_default="unlabeled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "label IN ('unlabeled', 'with_pest', 'without_pest')",
            name="ck_captures_label",
        ),
    )
    op.create_index("ix_captures_device_id", "captures", ["device_id"])
    op.create_index("ix_captures_device_captured", "captures", ["device_id", "captured_at"])
    op.create_table(
        "metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("pest_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("battery_v", sa.Float(), nullable=True),
        sa.Column("rssi", sa.Float(), nullable=True),
        sa.Column("snr", sa.Float(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("pest_count >= 0", name="ck_metrics_pest_count"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_metrics_confidence",
        ),
    )
    op.create_index("ix_metrics_device_id", "metrics", ["device_id"])
    op.create_index("ix_metrics_device_recorded", "metrics", ["device_id", "recorded_at"])


def downgrade() -> None:
    op.drop_table("metrics")
    op.drop_table("captures")
    op.drop_table("devices")
    op.drop_table("gateways")
    op.drop_table("users")
