"""Unit tests for P1a extension models + enums (no DB required)."""

from __future__ import annotations

from datetime import UTC


def test_image_variant_enum_values() -> None:
    from cloude_api.enums import ImageVariant

    assert {v.value for v in ImageVariant} == {"vanilla", "daily"}
    assert ImageVariant.vanilla.value == "vanilla"


def test_snapshot_kind_enum_values() -> None:
    from cloude_api.enums import SnapshotKind

    assert {v.value for v in SnapshotKind} == {"manual", "auto", "pre-restore"}


def test_snapshot_state_enum_values() -> None:
    from cloude_api.enums import SnapshotState

    assert {v.value for v in SnapshotState} == {"creating", "ready", "error", "deleted"}


def test_device_file_op_enum_values() -> None:
    from cloude_api.enums import DeviceFileOp

    assert {v.value for v in DeviceFileOp} == {"apk_install", "file_push", "file_pull"}


def test_device_file_state_enum_values() -> None:
    from cloude_api.enums import DeviceFileState

    assert {v.value for v in DeviceFileState} == {"pending", "running", "done", "error"}


def test_device_model_has_new_columns() -> None:
    """Device gains image_variant, current_session_id, last_known_ip,
    last_known_country, tags, auto_snapshot_enabled."""
    from cloude_api.enums import ImageVariant
    from cloude_api.models.device import Device

    cols = Device.__table__.columns
    assert "image_variant" in cols
    assert "current_session_id" in cols
    assert "last_known_ip" in cols
    assert "last_known_country" in cols
    assert "tags" in cols
    assert "auto_snapshot_enabled" in cols

    # Defaults wired correctly
    assert cols["image_variant"].default.arg == ImageVariant.vanilla
    assert cols["auto_snapshot_enabled"].default.arg is False


def test_proxy_model_has_new_columns() -> None:
    """Proxy gains session_username_template + supports_rotation."""
    from cloude_api.models.proxy import Proxy

    cols = Proxy.__table__.columns
    assert "session_username_template" in cols
    assert "supports_rotation" in cols

    # Default template matches Bright Data convention
    assert cols["session_username_template"].default.arg == "{user}-session-{session}"
    assert cols["supports_rotation"].default.arg is True


def test_invite_model_has_quota_column() -> None:
    """Invite carries the quota the redeemed user inherits."""
    from cloude_api.models.invite import Invite

    cols = Invite.__table__.columns
    assert "quota_instances" in cols
    assert cols["quota_instances"].default.arg == 3


def test_snapshot_model_shape() -> None:
    """Snapshot has all columns from design spec §4.2."""
    from cloude_api.models.snapshot import Snapshot

    cols = Snapshot.__table__.columns
    expected = {
        "id",
        "device_id",
        "user_id",
        "name",
        "kind",
        "size_bytes",
        "local_path",
        "s3_key",
        "state",
        "error_msg",
        "created_at",
    }
    assert expected.issubset(set(cols.keys())), f"missing: {expected - set(cols.keys())}"
    # Indexes
    index_names = {idx.name for idx in Snapshot.__table__.indexes}
    assert "ix_snapshots_device_created" in index_names


def test_device_file_model_shape() -> None:
    """DeviceFile has all columns from design spec §4.4."""
    from cloude_api.models.device_file import DeviceFile

    cols = DeviceFile.__table__.columns
    expected = {
        "id",
        "device_id",
        "user_id",
        "op",
        "filename",
        "phone_path",
        "size_bytes",
        "state",
        "error_msg",
        "created_at",
        "completed_at",
    }
    assert expected.issubset(set(cols.keys())), f"missing: {expected - set(cols.keys())}"


def test_models_package_exports_new_models() -> None:
    """models/__init__.py must export Snapshot + DeviceFile so Alembic sees them."""
    import cloude_api.models as m

    assert hasattr(m, "Snapshot")
    assert hasattr(m, "DeviceFile")
    assert "Snapshot" in m.__all__
    assert "DeviceFile" in m.__all__


def test_snapshot_read_schema_round_trip() -> None:
    """SnapshotRead pydantic model accepts an ORM-shaped dict."""
    import uuid
    from datetime import datetime

    from cloude_api.enums import SnapshotKind, SnapshotState
    from cloude_api.schemas.snapshot import SnapshotRead

    payload = {
        "id": uuid.uuid4(),
        "device_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "name": "manual-1",
        "kind": SnapshotKind.manual,
        "size_bytes": 1234,
        "local_path": "/x/y.tar.zst",
        "s3_key": None,
        "state": SnapshotState.ready,
        "error_msg": None,
        "created_at": datetime.now(UTC),
    }
    read = SnapshotRead.model_validate(payload)
    assert read.kind == SnapshotKind.manual
    assert read.state == SnapshotState.ready


def test_device_file_read_schema_round_trip() -> None:
    """DeviceFileRead pydantic model accepts an ORM-shaped dict."""
    import uuid
    from datetime import datetime

    from cloude_api.enums import DeviceFileOp, DeviceFileState
    from cloude_api.schemas.device_file import DeviceFileRead

    payload = {
        "id": uuid.uuid4(),
        "device_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "op": DeviceFileOp.apk_install,
        "filename": "app.apk",
        "phone_path": None,
        "size_bytes": 4096,
        "state": DeviceFileState.done,
        "error_msg": None,
        "created_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
    }
    read = DeviceFileRead.model_validate(payload)
    assert read.op == DeviceFileOp.apk_install
    assert read.state == DeviceFileState.done
