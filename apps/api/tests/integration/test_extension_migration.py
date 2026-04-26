"""Integration test: migration 0002 + ORM round-trip on real Postgres.

Run prerequisites:
    docker compose up -d postgres
    cd apps/api && alembic downgrade base   # reset schema
    INTEGRATION=1 pytest tests/integration/test_extension_migration.py -v
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC

import pytest
from sqlalchemy import select, text

from cloude_api.db import async_session_factory
from cloude_api.enums import (
    DeviceFileOp,
    DeviceFileState,
    DeviceState,
    ImageVariant,
    ProxyType,
    SnapshotKind,
    SnapshotState,
    UserRole,
)
from cloude_api.models import (
    Device,
    DeviceFile,
    DeviceProfile,
    Invite,
    Proxy,
    Snapshot,
    User,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _alembic(args: list[str]) -> None:
    """Run alembic CLI in apps/api with current env."""
    subprocess.run(
        ["alembic", *args],  # noqa: S603, S607
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        check=True,
    )


@pytest.fixture(scope="module", autouse=True)
def migrated_schema():
    """Force schema to head before tests, then back to base after.

    Sync fixture — alembic invocations are subprocess.run, no async needed.
    """
    if not os.getenv("INTEGRATION"):
        pytest.skip("set INTEGRATION=1 to run integration tests")
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])
    yield
    _alembic(["downgrade", "base"])


async def test_migration_creates_new_enum_types() -> None:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT typname FROM pg_type WHERE typname IN "
                    "('image_variant','snapshot_kind','snapshot_state',"
                    "'device_file_op','device_file_state')"
                )
            )
        ).all()
        names = {r[0] for r in rows}
        assert names == {
            "image_variant",
            "snapshot_kind",
            "snapshot_state",
            "device_file_op",
            "device_file_state",
        }


async def test_migration_adds_columns_to_devices() -> None:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='devices'"
                )
            )
        ).all()
        cols = {r[0] for r in rows}
        for new in (
            "image_variant",
            "current_session_id",
            "last_known_ip",
            "last_known_country",
            "tags",
            "auto_snapshot_enabled",
        ):
            assert new in cols, f"missing column on devices: {new}"


async def test_orm_round_trip_snapshot_and_device_file() -> None:
    """Insert through the ORM, read back, verify enum values cast correctly."""
    async with async_session_factory() as db:
        # minimum required parents
        user = User(
            id=uuid.uuid4(),
            email=f"t-{uuid.uuid4().hex[:8]}@x.test",
            password_hash="x",
            role=UserRole.user,
        )
        profile = DeviceProfile(
            id=uuid.uuid4(),
            name="Pixel 5",
            screen_width=1080,
            screen_height=2340,
            screen_dpi=440,
            manufacturer="Google",
            model="Pixel 5",
        )
        proxy = Proxy(
            id=uuid.uuid4(),
            user_id=user.id,
            label="t",
            type=ProxyType.socks5,
            host="proxy.example",
            port=1080,
        )
        device = Device(
            id=uuid.uuid4(),
            user_id=user.id,
            name="t-device",
            profile_id=profile.id,
            proxy_id=proxy.id,
            state=DeviceState.creating,
            image_variant=ImageVariant.daily,
            current_session_id="abc123",
            last_known_country="BD",
            tags=["daily", "test"],
            auto_snapshot_enabled=True,
        )
        snapshot = Snapshot(
            id=uuid.uuid4(),
            device_id=device.id,
            user_id=user.id,
            name="manual-1",
            kind=SnapshotKind.manual,
            local_path=f"/var/lib/cloude-phone/snapshots/{device.id}/x.tar.zst",
            state=SnapshotState.ready,
            size_bytes=1234,
        )
        device_file = DeviceFile(
            id=uuid.uuid4(),
            device_id=device.id,
            user_id=user.id,
            op=DeviceFileOp.apk_install,
            filename="app.apk",
            size_bytes=4096,
            state=DeviceFileState.done,
        )

        db.add_all([user, profile, proxy, device, snapshot, device_file])
        await db.commit()

        # Read back, verify enum values + array column
        loaded_device = (
            await db.execute(select(Device).where(Device.id == device.id))
        ).scalar_one()
        assert loaded_device.image_variant == ImageVariant.daily
        assert loaded_device.tags == ["daily", "test"]
        assert loaded_device.auto_snapshot_enabled is True

        loaded_snap = (
            await db.execute(select(Snapshot).where(Snapshot.id == snapshot.id))
        ).scalar_one()
        assert loaded_snap.kind == SnapshotKind.manual
        assert loaded_snap.state == SnapshotState.ready
        assert loaded_snap.size_bytes == 1234

        loaded_df = (
            await db.execute(select(DeviceFile).where(DeviceFile.id == device_file.id))
        ).scalar_one()
        assert loaded_df.op == DeviceFileOp.apk_install
        assert loaded_df.state == DeviceFileState.done


async def test_invite_quota_instances_default() -> None:
    """Insert an invite without specifying quota_instances → server default 3."""
    async with async_session_factory() as db:
        from datetime import datetime, timedelta

        admin = User(
            id=uuid.uuid4(),
            email=f"admin-{uuid.uuid4().hex[:8]}@x.test",
            password_hash="x",
            role=UserRole.admin,
        )
        invite = Invite(
            id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            created_by=admin.id,
        )
        db.add_all([admin, invite])
        await db.commit()

        loaded = (await db.execute(select(Invite).where(Invite.id == invite.id))).scalar_one()
        assert loaded.quota_instances == 3


async def test_proxy_session_template_default() -> None:
    """Insert a proxy without session_username_template → Bright Data default."""
    async with async_session_factory() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@x.test",
            password_hash="x",
            role=UserRole.user,
        )
        proxy = Proxy(
            id=uuid.uuid4(),
            user_id=user.id,
            label="brightdata-test",
            type=ProxyType.socks5,
            host="brd.superproxy.io",
            port=22225,
        )
        db.add_all([user, proxy])
        await db.commit()

        loaded = (await db.execute(select(Proxy).where(Proxy.id == proxy.id))).scalar_one()
        assert loaded.session_username_template == "{user}-session-{session}"
        assert loaded.supports_rotation is True
