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
