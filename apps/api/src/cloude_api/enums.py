"""Enums used by both models and pydantic schemas. Native PG enums in DB."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class ProxyType(str, Enum):
    socks5 = "socks5"
    http = "http"


class DeviceState(str, Enum):
    creating = "creating"
    running = "running"
    stopping = "stopping"
    stopped = "stopped"
    error = "error"
    deleted = "deleted"


class ImageVariant(str, Enum):
    vanilla = "vanilla"
    daily = "daily"


class SnapshotKind(str, Enum):
    manual = "manual"
    auto = "auto"
    pre_restore = "pre-restore"  # value uses hyphen to match design spec


class SnapshotState(str, Enum):
    creating = "creating"
    ready = "ready"
    error = "error"
    deleted = "deleted"


class DeviceFileOp(str, Enum):
    apk_install = "apk_install"
    file_push = "file_push"
    file_pull = "file_pull"


class DeviceFileState(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
