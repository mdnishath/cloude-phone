"""Pure-logic tests for device router helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.schemas.device import DevicePublic


def _make_device(state: DeviceState) -> Device:
    d = Device(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="t",
        profile_id=uuid.uuid4(),
        proxy_id=None,
        state=state,
    )
    d.created_at = datetime.now(tz=UTC)
    return d


def test_device_public_serializes_state_as_string() -> None:
    d = _make_device(DeviceState.creating)
    out = DevicePublic.model_validate(d).model_dump(mode="json")
    assert out["state"] == "creating"


def test_device_public_round_trips_running() -> None:
    d = _make_device(DeviceState.running)
    out = DevicePublic.model_validate(d).model_dump(mode="json")
    assert out["state"] == "running"
    assert out["adb_host_port"] is None
