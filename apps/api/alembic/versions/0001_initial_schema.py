"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-25 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role = postgresql.ENUM("admin", "user", name="user_role", create_type=False)
proxy_type = postgresql.ENUM("socks5", "http", name="proxy_type", create_type=False)
device_state = postgresql.ENUM(
    "creating", "running", "stopping", "stopped", "error", "deleted",
    name="device_state", create_type=False,
)


def upgrade() -> None:
    # Enums (created once)
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'user')")
    op.execute("CREATE TYPE proxy_type AS ENUM ('socks5', 'http')")
    op.execute(
        "CREATE TYPE device_state AS ENUM "
        "('creating','running','stopping','stopped','error','deleted')"
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("quota_instances", sa.Integer, nullable=False, server_default="3"),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("redeemed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"], unique=True)

    op.create_table(
        "device_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("android_version", sa.String(8), nullable=False, server_default="11"),
        sa.Column("screen_width", sa.Integer, nullable=False),
        sa.Column("screen_height", sa.Integer, nullable=False),
        sa.Column("screen_dpi", sa.Integer, nullable=False),
        sa.Column("ram_mb", sa.Integer, nullable=False, server_default="4096"),
        sa.Column("cpu_cores", sa.Integer, nullable=False, server_default="4"),
        sa.Column("manufacturer", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "proxies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("type", proxy_type, nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.LargeBinary, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_proxies_user_id", "proxies", ["user_id"])

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_profiles.id"), nullable=False,
        ),
        sa.Column(
            "proxy_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("state", device_state, nullable=False, server_default="creating"),
        sa.Column("state_reason", sa.Text, nullable=True),
        sa.Column("redroid_container_id", sa.String(64), nullable=True),
        sa.Column("sidecar_container_id", sa.String(64), nullable=True),
        sa.Column("adb_host_port", sa.Integer, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("stopped_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_devices_state", "devices", ["state"])
    op.create_index("ix_devices_user_id_state", "devices", ["user_id", "state"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "started_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "last_ping_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("client_ip", postgresql.INET, nullable=True),
    )
    op.create_index("ix_sessions_device_lastping", "sessions", ["device_id", "last_ping_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_user_created", "audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_user_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_sessions_device_lastping", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_devices_user_id_state", table_name="devices")
    op.drop_index("ix_devices_state", table_name="devices")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_proxies_user_id", table_name="proxies")
    op.drop_table("proxies")
    op.drop_table("device_profiles")
    op.drop_index("ix_invites_token_hash", table_name="invites")
    op.drop_table("invites")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE device_state")
    op.execute("DROP TYPE proxy_type")
    op.execute("DROP TYPE user_role")
