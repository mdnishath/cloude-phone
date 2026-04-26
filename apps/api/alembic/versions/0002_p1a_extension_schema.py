"""P1a extension schema: snapshots, device_files, plus columns on devices/proxies/invites.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reference handles for the new enum types. `create_type=False` because the
# CREATE TYPE statements are emitted explicitly via op.execute() below; this
# matches the pattern used by 0001_initial_schema.py.
image_variant = postgresql.ENUM(
    "vanilla", "daily", name="image_variant", create_type=False,
)
snapshot_kind = postgresql.ENUM(
    "manual", "auto", "pre-restore", name="snapshot_kind", create_type=False,
)
snapshot_state = postgresql.ENUM(
    "creating", "ready", "error", "deleted", name="snapshot_state", create_type=False,
)
device_file_op = postgresql.ENUM(
    "apk_install", "file_push", "file_pull", name="device_file_op", create_type=False,
)
device_file_state = postgresql.ENUM(
    "pending", "running", "done", "error", name="device_file_state", create_type=False,
)


def upgrade() -> None:
    # 1. Create the new enum types
    op.execute("CREATE TYPE image_variant AS ENUM ('vanilla', 'daily')")
    op.execute("CREATE TYPE snapshot_kind AS ENUM ('manual', 'auto', 'pre-restore')")
    op.execute("CREATE TYPE snapshot_state AS ENUM ('creating', 'ready', 'error', 'deleted')")
    op.execute("CREATE TYPE device_file_op AS ENUM ('apk_install', 'file_push', 'file_pull')")
    op.execute("CREATE TYPE device_file_state AS ENUM ('pending', 'running', 'done', 'error')")

    # 2. ALTER existing tables — devices
    op.add_column(
        "devices",
        sa.Column(
            "image_variant", image_variant,
            nullable=False, server_default="vanilla",
        ),
    )
    op.add_column(
        "devices",
        sa.Column("current_session_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_known_ip", postgresql.INET, nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_known_country", sa.String(2), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column(
            "tags", postgresql.ARRAY(sa.String),
            nullable=False, server_default="{}",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "auto_snapshot_enabled", sa.Boolean,
            nullable=False, server_default=sa.text("false"),
        ),
    )

    # 3. ALTER existing tables — proxies
    op.add_column(
        "proxies",
        sa.Column(
            "session_username_template", sa.String(255),
            nullable=False, server_default="{user}-session-{session}",
        ),
    )
    op.add_column(
        "proxies",
        sa.Column(
            "supports_rotation", sa.Boolean,
            nullable=False, server_default=sa.text("true"),
        ),
    )

    # 4. ALTER existing tables — invites
    op.add_column(
        "invites",
        sa.Column(
            "quota_instances", sa.Integer,
            nullable=False, server_default="3",
        ),
    )

    # 5. Create snapshots table
    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", snapshot_kind, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("local_path", sa.String(1024), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=True),
        sa.Column("state", snapshot_state, nullable=False, server_default="creating"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_snapshots_device_created", "snapshots", ["device_id", "created_at"],
    )

    # 6. Create device_files table
    op.create_table(
        "device_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("op", device_file_op, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("phone_path", sa.String(1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("state", device_file_state, nullable=False, server_default="pending"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True,
        ),
    )
    op.create_index(
        "ix_device_files_device_created", "device_files", ["device_id", "created_at"],
    )


def downgrade() -> None:
    # Reverse order of upgrade()
    op.drop_index("ix_device_files_device_created", table_name="device_files")
    op.drop_table("device_files")

    op.drop_index("ix_snapshots_device_created", table_name="snapshots")
    op.drop_table("snapshots")

    op.drop_column("invites", "quota_instances")

    op.drop_column("proxies", "supports_rotation")
    op.drop_column("proxies", "session_username_template")

    op.drop_column("devices", "auto_snapshot_enabled")
    op.drop_column("devices", "tags")
    op.drop_column("devices", "last_known_country")
    op.drop_column("devices", "last_known_ip")
    op.drop_column("devices", "current_session_id")
    op.drop_column("devices", "image_variant")

    op.execute("DROP TYPE device_file_state")
    op.execute("DROP TYPE device_file_op")
    op.execute("DROP TYPE snapshot_state")
    op.execute("DROP TYPE snapshot_kind")
    op.execute("DROP TYPE image_variant")
