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
