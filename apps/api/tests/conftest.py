"""Pytest fixtures + env defaults so settings load in-process."""

from __future__ import annotations

import os

# Defaults BEFORE any cloude_api import. These are throwaway dev values; the
# integration test overrides DATABASE_URL/REDIS_URL to the running services.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-test-secret-AAAA")
os.environ.setdefault("STREAM_TOKEN_SECRET", "test-stream-test-stream-test-stream-test-stream-AAAA")
os.environ.setdefault("ENCRYPTION_PUBLIC_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("ENCRYPTION_PRIVATE_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("ENVIRONMENT", "test")
