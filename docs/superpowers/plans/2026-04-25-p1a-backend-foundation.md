# P1a Backend Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI control plane, async worker scaffold, Postgres + Redis services, JWT-auth + invite redemption flow, and stub device-lifecycle endpoints — enough that an admin can mint an invite, a user can redeem it, create a device row that transitions `creating → running` via a stub worker job, and a CI pipeline enforces lint/type/test on every push.

**Architecture:** A FastAPI ASGI app (`apps/api/`) talks to Postgres 16 via SQLAlchemy 2 async + asyncpg, and to Redis 7 for the arq job queue, refresh-token denylist, stream-token nonces, and pub/sub for WebSocket fan-out. An arq worker process consumes the queue and runs lifecycle jobs — in P1a only a single stub job that sleeps then flips `creating → running` (no Docker SDK, that lands in P1b). A root `docker-compose.yml` defines `postgres`, `redis`, `api`, `worker` as the four services for the control plane; the per-device sidecar/redroid spawn from P0 stays untouched. Auth is JWT (HS256, 15-min access / 30-day refresh, rotated via Redis denylist), invite-only (admin CLI mints a token; user POSTs token + email + password to `/auth/redeem-invite`). Proxy passwords live in `proxies.password_encrypted` as libsodium sealed boxes, key from `ENCRYPTION_KEY` env.

**Tech Stack:** Python 3.11, FastAPI 0.110+, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic v2, arq 0.25, redis-py 5 (asyncio), PyNaCl (libsodium), python-jose[cryptography] (JWT), passlib[argon2] + argon2-cffi, slowapi, httpx (test client), pytest + pytest-asyncio, ruff, mypy --strict, Postgres 16, Redis 7, GitHub Actions.

---

## File Structure (target after P1a)

```
E:\cloude-phone\
├── .env.example                              (extended)
├── .github/
│   └── workflows/
│       └── api-ci.yml                        (new)
├── docker-compose.yml                        (new)
├── docker/
│   └── sidecar/                              (P0, untouched)
├── scripts/
│   └── p0/                                   (P0, untouched)
├── apps/
│   └── api/
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── alembic.ini
│       ├── alembic/
│       │   ├── env.py
│       │   ├── script.py.mako
│       │   └── versions/
│       │       └── 0001_initial_schema.py
│       ├── src/cloude_api/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── db.py
│       │   ├── enums.py
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   ├── auth.py
│       │   │   ├── deps.py
│       │   │   ├── encryption.py
│       │   │   ├── security.py
│       │   │   ├── stream_token.py
│       │   │   ├── audit.py
│       │   │   └── rate_limit.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── user.py
│       │   │   ├── invite.py
│       │   │   ├── device_profile.py
│       │   │   ├── proxy.py
│       │   │   ├── device.py
│       │   │   ├── session.py
│       │   │   └── audit_log.py
│       │   ├── schemas/
│       │   │   ├── __init__.py
│       │   │   ├── auth.py
│       │   │   ├── user.py
│       │   │   ├── device_profile.py
│       │   │   ├── proxy.py
│       │   │   ├── device.py
│       │   │   └── error.py
│       │   ├── api/
│       │   │   ├── __init__.py
│       │   │   ├── router.py
│       │   │   ├── auth.py
│       │   │   ├── me.py
│       │   │   ├── device_profiles.py
│       │   │   ├── proxies.py
│       │   │   └── devices.py
│       │   ├── workers/
│       │   │   ├── __init__.py
│       │   │   ├── arq_settings.py
│       │   │   └── tasks.py
│       │   └── ws/
│       │       ├── __init__.py
│       │       ├── status.py
│       │       └── pubsub.py
│       ├── scripts/
│       │   ├── seed_profiles.py
│       │   └── make_invite.py
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py
│           ├── unit/
│           │   ├── __init__.py
│           │   ├── test_security.py
│           │   ├── test_auth_handlers.py
│           │   ├── test_encryption.py
│           │   ├── test_stream_token.py
│           │   ├── test_proxies.py
│           │   └── test_devices.py
│           └── integration/
│               ├── __init__.py
│               └── test_e2e_invite_to_running.py
└── docs/superpowers/plans/
    └── 2026-04-25-p1a-backend-foundation.md  (this file)
```

---

## Task 0: Scaffold `apps/api/` and pyproject

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/cloude_api/__init__.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/tests/unit/__init__.py`
- Create: `apps/api/tests/integration/__init__.py`

- [ ] **Step 1:** Make directories

```bash
mkdir -p apps/api/src/cloude_api apps/api/tests/unit apps/api/tests/integration apps/api/alembic/versions apps/api/scripts
```

- [ ] **Step 2:** Write `apps/api/pyproject.toml`

```toml
[project]
name = "cloude-api"
version = "0.1.0"
description = "Cloud Android control plane API"
requires-python = ">=3.11,<3.13"
dependencies = [
  "fastapi==0.110.3",
  "uvicorn[standard]==0.29.0",
  "pydantic==2.7.1",
  "pydantic-settings==2.2.1",
  "sqlalchemy[asyncio]==2.0.30",
  "asyncpg==0.29.0",
  "alembic==1.13.1",
  "redis==5.0.4",
  "arq==0.25.0",
  "python-jose[cryptography]==3.3.0",
  "passlib[argon2]==1.7.4",
  "argon2-cffi==23.1.0",
  "pynacl==1.5.0",
  "slowapi==0.1.9",
  "httpx==0.27.0",
  "python-multipart==0.0.9",
  "email-validator==2.1.1",
  "websockets==12.0",
  "anyio==4.3.0",
]

[project.optional-dependencies]
dev = [
  "pytest==8.2.0",
  "pytest-asyncio==0.23.6",
  "pytest-cov==5.0.0",
  "ruff==0.4.4",
  "mypy==1.10.0",
  "types-python-jose==3.3.4.20240106",
  "types-passlib==1.7.7.20240327",
  "asgi-lifespan==2.1.0",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests", "scripts"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "RUF", "ASYNC", "S"]
ignore = ["S101", "S104", "B008"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S105", "S106"]
"scripts/**" = ["S105", "S106"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
exclude = ["alembic/versions"]
disallow_untyped_decorators = false

[[tool.mypy.overrides]]
module = ["arq.*", "slowapi.*", "passlib.*", "nacl.*", "jose.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
markers = [
  "integration: requires running postgres + redis (docker compose up)",
]
```

- [ ] **Step 3:** Add empty package markers

```bash
: > apps/api/src/cloude_api/__init__.py
: > apps/api/tests/__init__.py
: > apps/api/tests/unit/__init__.py
: > apps/api/tests/integration/__init__.py
```

- [ ] **Step 4:** Verify the project parses

```bash
cd apps/api && python -m pip install -e ".[dev]" --quiet && python -c "import cloude_api; print('ok')"
```

Expected output: `ok`. (Pip install can take ~60–90 s the first time; subsequent runs are fast.)

- [ ] **Step 5:** Commit

```bash
git add apps/api/pyproject.toml apps/api/src/cloude_api/__init__.py apps/api/tests/
git commit -m "chore(api): scaffold cloude-api package"
```

---

## Task 1: Settings (`config.py`) and `.env.example` extensions

**Files:**
- Create: `apps/api/src/cloude_api/config.py`
- Modify: `.env.example`

- [ ] **Step 1:** Extend `.env.example`

Append to the existing `E:\cloude-phone\.env.example`:

```
# ────────────────────────────────────────────────────────────────────
# P1a — Control plane (api + worker)
# ────────────────────────────────────────────────────────────────────

# Postgres
POSTGRES_USER=cloude
POSTGRES_PASSWORD=changeme_local_dev
POSTGRES_DB=cloude
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@postgres:5432/cloude

# Redis
REDIS_URL=redis://redis:6379/0

# JWT — generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET=replace_me_with_64_byte_urlsafe_token
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_SECONDS=2592000

# libsodium sealed-box keypair for proxy password encryption
# Generate with: python -m cloude_api.core.encryption keygen
ENCRYPTION_PUBLIC_KEY=replace_me_base64_32_byte_public_key
ENCRYPTION_PRIVATE_KEY=replace_me_base64_32_byte_private_key

# Stream token (HMAC) — separate secret from JWT
STREAM_TOKEN_SECRET=replace_me_with_64_byte_urlsafe_token
STREAM_TOKEN_TTL_SECONDS=300

# CORS — comma-separated origins. Leave empty in P1a (no dashboard yet).
CORS_ORIGINS=

# API runtime
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=info
ENVIRONMENT=dev
```

- [ ] **Step 2:** Write `apps/api/src/cloude_api/config.py`

```python
"""Application settings loaded from env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # rely on process env (docker-compose injects)
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")

    # Redis
    redis_url: str = Field(..., alias="REDIS_URL")

    # JWT
    jwt_secret: str = Field(..., alias="JWT_SECRET", min_length=32)
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_seconds: int = Field(900, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(2_592_000, alias="JWT_REFRESH_TTL_SECONDS")

    # Encryption (libsodium sealed box, base64-encoded 32-byte keys)
    encryption_public_key: str = Field(..., alias="ENCRYPTION_PUBLIC_KEY")
    encryption_private_key: str = Field(..., alias="ENCRYPTION_PRIVATE_KEY")

    # Stream token
    stream_token_secret: str = Field(..., alias="STREAM_TOKEN_SECRET", min_length=32)
    stream_token_ttl_seconds: int = Field(300, alias="STREAM_TOKEN_TTL_SECONDS")

    # CORS
    cors_origins: str = Field("", alias="CORS_ORIGINS")

    # Runtime
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    api_log_level: str = Field("info", alias="API_LOG_LEVEL")
    environment: str = Field("dev", alias="ENVIRONMENT")

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 3:** Smoke-test settings load with stub env

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://x:y@h/d \
  REDIS_URL=redis://h:6379/0 \
  JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  STREAM_TOKEN_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  python -c "from cloude_api.config import get_settings; s=get_settings(); print(s.environment, s.jwt_algorithm)"
```

Expected: `dev HS256`.

- [ ] **Step 4:** Commit

```bash
git add .env.example apps/api/src/cloude_api/config.py
git commit -m "feat(api): settings module + .env.example for control plane"
```

---

## Task 2: Enums + SQLAlchemy `Base` + `db.py`

**Files:**
- Create: `apps/api/src/cloude_api/enums.py`
- Create: `apps/api/src/cloude_api/models/__init__.py`
- Create: `apps/api/src/cloude_api/models/base.py`
- Create: `apps/api/src/cloude_api/db.py`

- [ ] **Step 1:** Write `enums.py`

```python
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
```

- [ ] **Step 2:** Write `models/base.py`

```python
"""Declarative base shared by all ORM models."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this. Note: SQLAlchemy reserves the attribute
    name ``metadata`` on DeclarativeBase, so any column literally called
    ``metadata`` (e.g. on audit_log) must be mapped via a different Python
    attribute name (we use ``metadata_``)."""
```

- [ ] **Step 3:** Write `models/__init__.py`

```python
"""Re-export models so Alembic autogenerate sees them all."""
from cloude_api.models.audit_log import AuditLog
from cloude_api.models.base import Base
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.invite import Invite
from cloude_api.models.proxy import Proxy
from cloude_api.models.session import Session
from cloude_api.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Device",
    "DeviceProfile",
    "Invite",
    "Proxy",
    "Session",
    "User",
]
```

(Files referenced here are written in later tasks; the import will resolve once those tasks complete. Keep this file as the single source of truth for "all models".)

- [ ] **Step 4:** Write `db.py`

```python
"""Async engine + session factory. One engine per process."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cloude_api.config import get_settings


def make_engine() -> object:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        future=True,
    )


_engine = make_engine()
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_engine,  # type: ignore[arg-type]
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Use in workers / scripts. Routes use FastAPI dependency `get_db`."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/enums.py apps/api/src/cloude_api/db.py \
        apps/api/src/cloude_api/models/__init__.py apps/api/src/cloude_api/models/base.py
git commit -m "feat(api): enums + SQLAlchemy base + async engine"
```

---

## Task 3: ORM models — User, Invite

**Files:**
- Create: `apps/api/src/cloude_api/models/user.py`
- Create: `apps/api/src/cloude_api/models/invite.py`

- [ ] **Step 1:** Write `models/user.py`

```python
"""User account."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import UserRole
from cloude_api.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False, native_enum=True),
        nullable=False,
        default=UserRole.user,
    )
    quota_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2:** Write `models/invite.py`

```python
"""Single-use invite token. Admin mints; user redeems to create account."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import UserRole
from cloude_api.models.base import Base


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # sha256 hex of the raw token (stored hashed so DB leak doesn't grant access)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False, native_enum=True),
        nullable=False,
        default=UserRole.user,
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=__import__("sqlalchemy").func.now(), nullable=False
    )
```

(The `__import__("sqlalchemy").func.now()` pattern is intentional only because we already import other names; if you prefer, put `from sqlalchemy import func` at the top and use `func.now()`. Either is fine — pick one and keep it consistent.) Cleaner version:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import UserRole
from cloude_api.models.base import Base


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False, native_enum=True),
        nullable=False,
        default=UserRole.user,
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

Use the cleaner version.

- [ ] **Step 3:** Commit

```bash
git add apps/api/src/cloude_api/models/user.py apps/api/src/cloude_api/models/invite.py
git commit -m "feat(api): User + Invite ORM models"
```

---

## Task 4: ORM models — DeviceProfile, Proxy

**Files:**
- Create: `apps/api/src/cloude_api/models/device_profile.py`
- Create: `apps/api/src/cloude_api/models/proxy.py`

- [ ] **Step 1:** Write `models/device_profile.py`

```python
"""Hardware template chosen at device-create time."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.models.base import Base


class DeviceProfile(Base):
    __tablename__ = "device_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    android_version: Mapped[str] = mapped_column(String(8), nullable=False, default="11")
    screen_width: Mapped[int] = mapped_column(Integer, nullable=False)
    screen_height: Mapped[int] = mapped_column(Integer, nullable=False)
    screen_dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    manufacturer: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2:** Write `models/proxy.py`

```python
"""User-owned proxy config. password_encrypted is libsodium sealed box."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import ProxyType
from cloude_api.models.base import Base


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[ProxyType] = mapped_column(
        SAEnum(ProxyType, name="proxy_type", create_constraint=False, native_enum=True),
        nullable=False,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3:** Commit

```bash
git add apps/api/src/cloude_api/models/device_profile.py apps/api/src/cloude_api/models/proxy.py
git commit -m "feat(api): DeviceProfile + Proxy ORM models"
```

---

## Task 5: ORM models — Device, Session, AuditLog

**Files:**
- Create: `apps/api/src/cloude_api/models/device.py`
- Create: `apps/api/src/cloude_api/models/session.py`
- Create: `apps/api/src/cloude_api/models/audit_log.py`

- [ ] **Step 1:** Write `models/device.py`

```python
"""Per-instance device record. State-machine column drives lifecycle."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceState
from cloude_api.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_profiles.id"), nullable=False
    )
    proxy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[DeviceState] = mapped_column(
        SAEnum(DeviceState, name="device_state", create_constraint=False, native_enum=True),
        nullable=False,
        default=DeviceState.creating,
        index=True,
    )
    state_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    redroid_container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sidecar_container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adb_host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_devices_user_id_state", "user_id", "state"),
    )
```

- [ ] **Step 2:** Write `models/session.py`

```python
"""Active streaming WS session. Rows ttl-collected by idle reaper (P1b)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_ping_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    client_ip: Mapped[str | None] = mapped_column(INET, nullable=True)

    __table_args__ = (
        Index("ix_sessions_device_lastping", "device_id", "last_ping_at"),
    )
```

- [ ] **Step 3:** Write `models/audit_log.py`

```python
"""Append-only audit trail.

DeclarativeBase reserves ``metadata``, so we map column ``metadata``
to Python attribute ``metadata_``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_user_created", "user_id", "created_at"),
    )
```

- [ ] **Step 4:** Verify all models import cleanly

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://x:y@h/d \
  REDIS_URL=redis://h/0 \
  JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  STREAM_TOKEN_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  python -c "from cloude_api.models import Base, User, Invite, DeviceProfile, Proxy, Device, Session, AuditLog; print(sorted(Base.metadata.tables.keys()))"
```

Expected: `['audit_log', 'device_profiles', 'devices', 'invites', 'proxies', 'sessions', 'users']`.

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/models/device.py apps/api/src/cloude_api/models/session.py apps/api/src/cloude_api/models/audit_log.py
git commit -m "feat(api): Device + Session + AuditLog ORM models"
```

---

## Task 6: Alembic config + initial migration

**Files:**
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/script.py.mako`
- Create: `apps/api/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1:** Write `apps/api/alembic.ini`

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
version_path_separator = os
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2:** Write `apps/api/alembic/env.py`

```python
"""Alembic env using async engine + sync migration ops."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from cloude_api.config import get_settings
from cloude_api.models import Base  # noqa: F401  triggers all model imports

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DATABASE_URL from settings (avoids duplicating it in alembic.ini)
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3:** Write `apps/api/alembic/script.py.mako`

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4:** Write `apps/api/alembic/versions/0001_initial_schema.py`

```python
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
```

- [ ] **Step 5:** Commit

```bash
git add apps/api/alembic.ini apps/api/alembic/env.py apps/api/alembic/script.py.mako apps/api/alembic/versions/0001_initial_schema.py
git commit -m "feat(api): alembic config + initial schema migration"
```

---

## Task 7: docker-compose.yml (postgres + redis only first, smoke-tested)

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1:** Write `docker-compose.yml` (api + worker added in Task 9; this version is pg + redis so we can run migrations from host)

```yaml
# Cloude Phone — control-plane services.
# Per-device redroid + sidecar containers are spawned dynamically by the worker
# (P1b) and are NOT defined here.

services:
  postgres:
    image: postgres:16
    container_name: cloude-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-cloude}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme_local_dev}
      POSTGRES_DB: ${POSTGRES_DB:-cloude}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-cloude} -d ${POSTGRES_DB:-cloude}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: cloude-redis
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
```

- [ ] **Step 2:** Bring services up

```bash
cd /e/cloude-phone && docker compose up -d postgres redis
docker compose ps
```

Expected: both containers `Up (healthy)` within ~10 s.

- [ ] **Step 3:** Run the migration against local Postgres

```bash
cd apps/api && \
  DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude \
  REDIS_URL=redis://localhost:6379/0 \
  JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  STREAM_TOKEN_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
  ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  python -m alembic upgrade head
```

Expected last line: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema`.

- [ ] **Step 4:** Verify tables exist

```bash
docker exec -it cloude-postgres psql -U cloude -d cloude -c "\dt"
```

Expected: 7 tables — `users`, `invites`, `device_profiles`, `proxies`, `devices`, `sessions`, `audit_log`.

- [ ] **Step 5:** Commit

```bash
git add docker-compose.yml
git commit -m "feat(infra): docker-compose with postgres + redis"
```

---

## Task 8: API Dockerfile

**Files:**
- Create: `apps/api/Dockerfile`

- [ ] **Step 1:** Write Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (cache layer)
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

# App source
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000

# Default CMD is API; worker overrides in compose
CMD ["uvicorn", "cloude_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2:** Build it

```bash
docker build -t cloude/api:dev apps/api
```

Expected: image builds in ~90 s on first run; final line `naming to docker.io/cloude/api:dev`.

- [ ] **Step 3:** Commit

```bash
git add apps/api/Dockerfile
git commit -m "feat(api): Dockerfile (python 3.11-slim, pinned deps)"
```

---

## Task 9: Extend docker-compose with api + worker services

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1:** Append `api` and `worker` services. Final compose:

```yaml
services:
  postgres:
    image: postgres:16
    container_name: cloude-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-cloude}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme_local_dev}
      POSTGRES_DB: ${POSTGRES_DB:-cloude}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-cloude} -d ${POSTGRES_DB:-cloude}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: cloude-redis
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  api:
    build: ./apps/api
    image: cloude/api:dev
    container_name: cloude-api
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      JWT_SECRET: ${JWT_SECRET}
      JWT_ALGORITHM: ${JWT_ALGORITHM:-HS256}
      JWT_ACCESS_TTL_SECONDS: ${JWT_ACCESS_TTL_SECONDS:-900}
      JWT_REFRESH_TTL_SECONDS: ${JWT_REFRESH_TTL_SECONDS:-2592000}
      ENCRYPTION_PUBLIC_KEY: ${ENCRYPTION_PUBLIC_KEY}
      ENCRYPTION_PRIVATE_KEY: ${ENCRYPTION_PRIVATE_KEY}
      STREAM_TOKEN_SECRET: ${STREAM_TOKEN_SECRET}
      STREAM_TOKEN_TTL_SECONDS: ${STREAM_TOKEN_TTL_SECONDS:-300}
      CORS_ORIGINS: ${CORS_ORIGINS:-}
      ENVIRONMENT: ${ENVIRONMENT:-dev}
      API_LOG_LEVEL: ${API_LOG_LEVEL:-info}
    ports:
      - "8000:8000"
    command: ["uvicorn", "cloude_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
    restart: unless-stopped

  worker:
    build: ./apps/api
    image: cloude/api:dev
    container_name: cloude-worker
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      JWT_SECRET: ${JWT_SECRET}
      JWT_ALGORITHM: ${JWT_ALGORITHM:-HS256}
      ENCRYPTION_PUBLIC_KEY: ${ENCRYPTION_PUBLIC_KEY}
      ENCRYPTION_PRIVATE_KEY: ${ENCRYPTION_PRIVATE_KEY}
      STREAM_TOKEN_SECRET: ${STREAM_TOKEN_SECRET}
      ENVIRONMENT: ${ENVIRONMENT:-dev}
    command: ["arq", "cloude_api.workers.arq_settings.WorkerSettings"]
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
```

- [ ] **Step 2:** Commit (api/worker won't start yet because `main.py` and `arq_settings.py` don't exist — that's fine, we'll bring them up after Task 19)

```bash
git add docker-compose.yml
git commit -m "feat(infra): add api + worker services to compose"
```

---

## Task 10: Encryption helpers + keygen CLI

**Files:**
- Create: `apps/api/src/cloude_api/core/__init__.py`
- Create: `apps/api/src/cloude_api/core/encryption.py`
- Create: `apps/api/tests/unit/test_encryption.py`

- [ ] **Step 1:** Write the failing test FIRST

`apps/api/tests/unit/test_encryption.py`:

```python
"""Tests for libsodium sealed-box helpers."""
from __future__ import annotations

import base64

from cloude_api.core.encryption import (
    decrypt_password,
    encrypt_password,
    generate_keypair,
)


def test_keypair_generates_two_distinct_b64_strings() -> None:
    pub, priv = generate_keypair()
    assert isinstance(pub, str) and isinstance(priv, str)
    assert pub != priv
    # base64-decoded length is 32 (Curve25519)
    assert len(base64.b64decode(pub)) == 32
    assert len(base64.b64decode(priv)) == 32


def test_round_trip_encrypts_and_decrypts() -> None:
    pub, priv = generate_keypair()
    plaintext = "hunter2-passw0rd!"
    ct = encrypt_password(plaintext, pub_b64=pub)
    assert isinstance(ct, bytes) and len(ct) > 0
    assert decrypt_password(ct, pub_b64=pub, priv_b64=priv) == plaintext


def test_two_encryptions_differ_due_to_random_nonce() -> None:
    pub, _priv = generate_keypair()
    a = encrypt_password("same", pub_b64=pub)
    b = encrypt_password("same", pub_b64=pub)
    assert a != b


def test_decrypt_with_wrong_key_raises() -> None:
    pub_a, _ = generate_keypair()
    _, priv_b = generate_keypair()
    ct = encrypt_password("secret", pub_b64=pub_a)
    try:
        decrypt_password(ct, pub_b64=pub_a, priv_b64=priv_b)
    except Exception:
        return
    raise AssertionError("expected decryption with wrong key to fail")
```

- [ ] **Step 2:** Run test — FAILS (no module yet)

```bash
cd apps/api && pytest tests/unit/test_encryption.py
```

Expected: `ModuleNotFoundError: No module named 'cloude_api.core.encryption'`.

- [ ] **Step 3:** Make `core/__init__.py`

```bash
: > apps/api/src/cloude_api/core/__init__.py
```

- [ ] **Step 4:** Implement `apps/api/src/cloude_api/core/encryption.py`

```python
"""libsodium sealed-box wrapper for proxy passwords.

Sealed boxes give us "anyone-can-encrypt, only-recipient-can-decrypt" with
ephemeral sender keys baked into the ciphertext. The API server holds both
public and private keys (single-tenant); rotation is a future concern (P2+).
"""
from __future__ import annotations

import base64
import sys

from nacl.public import PrivateKey, PublicKey, SealedBox


def generate_keypair() -> tuple[str, str]:
    """Generate a new Curve25519 keypair, returned as base64 strings."""
    sk = PrivateKey.generate()
    pk = sk.public_key
    return (
        base64.b64encode(bytes(pk)).decode("ascii"),
        base64.b64encode(bytes(sk)).decode("ascii"),
    )


def _load_public(pub_b64: str) -> PublicKey:
    return PublicKey(base64.b64decode(pub_b64))


def _load_private(priv_b64: str) -> PrivateKey:
    return PrivateKey(base64.b64decode(priv_b64))


def encrypt_password(plaintext: str, *, pub_b64: str) -> bytes:
    """Encrypt with the public key. Output is opaque bytes for `proxies.password_encrypted`."""
    if not plaintext:
        return b""
    box = SealedBox(_load_public(pub_b64))
    return bytes(box.encrypt(plaintext.encode("utf-8")))


def decrypt_password(ciphertext: bytes, *, pub_b64: str, priv_b64: str) -> str:
    """Decrypt. Raises if ciphertext was forged or wrong key."""
    if not ciphertext:
        return ""
    pk = _load_public(pub_b64)
    sk = _load_private(priv_b64)
    box = SealedBox(sk)  # SealedBox decrypt only needs the recipient secret key
    _ = pk  # kept for symmetry / future explicit verification
    return box.decrypt(ciphertext).decode("utf-8")


def _cli() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "keygen":
        pub, priv = generate_keypair()
        print(f"ENCRYPTION_PUBLIC_KEY={pub}")
        print(f"ENCRYPTION_PRIVATE_KEY={priv}")
        return 0
    print("usage: python -m cloude_api.core.encryption keygen", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
```

- [ ] **Step 5:** Re-run test — PASSES

```bash
cd apps/api && pytest tests/unit/test_encryption.py -v
```

Expected: `4 passed`.

- [ ] **Step 6:** Smoke-test the CLI

```bash
cd apps/api && python -m cloude_api.core.encryption keygen
```

Expected: two `ENCRYPTION_*_KEY=...` lines.

- [ ] **Step 7:** Commit

```bash
git add apps/api/src/cloude_api/core/__init__.py apps/api/src/cloude_api/core/encryption.py apps/api/tests/unit/test_encryption.py
git commit -m "feat(api): libsodium sealed-box encryption + keygen CLI"
```

---

## Task 11: Password hashing + JWT helpers (`security.py`)

**Files:**
- Create: `apps/api/src/cloude_api/core/security.py`
- Create: `apps/api/tests/unit/test_security.py`

- [ ] **Step 1:** Write the failing test

`apps/api/tests/unit/test_security.py`:

```python
"""Tests for password hashing + JWT issue/decode."""
from __future__ import annotations

import time

import pytest
from jose import JWTError

from cloude_api.core import security


def test_hash_password_returns_argon2_phc_string() -> None:
    h = security.hash_password("hunter2")
    assert h.startswith("$argon2id$")


def test_verify_password_accepts_correct() -> None:
    h = security.hash_password("hunter2")
    assert security.verify_password("hunter2", h) is True


def test_verify_password_rejects_wrong() -> None:
    h = security.hash_password("hunter2")
    assert security.verify_password("nope", h) is False


def test_create_access_and_decode_round_trip() -> None:
    tok = security.create_access_token(subject="user-123")
    payload = security.decode_token(tok)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_includes_jti() -> None:
    tok = security.create_refresh_token(subject="user-123")
    payload = security.decode_token(tok)
    assert payload["type"] == "refresh"
    assert "jti" in payload


def test_decode_rejects_tampered_token() -> None:
    tok = security.create_access_token(subject="user-123")
    tampered = tok[:-2] + ("aa" if tok[-2:] != "aa" else "bb")
    with pytest.raises(JWTError):
        security.decode_token(tampered)


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_now", lambda: int(time.time()) - 10_000)
    tok = security.create_access_token(subject="user-123")
    with pytest.raises(JWTError):
        security.decode_token(tok)
```

- [ ] **Step 2:** Run test — FAILS (no module)

```bash
cd apps/api && pytest tests/unit/test_security.py
```

- [ ] **Step 3:** Implement `apps/api/src/cloude_api/core/security.py`

```python
"""Password hashing (argon2id) + JWT issue/decode (HS256)."""
from __future__ import annotations

import time
import uuid
from typing import Any, cast

from jose import jwt
from passlib.context import CryptContext

from cloude_api.config import get_settings

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _now() -> int:
    return int(time.time())


def hash_password(plaintext: str) -> str:
    return cast(str, _pwd.hash(plaintext))


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return cast(bool, _pwd.verify(plaintext, hashed))
    except Exception:
        return False


def _encode(payload: dict[str, Any]) -> str:
    s = get_settings()
    return cast(str, jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm))


def create_access_token(*, subject: str, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + s.jwt_access_ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return _encode(payload)


def create_refresh_token(*, subject: str) -> str:
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": REFRESH_TOKEN_TYPE,
        "iat": now,
        "exp": now + s.jwt_refresh_ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return _encode(payload)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return cast(dict[str, Any], jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm]))
```

- [ ] **Step 4:** Set required env so settings load during test, run test

Create `apps/api/tests/conftest.py`:

```python
"""Pytest fixtures + env defaults so settings load in-process."""
from __future__ import annotations

import os

# Defaults BEFORE any cloude_api import. These are throwaway dev values; the
# integration test overrides DATABASE_URL/REDIS_URL to the running services.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-test-secret-AAAA")
os.environ.setdefault("STREAM_TOKEN_SECRET", "test-stream-test-stream-test-stream-test-stream-AAAA")
os.environ.setdefault("ENCRYPTION_PUBLIC_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("ENCRYPTION_PRIVATE_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("ENVIRONMENT", "test")
```

(The two AAAA-padded base64 strings happen to be valid 32-byte zero keys — fine for unit tests that don't actually round-trip encryption with these. The encryption test calls `generate_keypair()` itself.)

- [ ] **Step 5:** Run

```bash
cd apps/api && pytest tests/unit/test_security.py -v
```

Expected: `7 passed`.

- [ ] **Step 6:** Commit

```bash
git add apps/api/src/cloude_api/core/security.py apps/api/tests/unit/test_security.py apps/api/tests/conftest.py
git commit -m "feat(api): argon2 password + HS256 JWT helpers"
```

---

## Task 12: Stream token (HMAC) + Redis nonce store

**Files:**
- Create: `apps/api/src/cloude_api/core/stream_token.py`
- Create: `apps/api/tests/unit/test_stream_token.py`

- [ ] **Step 1:** Write the failing test

`apps/api/tests/unit/test_stream_token.py`:

```python
"""Tests for HMAC stream-token issue/verify (no Redis)."""
from __future__ import annotations

import time

import pytest

from cloude_api.core import stream_token as st


def test_token_is_three_segments() -> None:
    tok = st.issue("device-id-1")
    assert tok.count(":") == 2


def test_verify_round_trip_returns_payload() -> None:
    tok = st.issue("device-id-1")
    payload = st.verify(tok, expected_device_id="device-id-1")
    assert payload.device_id == "device-id-1"
    assert payload.exp > int(time.time())


def test_verify_rejects_wrong_device_id() -> None:
    tok = st.issue("device-id-1")
    with pytest.raises(st.StreamTokenError):
        st.verify(tok, expected_device_id="device-id-2")


def test_verify_rejects_tampered_signature() -> None:
    tok = st.issue("device-id-1")
    head, nonce, sig = tok.split(":")
    bad = f"{head}:{nonce}:{'A' * len(sig)}"
    with pytest.raises(st.StreamTokenError):
        st.verify(bad, expected_device_id="device-id-1")


def test_verify_rejects_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "_now", lambda: int(time.time()) - 10_000)
    tok = st.issue("device-id-1")
    monkeypatch.setattr(st, "_now", lambda: int(time.time()))
    with pytest.raises(st.StreamTokenError):
        st.verify(tok, expected_device_id="device-id-1")
```

- [ ] **Step 2:** Implement `apps/api/src/cloude_api/core/stream_token.py`

```python
"""Single-use, short-TTL HMAC token gating /ws/devices/{id}/stream.

Format: base64url(device_id):base64url(nonce):base64url(hmac_sha256)
where the HMAC input is `device_id|nonce|exp`, exp is encoded as ascii int
inside `device_id` segment (we pack `<device_id>|<exp>`).

Single-use enforcement (Redis SETNX `stream:nonce:<nonce>` with TTL) lives in
the websocket route — not here, because nonce-store testing belongs in the
integration suite where Redis is real.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from cloude_api.config import get_settings


def _now() -> int:
    return int(time.time())


class StreamTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StreamPayload:
    device_id: str
    nonce: str
    exp: int


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue(device_id: str) -> str:
    s = get_settings()
    exp = _now() + s.stream_token_ttl_seconds
    head_raw = f"{device_id}|{exp}".encode("utf-8")
    nonce = secrets.token_bytes(16)
    msg = head_raw + b"|" + nonce
    sig = hmac.new(s.stream_token_secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"{_b64e(head_raw)}:{_b64e(nonce)}:{_b64e(sig)}"


def verify(token: str, *, expected_device_id: str) -> StreamPayload:
    s = get_settings()
    try:
        head_b64, nonce_b64, sig_b64 = token.split(":")
        head_raw = _b64d(head_b64)
        nonce = _b64d(nonce_b64)
        sig = _b64d(sig_b64)
    except (ValueError, IndexError) as e:
        raise StreamTokenError("malformed token") from e

    expected_sig = hmac.new(
        s.stream_token_secret.encode("utf-8"), head_raw + b"|" + nonce, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise StreamTokenError("bad signature")

    try:
        device_id, exp_str = head_raw.decode("utf-8").split("|", 1)
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError) as e:
        raise StreamTokenError("malformed payload") from e

    if device_id != expected_device_id:
        raise StreamTokenError("device mismatch")
    if exp < _now():
        raise StreamTokenError("expired")

    return StreamPayload(device_id=device_id, nonce=nonce.hex(), exp=exp)
```

- [ ] **Step 3:** Run

```bash
cd apps/api && pytest tests/unit/test_stream_token.py -v
```

Expected: `5 passed`.

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/core/stream_token.py apps/api/tests/unit/test_stream_token.py
git commit -m "feat(api): HMAC stream-token issue + verify"
```

---

## Task 13: pydantic schemas (auth + user + error)

**Files:**
- Create: `apps/api/src/cloude_api/schemas/__init__.py`
- Create: `apps/api/src/cloude_api/schemas/error.py`
- Create: `apps/api/src/cloude_api/schemas/auth.py`
- Create: `apps/api/src/cloude_api/schemas/user.py`

- [ ] **Step 1:** Write `schemas/__init__.py`

```python
"""Pydantic v2 request/response models."""
```

- [ ] **Step 2:** Write `schemas/error.py`

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
```

- [ ] **Step 3:** Write `schemas/auth.py`

```python
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class TokenPair(BaseModel):
    access: str
    refresh: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh: str


class RedeemInviteRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
```

- [ ] **Step 4:** Write `schemas/user.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from cloude_api.enums import UserRole


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    quota_instances: int
    created_at: datetime
```

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/schemas/__init__.py apps/api/src/cloude_api/schemas/error.py \
        apps/api/src/cloude_api/schemas/auth.py apps/api/src/cloude_api/schemas/user.py
git commit -m "feat(api): auth + user + error pydantic schemas"
```

---

## Task 14: pydantic schemas (device_profile + proxy + device)

**Files:**
- Create: `apps/api/src/cloude_api/schemas/device_profile.py`
- Create: `apps/api/src/cloude_api/schemas/proxy.py`
- Create: `apps/api/src/cloude_api/schemas/device.py`

- [ ] **Step 1:** Write `schemas/device_profile.py`

```python
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class DeviceProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    android_version: str
    screen_width: int
    screen_height: int
    screen_dpi: int
    ram_mb: int
    cpu_cores: int
    manufacturer: str
    model: str
    is_public: bool
```

- [ ] **Step 2:** Write `schemas/proxy.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cloude_api.enums import ProxyType


class ProxyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    type: ProxyType
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)


class ProxyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    type: ProxyType
    host: str
    port: int
    username: str | None
    has_password: bool
    created_at: datetime
```

- [ ] **Step 3:** Write `schemas/device.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cloude_api.enums import DeviceState


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: uuid.UUID
    proxy_id: uuid.UUID | None = None


class DevicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile_id: uuid.UUID
    proxy_id: uuid.UUID | None
    state: DeviceState
    state_reason: str | None
    adb_host_port: int | None
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None


class AdbInfo(BaseModel):
    host: str
    port: int
    command: str


class StreamTokenResponse(BaseModel):
    token: str
    ttl_seconds: int
```

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/schemas/device_profile.py apps/api/src/cloude_api/schemas/proxy.py apps/api/src/cloude_api/schemas/device.py
git commit -m "feat(api): device_profile + proxy + device pydantic schemas"
```

---

## Task 15: Auth token machinery (`core/auth.py`) + Redis denylist

**Files:**
- Create: `apps/api/src/cloude_api/core/auth.py`
- Create: `apps/api/tests/unit/test_auth_handlers.py`

- [ ] **Step 1:** Write the failing test

`apps/api/tests/unit/test_auth_handlers.py`:

```python
"""Unit tests for invite hashing + token-rotation logic (Redis mocked)."""
from __future__ import annotations

import pytest

from cloude_api.core import auth


def test_generate_invite_token_returns_url_safe_string() -> None:
    raw = auth.generate_invite_token()
    assert len(raw) >= 32
    # URL-safe base64 alphabet only
    assert all(c.isalnum() or c in "-_" for c in raw)


def test_hash_invite_token_is_deterministic_sha256_hex() -> None:
    h1 = auth.hash_invite_token("hello")
    h2 = auth.hash_invite_token("hello")
    assert h1 == h2 and len(h1) == 64


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0


@pytest.mark.asyncio
async def test_refresh_denylist_set_and_check() -> None:
    r = FakeRedis()
    jti = "j-1"
    assert await auth.is_refresh_revoked(r, jti) is False
    assert await auth.revoke_refresh(r, jti, ttl_seconds=60) is True
    assert await auth.is_refresh_revoked(r, jti) is True


@pytest.mark.asyncio
async def test_revoke_refresh_idempotent_returns_false_second_time() -> None:
    r = FakeRedis()
    assert await auth.revoke_refresh(r, "j-2", ttl_seconds=60) is True
    assert await auth.revoke_refresh(r, "j-2", ttl_seconds=60) is False
```

- [ ] **Step 2:** Implement `apps/api/src/cloude_api/core/auth.py`

```python
"""Auth-flow primitives shared by routes + scripts.

Includes:
- invite token generation + sha256 hashing
- refresh-token denylist via Redis (set-on-use, with TTL = refresh lifetime)

The denylist stores the *used* refresh JTI. When the client presents a
refresh, the route checks the JTI is NOT in the denylist, then atomically
adds it (using SET NX), then issues a fresh access+refresh pair.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Protocol


def generate_invite_token() -> str:
    """Return a 32-byte url-safe random token (~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class _RedisLike(Protocol):
    async def set(
        self, key: str, value: str, *, ex: int | None = ..., nx: bool = ...
    ) -> bool: ...
    async def exists(self, key: str) -> int: ...


def _denylist_key(jti: str) -> str:
    return f"refresh:used:{jti}"


async def is_refresh_revoked(redis: _RedisLike, jti: str) -> bool:
    return bool(await redis.exists(_denylist_key(jti)))


async def revoke_refresh(redis: _RedisLike, jti: str, *, ttl_seconds: int) -> bool:
    """Mark a refresh JTI as used. Returns True if newly added, False if already revoked."""
    return bool(await redis.set(_denylist_key(jti), "1", ex=ttl_seconds, nx=True))
```

- [ ] **Step 3:** Run

```bash
cd apps/api && pytest tests/unit/test_auth_handlers.py -v
```

Expected: `4 passed`.

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/core/auth.py apps/api/tests/unit/test_auth_handlers.py
git commit -m "feat(api): invite token hash + refresh denylist primitives"
```

---

## Task 16: FastAPI deps (`core/deps.py`) + Redis client + audit helper + rate limiter

**Files:**
- Create: `apps/api/src/cloude_api/core/deps.py`
- Create: `apps/api/src/cloude_api/core/audit.py`
- Create: `apps/api/src/cloude_api/core/rate_limit.py`

- [ ] **Step 1:** Write `core/deps.py`

```python
"""FastAPI dependencies: DB session, Redis client, current user."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.config import get_settings
from cloude_api.core import security
from cloude_api.db import async_session_factory
from cloude_api.models.user import User


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = security.decode_token(token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if payload.get("type") != security.ACCESS_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not an access token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad subject") from e
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user gone")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
```

- [ ] **Step 2:** Write `core/audit.py`

```python
"""Audit-log writer. Always called within an existing session/transaction."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.models.audit_log import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )
    await db.flush()
```

- [ ] **Step 3:** Write `core/rate_limit.py`

```python
"""slowapi limiter — in-process. Move to Redis-backed before horizontal scale."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/core/deps.py apps/api/src/cloude_api/core/audit.py apps/api/src/cloude_api/core/rate_limit.py
git commit -m "feat(api): FastAPI deps + audit + rate-limit primitives"
```

---

## Task 17: Auth router (`/auth/login`, `/auth/refresh`, `/auth/redeem-invite`)

**Files:**
- Create: `apps/api/src/cloude_api/api/__init__.py`
- Create: `apps/api/src/cloude_api/api/auth.py`

- [ ] **Step 1:** Write `api/__init__.py`

```python
"""HTTP routers."""
```

- [ ] **Step 2:** Write `api/auth.py`

```python
"""Auth routes: login, refresh, redeem-invite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core import auth as auth_core
from cloude_api.core import security
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import DbSession, RedisClient
from cloude_api.core.rate_limit import limiter
from cloude_api.models.invite import Invite
from cloude_api.models.user import User
from cloude_api.schemas.auth import (
    LoginRequest,
    RedeemInviteRequest,
    RefreshRequest,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DbSession) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    refresh = security.create_refresh_token(subject=str(user.id))
    await write_audit(db, user_id=user.id, action="auth.login")
    await db.commit()
    return TokenPair(access=access, refresh=refresh)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh_tokens(
    request: Request, body: RefreshRequest, db: DbSession, redis: RedisClient
) -> TokenPair:
    try:
        payload = security.decode_token(body.refresh)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if payload.get("type") != security.REFRESH_TOKEN_TYPE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not a refresh token")
    jti = payload.get("jti")
    sub = payload.get("sub")
    exp = payload.get("exp")
    if not jti or not sub or not exp:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="malformed refresh")

    if await auth_core.is_refresh_revoked(redis, jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="refresh reused")

    s = get_settings()
    ttl = max(int(exp) - int(datetime.now(tz=timezone.utc).timestamp()), 0) or s.jwt_refresh_ttl_seconds
    added = await auth_core.revoke_refresh(redis, jti, ttl_seconds=ttl)
    if not added:
        # Race lost — another concurrent request claimed it first.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="refresh reused")

    try:
        user_id = uuid.UUID(sub)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="bad subject") from e
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user gone")

    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    new_refresh = security.create_refresh_token(subject=str(user.id))
    return TokenPair(access=access, refresh=new_refresh)


@router.post("/redeem-invite", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def redeem_invite(
    request: Request, body: RedeemInviteRequest, db: DbSession
) -> TokenPair:
    token_hash = auth_core.hash_invite_token(body.token)
    invite = await db.scalar(select(Invite).where(Invite.token_hash == token_hash))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invalid invite")
    now = datetime.now(tz=timezone.utc)
    if invite.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="already redeemed")
    if invite.expires_at < now:
        raise HTTPException(status.HTTP_410_GONE, detail="invite expired")

    target_email = (invite.email or body.email).lower()
    if invite.email and invite.email.lower() != body.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="email does not match invite")

    existing = await db.scalar(select(User).where(User.email == target_email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(
        id=uuid.uuid4(),
        email=target_email,
        password_hash=security.hash_password(body.password),
        role=invite.role,
    )
    db.add(user)
    invite.redeemed_at = now
    await db.flush()
    await write_audit(
        db,
        user_id=user.id,
        action="auth.redeem_invite",
        target_id=invite.id,
        metadata={"email": target_email},
    )
    await db.commit()

    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    refresh = security.create_refresh_token(subject=str(user.id))
    return TokenPair(access=access, refresh=refresh)
```

- [ ] **Step 3:** Commit

```bash
git add apps/api/src/cloude_api/api/__init__.py apps/api/src/cloude_api/api/auth.py
git commit -m "feat(api): /auth login + refresh + redeem-invite routes"
```

---

## Task 18: `/me` + `/device-profiles` routers

**Files:**
- Create: `apps/api/src/cloude_api/api/me.py`
- Create: `apps/api/src/cloude_api/api/device_profiles.py`

- [ ] **Step 1:** Write `api/me.py`

```python
"""GET /me — current user."""
from __future__ import annotations

from fastapi import APIRouter

from cloude_api.core.deps import CurrentUser
from cloude_api.schemas.user import UserPublic

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserPublic)
async def me(current: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current)
```

- [ ] **Step 2:** Write `api/device_profiles.py`

```python
"""GET /device-profiles — list available profiles for current user."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import or_, select

from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.schemas.device_profile import DeviceProfilePublic

router = APIRouter(prefix="/device-profiles", tags=["device-profiles"])


@router.get("", response_model=list[DeviceProfilePublic])
async def list_profiles(current: CurrentUser, db: DbSession) -> list[DeviceProfilePublic]:
    rows = (
        await db.scalars(
            select(DeviceProfile)
            .where(or_(DeviceProfile.is_public.is_(True), DeviceProfile.created_by == current.id))
            .order_by(DeviceProfile.name)
        )
    ).all()
    return [DeviceProfilePublic.model_validate(r) for r in rows]
```

- [ ] **Step 3:** Commit

```bash
git add apps/api/src/cloude_api/api/me.py apps/api/src/cloude_api/api/device_profiles.py
git commit -m "feat(api): /me + /device-profiles routes"
```

---

## Task 19: Proxies router (CRUD with encrypted password) + unit test

**Files:**
- Create: `apps/api/src/cloude_api/api/proxies.py`
- Create: `apps/api/tests/unit/test_proxies.py`

- [ ] **Step 1:** Write `api/proxies.py`

```python
"""Proxy CRUD. Passwords encrypted at rest with libsodium sealed box."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.core.encryption import encrypt_password
from cloude_api.models.proxy import Proxy
from cloude_api.schemas.proxy import ProxyCreate, ProxyPublic

router = APIRouter(prefix="/proxies", tags=["proxies"])


def _to_public(p: Proxy) -> ProxyPublic:
    return ProxyPublic(
        id=p.id,
        label=p.label,
        type=p.type,
        host=p.host,
        port=p.port,
        username=p.username,
        has_password=bool(p.password_encrypted),
        created_at=p.created_at,
    )


@router.post("", response_model=ProxyPublic, status_code=status.HTTP_201_CREATED)
async def create_proxy(body: ProxyCreate, current: CurrentUser, db: DbSession) -> ProxyPublic:
    s = get_settings()
    enc = encrypt_password(body.password or "", pub_b64=s.encryption_public_key) if body.password else None
    p = Proxy(
        id=uuid.uuid4(),
        user_id=current.id,
        label=body.label,
        type=body.type,
        host=body.host,
        port=body.port,
        username=body.username,
        password_encrypted=enc,
    )
    db.add(p)
    await db.flush()
    await write_audit(db, user_id=current.id, action="proxy.create", target_id=p.id)
    await db.commit()
    await db.refresh(p)
    return _to_public(p)


@router.get("", response_model=list[ProxyPublic])
async def list_proxies(current: CurrentUser, db: DbSession) -> list[ProxyPublic]:
    rows = (
        await db.scalars(
            select(Proxy).where(Proxy.user_id == current.id).order_by(Proxy.created_at.desc())
        )
    ).all()
    return [_to_public(p) for p in rows]


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(proxy_id: uuid.UUID, current: CurrentUser, db: DbSession) -> None:
    p = await db.scalar(select(Proxy).where(Proxy.id == proxy_id, Proxy.user_id == current.id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="proxy not found")
    await db.delete(p)
    await write_audit(db, user_id=current.id, action="proxy.delete", target_id=p.id)
    await db.commit()
```

- [ ] **Step 2:** Write the unit test

`apps/api/tests/unit/test_proxies.py`:

```python
"""Unit-level test of proxy serialization helper.

End-to-end CRUD is covered by the integration test (Task 30+). Here we just
prove the to-public mapper masks passwords correctly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from cloude_api.api.proxies import _to_public
from cloude_api.enums import ProxyType
from cloude_api.models.proxy import Proxy


def _make(password: bytes | None) -> Proxy:
    p = Proxy(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        label="t",
        type=ProxyType.socks5,
        host="h",
        port=1080,
        username="u",
        password_encrypted=password,
    )
    p.created_at = datetime.now(tz=timezone.utc)
    return p


def test_to_public_marks_has_password_true_when_bytes_present() -> None:
    out = _to_public(_make(b"\x00\x01\x02"))
    assert out.has_password is True


def test_to_public_marks_has_password_false_when_none() -> None:
    out = _to_public(_make(None))
    assert out.has_password is False
    assert "password" not in out.model_dump()  # password never serialized
```

- [ ] **Step 3:** Run

```bash
cd apps/api && pytest tests/unit/test_proxies.py -v
```

Expected: `2 passed`.

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/api/proxies.py apps/api/tests/unit/test_proxies.py
git commit -m "feat(api): /proxies CRUD with encrypted password"
```

---

## Task 20: Devices router (CRUD + start/stop + adb-info + stream-token)

**Files:**
- Create: `apps/api/src/cloude_api/api/devices.py`
- Create: `apps/api/tests/unit/test_devices.py`

- [ ] **Step 1:** Write `api/devices.py`

```python
"""Device CRUD + state transitions. Lifecycle work is enqueued to arq."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.core.stream_token import issue as issue_stream_token
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.proxy import Proxy
from cloude_api.schemas.device import (
    AdbInfo,
    DeviceCreate,
    DevicePublic,
    StreamTokenResponse,
)

router = APIRouter(prefix="/devices", tags=["devices"])


async def _enqueue_create(device_id: uuid.UUID) -> None:
    s = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    try:
        await pool.enqueue_job("create_device_stub", str(device_id))
    finally:
        await pool.aclose()


@router.post("", response_model=DevicePublic, status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate, current: CurrentUser, db: DbSession
) -> DevicePublic:
    profile = await db.scalar(select(DeviceProfile).where(DeviceProfile.id == body.profile_id))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if not profile.is_public and profile.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="profile not visible")

    if body.proxy_id is not None:
        proxy = await db.scalar(
            select(Proxy).where(Proxy.id == body.proxy_id, Proxy.user_id == current.id)
        )
        if proxy is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="proxy not found")

    # Quota: count non-deleted devices
    active = (
        await db.scalars(
            select(Device).where(
                Device.user_id == current.id,
                Device.state.notin_([DeviceState.deleted, DeviceState.stopped]),
            )
        )
    ).all()
    if len(active) >= current.quota_instances:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail="quota exceeded")

    d = Device(
        id=uuid.uuid4(),
        user_id=current.id,
        name=body.name,
        profile_id=body.profile_id,
        proxy_id=body.proxy_id,
        state=DeviceState.creating,
    )
    db.add(d)
    await db.flush()
    await write_audit(db, user_id=current.id, action="device.create", target_id=d.id)
    await db.commit()
    await db.refresh(d)

    await _enqueue_create(d.id)
    return DevicePublic.model_validate(d)


@router.get("", response_model=list[DevicePublic])
async def list_devices(current: CurrentUser, db: DbSession) -> list[DevicePublic]:
    rows = (
        await db.scalars(
            select(Device)
            .where(Device.user_id == current.id, Device.state != DeviceState.deleted)
            .order_by(Device.created_at.desc())
        )
    ).all()
    return [DevicePublic.model_validate(r) for r in rows]


async def _get_owned(db: DbSession, device_id: uuid.UUID, user_id: uuid.UUID) -> Device:
    d = await db.scalar(
        select(Device).where(Device.id == device_id, Device.user_id == user_id)
    )
    if d is None or d.state == DeviceState.deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="device not found")
    return d


@router.get("/{device_id}", response_model=DevicePublic)
async def get_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    return DevicePublic.model_validate(d)


@router.post("/{device_id}/start", response_model=DevicePublic)
async def start_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.stopped, DeviceState.error):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot start from {d.state.value}")
    d.state = DeviceState.creating  # re-enter creating; worker re-runs spawn job
    d.state_reason = None
    await write_audit(db, user_id=current.id, action="device.start", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    await _enqueue_create(d.id)
    return DevicePublic.model_validate(d)


@router.post("/{device_id}/stop", response_model=DevicePublic)
async def stop_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.running, DeviceState.creating):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot stop from {d.state.value}")
    d.state = DeviceState.stopped
    d.stopped_at = datetime.now(tz=timezone.utc)
    await write_audit(db, user_id=current.id, action="device.stop", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    return DevicePublic.model_validate(d)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> None:
    d = await _get_owned(db, device_id, current.id)
    d.state = DeviceState.deleted
    d.stopped_at = d.stopped_at or datetime.now(tz=timezone.utc)
    await write_audit(db, user_id=current.id, action="device.delete", target_id=d.id)
    await db.commit()


@router.get("/{device_id}/stream-token", response_model=StreamTokenResponse)
async def get_stream_token(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> StreamTokenResponse:
    d = await _get_owned(db, device_id, current.id)
    if d.state != DeviceState.running:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="device not running")
    s = get_settings()
    return StreamTokenResponse(
        token=issue_stream_token(str(d.id)),
        ttl_seconds=s.stream_token_ttl_seconds,
    )


@router.get("/{device_id}/adb-info", response_model=AdbInfo)
async def get_adb_info(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> AdbInfo:
    d = await _get_owned(db, device_id, current.id)
    if d.state != DeviceState.running or d.adb_host_port is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="device not running with adb port")
    # P1a placeholder. P2 swaps to PUBLIC_HOST env so external clients can connect.
    host = "localhost"
    return AdbInfo(
        host=host,
        port=d.adb_host_port,
        command=f"adb connect {host}:{d.adb_host_port}",
    )
```

- [ ] **Step 2:** Write the unit test

`apps/api/tests/unit/test_devices.py`:

```python
"""Pure-logic tests for device router helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    d.created_at = datetime.now(tz=timezone.utc)
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
```

- [ ] **Step 3:** Run

```bash
cd apps/api && pytest tests/unit/test_devices.py -v
```

Expected: `2 passed`.

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/api/devices.py apps/api/tests/unit/test_devices.py
git commit -m "feat(api): /devices CRUD + start/stop + stream-token + adb-info"
```

---

## Task 21: Aggregator router + WebSocket pubsub + status WS

**Files:**
- Create: `apps/api/src/cloude_api/api/router.py`
- Create: `apps/api/src/cloude_api/ws/__init__.py`
- Create: `apps/api/src/cloude_api/ws/pubsub.py`
- Create: `apps/api/src/cloude_api/ws/status.py`

- [ ] **Step 1:** Write `api/router.py`

```python
"""Mount all v1 routers under /api/v1."""
from __future__ import annotations

from fastapi import APIRouter

from cloude_api.api import auth, device_profiles, devices, me, proxies

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(me.router)
api_v1.include_router(device_profiles.router)
api_v1.include_router(proxies.router)
api_v1.include_router(devices.router)
```

- [ ] **Step 2:** Write `ws/__init__.py`

```python
"""WebSocket handlers + Redis pub/sub fan-out."""
```

- [ ] **Step 3:** Write `ws/pubsub.py`

```python
"""Publish + subscribe helpers for `ws:device:{id}` channel."""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis


def channel_for(device_id: str) -> str:
    return f"ws:device:{device_id}"


async def publish_status(redis: aioredis.Redis, device_id: str, payload: dict[str, Any]) -> int:
    return int(await redis.publish(channel_for(device_id), json.dumps(payload)))
```

- [ ] **Step 4:** Write `ws/status.py`

```python
"""WS /ws/devices/{id}/status — push state transitions to dashboard."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select

from cloude_api.core import security
from cloude_api.core.deps import get_redis
from cloude_api.db import async_session_factory
from cloude_api.models.device import Device
from cloude_api.ws.pubsub import channel_for

router = APIRouter()


async def _authenticate(token: str) -> uuid.UUID:
    payload = security.decode_token(token)
    if payload.get("type") != security.ACCESS_TOKEN_TYPE:
        raise JWTError("not an access token")
    return uuid.UUID(payload["sub"])


@router.websocket("/ws/devices/{device_id}/status")
async def device_status_ws(
    ws: WebSocket, device_id: uuid.UUID, token: str = Query(...)
) -> None:
    try:
        user_id = await _authenticate(token)
    except (JWTError, ValueError, KeyError):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with async_session_factory() as db:
        d = await db.scalar(
            select(Device).where(Device.id == device_id, Device.user_id == user_id)
        )
        if d is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        # Push current snapshot first
        await ws.send_json({
            "device_id": str(d.id),
            "state": d.state.value,
            "state_reason": d.state_reason,
            "adb_host_port": d.adb_host_port,
        })

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_for(str(device_id)))
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if msg is None:
                # Heartbeat to keep connection alive
                await ws.send_json({"heartbeat": True})
                continue
            data = msg["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await ws.send_text(data)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(channel_for(str(device_id)))
        await pubsub.aclose()
```

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/api/router.py apps/api/src/cloude_api/ws/
git commit -m "feat(api): /api/v1 aggregator + /ws/devices/{id}/status"
```

---

## Task 22: arq worker scaffold + stub `create_device_stub`

**Files:**
- Create: `apps/api/src/cloude_api/workers/__init__.py`
- Create: `apps/api/src/cloude_api/workers/tasks.py`
- Create: `apps/api/src/cloude_api/workers/arq_settings.py`

- [ ] **Step 1:** Write `workers/__init__.py`

```python
"""arq worker tasks + settings."""
```

- [ ] **Step 2:** Write `workers/tasks.py`

```python
"""Background tasks. P1a only ships a stub for create_device.

P1b replaces `create_device_stub` with the real Docker SDK spawn flow:
allocate ADB port, render proxy creds, spawn sidecar, spawn redroid,
poll boot-complete, update DB, publish state. For now we prove the
queue + state-transition + pub/sub fan-out works end-to-end.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

import redis.asyncio as aioredis

from cloude_api.config import get_settings
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker")


async def _publish(redis: aioredis.Redis, device_id: str, payload: dict[str, Any]) -> None:
    await redis.publish(channel_for(device_id), json.dumps(payload))


async def create_device_stub(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """Pretend to spawn a device. Sleeps, then flips creating → running.

    Real implementation lands in P1b. The contract here:
      * If device is in `creating` state, transition to `running`.
      * If device is in any other state, no-op (idempotent retry safe).
      * Always publish state to ws channel.
    """
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    settle_seconds = float(ctx.get("settle_seconds", 2.0))

    log.info("create_device_stub start device_id=%s", device_id)
    await asyncio.sleep(settle_seconds)

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            log.warning("device %s gone before stub completed", device_id)
            return {"ok": False, "reason": "device_missing"}
        if d.state != DeviceState.creating:
            log.info("device %s in state %s; stub no-op", device_id, d.state)
            return {"ok": True, "noop": True, "state": d.state.value}

        d.state = DeviceState.running
        d.started_at = datetime.now(tz=timezone.utc)
        d.adb_host_port = random.randint(40000, 49999)  # P1b: real port allocator + actual binding
        d.redroid_container_id = f"stub-redroid-{device_id.hex[:12]}"
        d.sidecar_container_id = f"stub-sidecar-{device_id.hex[:12]}"
        await db.commit()
        await db.refresh(d)

        await _publish(
            redis,
            str(device_id),
            {
                "device_id": str(device_id),
                "state": d.state.value,
                "state_reason": None,
                "adb_host_port": d.adb_host_port,
            },
        )
    log.info("create_device_stub done device_id=%s", device_id)
    return {"ok": True, "state": "running"}


async def _on_startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    ctx["redis"] = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    log.info("worker startup: redis=%s", s.redis_url)


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    redis: aioredis.Redis | None = ctx.get("redis")
    if redis is not None:
        await redis.aclose()
```

- [ ] **Step 3:** Write `workers/arq_settings.py`

```python
"""arq WorkerSettings — picked up by `arq cloude_api.workers.arq_settings.WorkerSettings`."""
from __future__ import annotations

from arq.connections import RedisSettings

from cloude_api.config import get_settings
from cloude_api.workers.tasks import _on_shutdown, _on_startup, create_device_stub


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [create_device_stub]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 120
```

- [ ] **Step 4:** Commit

```bash
git add apps/api/src/cloude_api/workers/
git commit -m "feat(worker): arq scaffold + create_device_stub job"
```

---

## Task 23: FastAPI `main.py` (assemble app, lifespan, exception handlers, CORS)

**Files:**
- Create: `apps/api/src/cloude_api/main.py`

- [ ] **Step 1:** Write `main.py`

```python
"""ASGI entrypoint. Run via: `uvicorn cloude_api.main:app`."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloude_api.api.router import api_v1
from cloude_api.config import get_settings
from cloude_api.core.deps import close_redis
from cloude_api.core.rate_limit import limiter
from cloude_api.schemas.error import ErrorBody, ErrorEnvelope
from cloude_api.ws.status import router as ws_status_router

log = logging.getLogger("cloude.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info("api startup environment=%s", get_settings().environment)
    yield
    await close_redis()
    log.info("api shutdown")


app = FastAPI(
    title="Cloude Phone API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.state.limiter = limiter
app.include_router(api_v1)
app.include_router(ws_status_router)


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details)).model_dump()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "bad_request", 401: "unauthorized", 402: "payment_required",
        403: "forbidden", 404: "not_found", 409: "conflict", 410: "gone",
        429: "rate_limited", 500: "internal_error",
    }
    code = code_map.get(exc.status_code, "error")
    detail_obj = exc.detail if isinstance(exc.detail, dict) else None
    msg = str(exc.detail) if not isinstance(exc.detail, dict) else code
    return JSONResponse(status_code=exc.status_code, content=_envelope(code, msg, detail_obj))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope("validation_error", "request validation failed", {"errors": exc.errors()}),
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=_envelope("rate_limited", "too many requests", {"limit": str(exc.detail)}),
    )


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 2:** Bring it up locally with compose

```bash
cd /e/cloude-phone && \
  cp .env.example .env && \
  python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env && \
  python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env && \
  python apps/api/src/cloude_api/core/encryption.py keygen >> .env

# Ensure DATABASE_URL host=postgres for in-compose; use localhost only when running tools from host
docker compose up -d --build
docker compose ps
```

Expected: 4 services up, all `healthy` or running.

- [ ] **Step 3:** Run migrations inside the api container

```bash
docker compose exec api alembic upgrade head
```

Expected: migration `0001` applies; subsequent runs print `Will assume non-transactional DDL.` and exit clean.

- [ ] **Step 4:** Smoke

```bash
curl -fsS http://localhost:8000/healthz
```

Expected: `{"status":"ok"}`.

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/main.py
git commit -m "feat(api): FastAPI main app, lifespan, error envelopes, /healthz"
```

---

## Task 24: Seed script for device profiles

**Files:**
- Create: `apps/api/scripts/seed_profiles.py`

- [ ] **Step 1:** Write the seed script

```python
"""Seed the 6 public device profiles. Idempotent: skips if name already exists."""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from cloude_api.db import async_session_factory
from cloude_api.models.device_profile import DeviceProfile

PROFILES: list[dict[str, object]] = [
    {
        "name": "Pixel 5 (1080×2340)",
        "screen_width": 1080, "screen_height": 2340, "screen_dpi": 440,
        "ram_mb": 4096, "cpu_cores": 4,
        "manufacturer": "Google", "model": "Pixel 5",
    },
    {
        "name": "Pixel 7 (1080×2400)",
        "screen_width": 1080, "screen_height": 2400, "screen_dpi": 420,
        "ram_mb": 6144, "cpu_cores": 4,
        "manufacturer": "Google", "model": "Pixel 7",
    },
    {
        "name": "Galaxy A53 (1080×2400)",
        "screen_width": 1080, "screen_height": 2400, "screen_dpi": 405,
        "ram_mb": 4096, "cpu_cores": 4,
        "manufacturer": "Samsung", "model": "SM-A536U",
    },
    {
        "name": "Low-end 720p",
        "screen_width": 720, "screen_height": 1600, "screen_dpi": 320,
        "ram_mb": 2048, "cpu_cores": 2,
        "manufacturer": "Generic", "model": "Generic-720p",
    },
    {
        "name": "Tablet 1200×1920",
        "screen_width": 1200, "screen_height": 1920, "screen_dpi": 240,
        "ram_mb": 4096, "cpu_cores": 4,
        "manufacturer": "Generic", "model": "Tablet-10",
    },
    {
        "name": "Small phone 720×1280",
        "screen_width": 720, "screen_height": 1280, "screen_dpi": 320,
        "ram_mb": 2048, "cpu_cores": 2,
        "manufacturer": "Generic", "model": "Compact",
    },
]


async def main() -> None:
    async with async_session_factory() as db:
        for spec in PROFILES:
            name = spec["name"]
            assert isinstance(name, str)
            existing = await db.scalar(select(DeviceProfile).where(DeviceProfile.name == name))
            if existing is not None:
                print(f"skip (exists): {name}")
                continue
            db.add(
                DeviceProfile(
                    id=uuid.uuid4(),
                    android_version="11",
                    is_public=True,
                    **spec,  # type: ignore[arg-type]
                )
            )
            print(f"add: {name}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2:** Run

```bash
docker compose exec api python scripts/seed_profiles.py
```

Expected: six `add: ...` lines on first run; six `skip (exists)` on second run.

- [ ] **Step 3:** Commit

```bash
git add apps/api/scripts/seed_profiles.py
git commit -m "feat(api): seed_profiles.py — 6 public device profiles"
```

---

## Task 25: Make-invite CLI

**Files:**
- Create: `apps/api/scripts/make_invite.py`

- [ ] **Step 1:** Write the CLI

```python
"""Mint an invite. Prints the raw token (store nowhere — give it to the user once).

Usage examples:
  python scripts/make_invite.py --role admin --ttl-hours 48
  python scripts/make_invite.py --email new@user.com --role user
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from cloude_api.core.auth import generate_invite_token, hash_invite_token
from cloude_api.db import async_session_factory
from cloude_api.enums import UserRole
from cloude_api.models.invite import Invite


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mint a single-use invite token.")
    p.add_argument("--email", default=None, help="Optional pre-bind to this email.")
    p.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.user.value)
    p.add_argument("--ttl-hours", type=int, default=72)
    return p.parse_args()


async def main() -> None:
    args = _parse()
    raw = generate_invite_token()
    invite = Invite(
        id=uuid.uuid4(),
        token_hash=hash_invite_token(raw),
        email=args.email,
        role=UserRole(args.role),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=args.ttl_hours),
    )
    async with async_session_factory() as db:
        db.add(invite)
        await db.commit()
    print("Invite minted.")
    print(f"  id:         {invite.id}")
    print(f"  email:      {args.email or '(any)'}")
    print(f"  role:       {args.role}")
    print(f"  expires_at: {invite.expires_at.isoformat()}")
    print("")
    print(f"  token:  {raw}")
    print("")
    print("Give the user this curl to redeem:")
    print(f'  curl -X POST http://localhost:8000/api/v1/auth/redeem-invite \\')
    print(f'    -H "content-type: application/json" \\')
    print(f"    -d '{{\"token\":\"{raw}\",\"email\":\"USER@EXAMPLE.COM\",\"password\":\"choose-strong-pw\"}}'")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2:** Run smoke

```bash
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 1
```

Expected: prints invite details + token + curl example.

- [ ] **Step 3:** Commit

```bash
git add apps/api/scripts/make_invite.py
git commit -m "feat(api): make_invite.py CLI"
```

---

## Task 26: Manual end-to-end smoke (no test, just verification)

**Files:** none

- [ ] **Step 1:** Mint an admin invite

```bash
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24
# Note: copy the token printed.
```

- [ ] **Step 2:** Redeem it

```bash
TOKEN="paste-token-here"
curl -fsS -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H "content-type: application/json" \
  -d "{\"token\":\"$TOKEN\",\"email\":\"admin@example.com\",\"password\":\"correct horse battery staple\"}"
```

Expected: `{"access":"...","refresh":"...","token_type":"bearer"}`.

- [ ] **Step 3:** Login

```bash
curl -fsS -X POST http://localhost:8000/api/v1/auth/login \
  -H "content-type: application/json" \
  -d '{"email":"admin@example.com","password":"correct horse battery staple"}'
```

Expected: token pair.

- [ ] **Step 4:** Hit /me

```bash
ACCESS="paste-access-here"
curl -fsS http://localhost:8000/api/v1/me -H "authorization: Bearer $ACCESS"
```

Expected: `{"id":"...","email":"admin@example.com","role":"admin","quota_instances":3,...}`.

- [ ] **Step 5:** List profiles (after seed)

```bash
curl -fsS http://localhost:8000/api/v1/device-profiles -H "authorization: Bearer $ACCESS" | python -m json.tool | head -50
```

Expected: array of 6 profiles.

- [ ] **Step 6:** Create a device + watch state transition

```bash
PROFILE_ID=$(curl -fsS http://localhost:8000/api/v1/device-profiles -H "authorization: Bearer $ACCESS" | python -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")
curl -fsS -X POST http://localhost:8000/api/v1/devices \
  -H "authorization: Bearer $ACCESS" -H "content-type: application/json" \
  -d "{\"name\":\"smoke-test\",\"profile_id\":\"$PROFILE_ID\"}"
# returns: { ..., "state":"creating", ... }

# Within ~3 s, the worker stub flips it:
sleep 4
curl -fsS http://localhost:8000/api/v1/devices -H "authorization: Bearer $ACCESS" | python -m json.tool
# state should now be "running" with adb_host_port set
```

Expected: device row state goes `creating` → `running`. If still `creating`, check `docker compose logs worker`.

- [ ] **Step 7:** No commit needed — this is verification only.

---

## Task 27: Integration test (invite → redeem → create-device → worker stub → running)

**Files:**
- Create: `apps/api/tests/integration/test_e2e_invite_to_running.py`

- [ ] **Step 1:** Write the integration test (skipped unless services are up + env points at them)

```python
"""End-to-end smoke. Requires: `docker compose up -d postgres redis`
and migrations applied. Run with: `pytest -m integration tests/integration`.

The test:
  1. Mints an invite directly in DB.
  2. Redeems via HTTP.
  3. Logs in.
  4. Creates a device.
  5. Manually invokes the worker stub (we don't run a real arq worker here;
     calling the function directly with an in-memory ctx is enough to prove
     the state-transition + pub/sub contract).
  6. Asserts state is `running` and adb_host_port is set.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.auth import generate_invite_token, hash_invite_token
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState, UserRole
from cloude_api.main import app
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.invite import Invite
from cloude_api.workers.tasks import create_device_stub


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


@pytest.fixture
async def seed_profile() -> DeviceProfile:
    async with async_session_factory() as db:
        prof = DeviceProfile(
            id=uuid.uuid4(),
            name=f"int-test-{uuid.uuid4().hex[:6]}",
            screen_width=1080, screen_height=2340, screen_dpi=440,
            ram_mb=4096, cpu_cores=4,
            manufacturer="Google", model="Pixel 5",
            is_public=True,
        )
        db.add(prof)
        await db.commit()
        await db.refresh(prof)
        return prof


async def test_invite_to_running_smoke(client: AsyncClient, seed_profile: DeviceProfile) -> None:
    if not os.environ.get("INTEGRATION") and not os.environ.get("PYTEST_INTEGRATION"):
        pytest.skip("set INTEGRATION=1 to run integration tests")

    raw = generate_invite_token()
    async with async_session_factory() as db:
        db.add(
            Invite(
                id=uuid.uuid4(),
                token_hash=hash_invite_token(raw),
                email=None,
                role=UserRole.user,
                expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
            )
        )
        await db.commit()

    email = f"int-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/v1/auth/redeem-invite",
        json={"token": raw, "email": email, "password": "password-1234"},
    )
    assert r.status_code == 201, r.text
    access = r.json()["access"]
    auth = {"authorization": f"Bearer {access}"}

    r = await client.post(
        "/api/v1/devices",
        headers=auth,
        json={"name": "smoke", "profile_id": str(seed_profile.id)},
    )
    assert r.status_code == 201, r.text
    device_id = uuid.UUID(r.json()["id"])
    assert r.json()["state"] == "creating"

    # Manually drive the worker (we don't run an arq subprocess in tests).
    s = get_settings()
    redis = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    try:
        result = await create_device_stub({"redis": redis, "settle_seconds": 0.1}, str(device_id))
    finally:
        await redis.aclose()
    assert result["ok"] is True
    assert result.get("state") == "running"

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        assert d is not None
        assert d.state == DeviceState.running
        assert d.adb_host_port is not None
        assert 40000 <= d.adb_host_port <= 49999
        assert d.started_at is not None

    r = await client.get(f"/api/v1/devices/{device_id}/adb-info", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "localhost"
    assert body["port"] == d.adb_host_port
    assert body["command"].startswith("adb connect localhost:")
```

- [ ] **Step 2:** Run with services up

```bash
cd /e/cloude-phone && docker compose up -d postgres redis
# Apply migrations once
DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude \
  bash -c "cd apps/api && alembic upgrade head"

# Run integration tests
cd apps/api && \
  DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude \
  REDIS_URL=redis://localhost:6379/0 \
  INTEGRATION=1 \
  pytest tests/integration -v
```

Expected: `1 passed`.

- [ ] **Step 3:** Commit

```bash
git add apps/api/tests/integration/test_e2e_invite_to_running.py
git commit -m "test(api): e2e invite→redeem→create→worker-stub→running"
```

---

## Task 28: Lint, format, mypy clean

**Files:** none new — fix any errors found

- [ ] **Step 1:** Ruff lint

```bash
cd apps/api && ruff check src tests scripts
```

Expected: `All checks passed!`. If errors: fix them, then re-run.

- [ ] **Step 2:** Ruff format check

```bash
cd apps/api && ruff format --check src tests scripts
```

Expected: `n files already formatted`. If reformat needed: `ruff format src tests scripts`.

- [ ] **Step 3:** mypy strict

```bash
cd apps/api && mypy --strict src
```

Expected: `Success: no issues found in N source files`.

- [ ] **Step 4:** Full test sweep

```bash
cd apps/api && pytest -v
```

Expected: all unit tests pass; integration test SKIPS without `INTEGRATION=1` set.

- [ ] **Step 5:** If any fixups: commit

```bash
git add -A
git commit -m "chore(api): lint + format + mypy clean"
```

---

## Task 29: GitHub Actions CI

**Files:**
- Create: `.github/workflows/api-ci.yml`

- [ ] **Step 1:** Make `.github/workflows/`

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2:** Write the workflow

```yaml
name: api-ci

on:
  push:
    branches: [main]
    paths:
      - "apps/api/**"
      - ".github/workflows/api-ci.yml"
  pull_request:
    paths:
      - "apps/api/**"
      - ".github/workflows/api-ci.yml"

jobs:
  lint-type-test:
    runs-on: ubuntu-22.04
    timeout-minutes: 15

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: cloude
          POSTGRES_PASSWORD: changeme_local_dev
          POSTGRES_DB: cloude
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U cloude -d cloude"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10

    env:
      DATABASE_URL: postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude
      REDIS_URL: redis://localhost:6379/0
      JWT_SECRET: ci-secret-ci-secret-ci-secret-ci-secret-ci-secret-ci-secret-AAAA
      STREAM_TOKEN_SECRET: ci-stream-ci-stream-ci-stream-ci-stream-ci-stream-AAAA
      ENCRYPTION_PUBLIC_KEY: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
      ENCRYPTION_PRIVATE_KEY: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
      ENVIRONMENT: ci

    defaults:
      run:
        working-directory: apps/api

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Generate real encryption keypair for CI
        run: |
          python -m cloude_api.core.encryption keygen >> $GITHUB_ENV

      - name: Ruff lint
        run: ruff check src tests scripts

      - name: Ruff format check
        run: ruff format --check src tests scripts

      - name: mypy --strict
        run: mypy --strict src

      - name: Alembic upgrade
        run: alembic upgrade head

      - name: pytest (unit)
        run: pytest tests/unit -v

      - name: pytest (integration)
        env:
          INTEGRATION: "1"
        run: pytest tests/integration -v
```

- [ ] **Step 3:** Commit

```bash
git add .github/workflows/api-ci.yml
git commit -m "ci: api lint + mypy + pytest workflow"
```

- [ ] **Step 4:** Push and watch first run go green

```bash
git push origin main
```

Then check the Actions tab on GitHub. Expected: green tick on the next push.

---

## Task 30: README updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Add P1a section before "Phases ahead"

Find the line `## Phases ahead` in `README.md` and immediately before it, insert:

```markdown
## Current phase: P1a (Backend Foundation)

P1a stands up the control plane: FastAPI + arq worker + Postgres 16 + Redis 7 in a single `docker-compose.yml`. JWT auth, invite-only signup, full device CRUD with a stub worker that fakes the spawn (real Docker SDK lands in P1b). No frontend yet.

Full task list: [P1a plan](docs/superpowers/plans/2026-04-25-p1a-backend-foundation.md).

### Bring it up locally

```bash
cp .env.example .env
# Mint secrets
python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
# Generate libsodium keypair
docker compose run --rm api python -m cloude_api.core.encryption keygen >> .env

docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_profiles.py
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24
# copy the printed token, then:
curl -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H 'content-type: application/json' \
  -d '{"token":"<TOKEN>","email":"you@example.com","password":"choose-a-good-one"}'
```

API docs: <http://localhost:8000/api/docs>.
```

- [ ] **Step 2:** Update "Phases ahead" to reflect P1a/b/c/d split

Replace the existing `## Phases ahead` block with:

```markdown
## Phases ahead

- **P1a** (this phase) — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub.
- **P1b** — real Docker SDK device spawn, idle reaper, GC cron.
- **P1c** — Next.js dashboard.
- **P1d** — ws-scrcpy bridge for in-browser streaming.
- **P2** — public signup + Stripe + per-plan quotas.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
```

- [ ] **Step 3:** Commit

```bash
git add README.md
git commit -m "docs: README — P1a quick start + phase breakdown"
```

---

## Task 31: P1a closeout

**Files:** none new — final verification

- [ ] **Step 1:** Full local re-run from scratch

```bash
cd /e/cloude-phone && \
  docker compose down -v && \
  docker compose up -d --build && \
  docker compose exec api alembic upgrade head && \
  docker compose exec api python scripts/seed_profiles.py
```

- [ ] **Step 2:** Run full test suite

```bash
cd apps/api && \
  DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5432/cloude \
  REDIS_URL=redis://localhost:6379/0 \
  INTEGRATION=1 \
  pytest -v
```

Expected: all tests green.

- [ ] **Step 3:** Tag release

```bash
git tag p1a-complete
git push origin p1a-complete
```

- [ ] **Step 4:** Bring services down for cleanup

```bash
docker compose down
```

---

## Completion Criteria

P1a is done when all of the following hold:

1. `docker compose up -d --build` brings `postgres`, `redis`, `api`, `worker` all healthy.
2. `alembic upgrade head` applies cleanly to a fresh DB; 7 tables present.
3. `python scripts/make_invite.py --role admin --ttl-hours 24` mints a working invite.
4. `POST /api/v1/auth/redeem-invite` with that token creates a user + returns a token pair.
5. `POST /api/v1/auth/login` with that user's email/password returns a token pair.
6. `POST /api/v1/auth/refresh` with a refresh token returns a new pair AND fails on second use.
7. `GET /api/v1/me` with the access token returns the user.
8. `GET /api/v1/device-profiles` returns the 6 seeded profiles.
9. `POST /api/v1/proxies` creates a row with `password_encrypted` populated; `GET` lists with `has_password=true`.
10. `POST /api/v1/devices` returns `state="creating"`; within seconds the worker flips it to `running` with `adb_host_port` ∈ [40000, 49999].
11. `GET /api/v1/devices/{id}/adb-info` returns `host="localhost"`, port matching the worker's allocation.
12. `GET /api/v1/devices/{id}/stream-token` returns a 3-segment HMAC token that round-trips through `stream_token.verify()`.
13. `WS /ws/devices/{id}/status?token=<access>` accepts the connection and pushes `{"device_id":..., "state":"running", ...}` after the worker transition.
14. `ruff check`, `ruff format --check`, `mypy --strict` all clean.
15. Unit tests pass; integration test passes with services up + `INTEGRATION=1`.
16. GitHub Actions `api-ci` workflow is green on `main`.
17. Git tag `p1a-complete` pushed.

---

## What's NOT in P1a (deferred — separate plans)

- **P1b** — Real Docker SDK device spawn (replaces `create_device_stub`), ADB port allocator with Redis free-set, sidecar/redroid lifecycle inside the worker, idle reaper cron, stuck-state reaper, GC of `state=stopped > 7 d`, `http-connect` mapping when sidecar receives `type=http`.
- **P1c** — Next.js 14 dashboard (login, device grid, create wizard, proxy CRUD UI, admin user-management).
- **P1d** — ws-scrcpy bridge container + `/ws/devices/{id}/stream` WebSocket proxy + `sessions` row writes + last_ping_at heartbeat.
- **P2** — Stripe billing, public email-verified signup, per-plan quota enforcement, Redis-backed rate limiter, multi-node split.
- **Permanent non-goals** — Magisk, Shamiko, HideMyApplist, Play Integrity bypass (spec §16). Anti-detect framing.

---

## Self-review

Before marking the plan complete, the agent who executes it must check:

1. **Placeholder scan:** grep the diff for `TBD`, `TODO`, `FIXME`, `placeholder`, `XXX`. There should be exactly one acceptable `TODO`-style mention: the `# P1a placeholder` comment in `api/devices.py` `get_adb_info` (deliberate, with rationale and the P2 ticket linked in the doc string above).
2. **Type/method-name consistency:**
   - `verify_password()` defined in Task 11 → used in Task 17 (`/auth/login`).
   - `hash_password()` defined in Task 11 → used in Task 17 (`/auth/redeem-invite`).
   - `create_access_token()` / `create_refresh_token()` / `decode_token()` defined in Task 11 → used in Tasks 17, 16 (`get_current_user`), 21 (WS auth).
   - `encrypt_password()` defined in Task 10 → used in Task 19 (`/proxies`).
   - `issue()` (stream token) defined in Task 12 → imported as `issue_stream_token` in Task 20.
   - `generate_invite_token()` / `hash_invite_token()` defined in Task 15 → used in Tasks 17 (redeem) and 25 (CLI).
   - `is_refresh_revoked()` / `revoke_refresh()` defined in Task 15 → used in Task 17 (`/auth/refresh`).
   - `write_audit()` defined in Task 16 → used in Tasks 17, 19, 20.
   - `metadata_` attr on `AuditLog` (Task 5) ↔ DB column `metadata` (Task 6 migration) ↔ Python attr (Task 16 audit writer).
   - Enum names: `UserRole`, `ProxyType`, `DeviceState` declared once in Task 2, referenced in models (Tasks 3–5), schemas (Tasks 13–14), routes (Tasks 17, 19, 20), workers (Task 22), tests.
3. **Spec coverage** (every IN SCOPE item has a task):
   - FastAPI app → Tasks 0, 23
   - Postgres + Redis services → Task 7
   - api + worker services → Task 9
   - Models (users, device_profiles, proxies, devices, sessions, audit_log + invites) → Tasks 3, 4, 5
   - Single Alembic migration → Task 6
   - JWT (HS256, 15m/30d, rotation via Redis denylist) → Tasks 11, 15, 17
   - argon2id → Task 11
   - Invite-only flow → Tasks 15, 17, 25
   - libsodium sealed-box for proxies → Task 10, 19
   - REST endpoints (login/refresh/redeem-invite/me/profiles/proxies/devices/start/stop/stream-token/adb-info) → Tasks 17, 18, 19, 20
   - WebSocket /ws/devices/{id}/status with Redis pub/sub → Task 21
   - arq worker scaffold + ONE stub job → Task 22
   - Seed script → Task 24
   - CLI scripts (make_invite, seed_profiles) → Tasks 24, 25
   - pytest unit + 1 integration → Tasks 10, 11, 12, 19, 20, 27
   - GitHub Actions CI → Task 29
   - README + .env.example → Tasks 1, 30
4. **Out-of-scope items absent:** No Docker SDK calls in worker (only stub). No idle reaper. No Next.js. No ws-scrcpy bridge. No Stripe. No Magisk/Shamiko.

If any of the above check fails, fix it before declaring P1a's plan ready to execute.

---

*End of P1a plan.*
