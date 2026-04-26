"""Unit tests for P1a extension models + enums (no DB required)."""
from __future__ import annotations


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
