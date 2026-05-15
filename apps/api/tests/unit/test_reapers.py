"""Tests for reapers.STUCK_THRESHOLD_SECONDS, reap_stuck_devices, orphan_scan (mocked)."""

from __future__ import annotations

from cloude_api.workers import reapers


def test_stuck_threshold_is_three_minutes() -> None:
    assert reapers.STUCK_THRESHOLD_SECONDS == 180


def test_module_exports_required_callables() -> None:
    # These names are imported by arq_settings; if a refactor renames them,
    # this test catches it before runtime.
    assert callable(reapers.reap_stuck_devices)
    assert callable(reapers.orphan_scan)
