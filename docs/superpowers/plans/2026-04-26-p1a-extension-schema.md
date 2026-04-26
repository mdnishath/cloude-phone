# P1a Extension: Schema Additions for Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the P1a backend foundation with the schema additions required by the 2026-04-26 upgrade design (`snapshots`, `device_files` tables; new columns on `devices`, `proxies`, `invites`). Land these as Alembic migration `0002` plus new SQLAlchemy models so P1b/P1c work can compose against them.

**Architecture:** A second Alembic migration file (`0002_p1a_extension_schema.py`) that:
1. Creates four new native Postgres enums (`image_variant`, `snapshot_kind`, `snapshot_state`, `device_file_op`, `device_file_state`).
2. `ALTER`s the existing `devices`, `proxies`, and `invites` tables to add new columns (all NULL-tolerant or with safe server defaults so the migration is non-blocking even with rows present).
3. `CREATE`s the new `snapshots` and `device_files` tables with their indexes.

Two new SQLAlchemy models (`Snapshot`, `DeviceFile`) follow the same conventions as existing P1a models. Three existing models (`Device`, `Proxy`, `Invite`) gain matching new mapped columns. Tests cover migration upgrade/downgrade and ORM round-trips against a real Postgres (skipped unless `INTEGRATION=1`).

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, asyncpg, Alembic 1.13, pydantic v2, pytest 8 + pytest-asyncio. Same as P1a.

**Design reference:** [`docs/superpowers/specs/2026-04-26-cloud-android-platform-upgrade-design.md`](../specs/2026-04-26-cloud-android-platform-upgrade-design.md) §4 (Data Model Additions) and §13.1 (P1a DoD extension).

**Prerequisites:** All tasks from `2026-04-25-p1a-backend-foundation.md` complete and committed:
- `apps/api/` scaffolded with pyproject + alembic config.
- `apps/api/src/cloude_api/enums.py` exists with `UserRole`, `ProxyType`, `DeviceState`.
- `apps/api/src/cloude_api/models/{base,user,invite,device_profile,proxy,device,session,audit_log}.py` exist.
- `apps/api/alembic/versions/0001_initial_schema.py` exists.
- `apps/api/tests/conftest.py` exists with env defaults for in-process imports.

---

## File Structure (changes from P1a foundation)

```
apps/api/
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py            (existing, untouched)
│       └── 0002_p1a_extension_schema.py      (NEW — Task 7)
├── src/cloude_api/
│   ├── enums.py                              (MODIFY — Task 1)
│   ├── models/
│   │   ├── __init__.py                       (MODIFY — Task 6)
│   │   ├── device.py                         (MODIFY — Task 2)
│   │   ├── proxy.py                          (MODIFY — Task 3)
│   │   ├── invite.py                         (MODIFY — Task 4)
│   │   ├── snapshot.py                       (NEW — Task 5)
│   │   └── device_file.py                    (NEW — Task 5)
│   └── schemas/
│       ├── snapshot.py                       (NEW — Task 9)
│       └── device_file.py                    (NEW — Task 9)
└── tests/
    ├── unit/
    │   └── test_extension_models.py          (NEW — Tasks 2–5, 9)
    └── integration/
        └── test_extension_migration.py       (NEW — Task 8)
```

**Why this layout:**
- One file per ORM model — same convention the rest of P1a uses.
- Tests split by what they exercise: `unit/test_extension_models.py` for things that work without a database (class shape, default values, enum membership); `integration/test_extension_migration.py` for things that need real Postgres.
- Pydantic schemas are split into their own files mirroring the model files; in P1a, REST endpoints for snapshots/device-files don't exist yet, but defining the schemas now keeps imports stable for P1c.

---

## Task 1: Extend `enums.py` with the five new enums

**Files:**
- Modify: `apps/api/src/cloude_api/enums.py`
- Create: `apps/api/tests/unit/test_extension_models.py`

Why first: subsequent ORM models import enum values; tests later assert enum membership.

- [ ] **Step 1:** Write the failing test

Create `apps/api/tests/unit/test_extension_models.py`:

```python
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
```

- [ ] **Step 2:** Run the test to verify it fails

```bash
cd apps/api && pytest tests/unit/test_extension_models.py -v
```

Expected: 5 failures with `ImportError: cannot import name 'ImageVariant' from 'cloude_api.enums'` (and similar for the others).

- [ ] **Step 3:** Add the five enums to `apps/api/src/cloude_api/enums.py`

Append after the existing `DeviceState` enum (do NOT remove existing enums):

```python
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
```

Note the `pre_restore = "pre-restore"` mapping: the Python identifier can't contain a hyphen, but the **string value** (which is what gets stored in Postgres) does. SQLAlchemy's `SAEnum` uses `.value` when binding parameters, so this is correct.

- [ ] **Step 4:** Re-run the test to verify it passes

```bash
cd apps/api && pytest tests/unit/test_extension_models.py -v
```

Expected: 5 passed.

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/enums.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): add ImageVariant + Snapshot + DeviceFile enums"
```

---

## Task 2: Extend the `Device` ORM model

**Files:**
- Modify: `apps/api/src/cloude_api/models/device.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

Why second: the `Snapshot` and `DeviceFile` models foreign-key into `devices`; if Device has typos, downstream tasks fail confusingly.

- [ ] **Step 1:** Add the failing test

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
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
```

- [ ] **Step 2:** Run the test to verify it fails

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_device_model_has_new_columns -v
```

Expected: `AssertionError: 'image_variant' in cols` (the column doesn't exist yet).

- [ ] **Step 3:** Modify `apps/api/src/cloude_api/models/device.py`

The existing imports section already has `Enum as SAEnum`, `ForeignKey`, `Index`, `Integer`, `String`, `Text`, `func`. Add `Boolean`. Add `INET`, `ARRAY` to the postgresql import line. Add `ImageVariant` to the enums import.

Replace the import block at the top:

```python
"""Per-instance device record. State-machine column drives lifecycle."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceState, ImageVariant
from cloude_api.models.base import Base
```

Then, inside the `Device` class — append the new columns AFTER the existing `stopped_at` column and BEFORE the `__table_args__` line:

```python
    # --- P1a extension columns (2026-04-26 upgrade design §4.1) ---
    image_variant: Mapped[ImageVariant] = mapped_column(
        SAEnum(ImageVariant, name="image_variant", create_constraint=False, native_enum=True),
        nullable=False,
        default=ImageVariant.vanilla,
        server_default=ImageVariant.vanilla.value,
    )
    current_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_known_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_known_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    auto_snapshot_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
```

Note the dual `default` (Python-side, used when ORM creates a new row without specifying it) and `server_default` (SQL-side, used by the migration's `ALTER` so existing rows backfill correctly).

- [ ] **Step 4:** Re-run the test to verify it passes

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_device_model_has_new_columns -v
```

Expected: PASS.

- [ ] **Step 5:** Run all unit tests to make sure nothing else broke

```bash
cd apps/api && pytest tests/unit -v
```

Expected: all green (the existing P1a unit tests + the 6 new ones from Task 1 + this one = 7 passed in this file).

- [ ] **Step 6:** Commit

```bash
git add apps/api/src/cloude_api/models/device.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): extend Device model with image_variant + IP cache + tags"
```

---

## Task 3: Extend the `Proxy` ORM model

**Files:**
- Modify: `apps/api/src/cloude_api/models/proxy.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

Adds `session_username_template` (default `'{user}-session-{session}'`, Bright Data convention) and `supports_rotation` (default `TRUE`).

- [ ] **Step 1:** Add the failing test

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
def test_proxy_model_has_new_columns() -> None:
    """Proxy gains session_username_template + supports_rotation."""
    from cloude_api.models.proxy import Proxy

    cols = Proxy.__table__.columns
    assert "session_username_template" in cols
    assert "supports_rotation" in cols

    # Default template matches Bright Data convention
    assert cols["session_username_template"].default.arg == "{user}-session-{session}"
    assert cols["supports_rotation"].default.arg is True
```

- [ ] **Step 2:** Run to verify failure

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_proxy_model_has_new_columns -v
```

Expected: `AssertionError: 'session_username_template' in cols`.

- [ ] **Step 3:** Modify `apps/api/src/cloude_api/models/proxy.py`

Add `Boolean` to the `sqlalchemy` import line. Append columns inside the `Proxy` class AFTER the existing `created_at`:

```python
    # --- P1a extension columns (2026-04-26 upgrade design §4.5) ---
    session_username_template: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="{user}-session-{session}",
        server_default="{user}-session-{session}",
    )
    supports_rotation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
```

The first import line at the top of the file should now read:

```python
from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, LargeBinary, String, func
```

- [ ] **Step 4:** Re-run to verify pass

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_proxy_model_has_new_columns -v
```

Expected: PASS.

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/models/proxy.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): extend Proxy model with session_username_template + supports_rotation"
```

---

## Task 4: Extend the `Invite` ORM model

**Files:**
- Modify: `apps/api/src/cloude_api/models/invite.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

Adds `quota_instances` (the device quota the redeemed user gets — defaults to 3, matches `users.quota_instances` default).

- [ ] **Step 1:** Add the failing test

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
def test_invite_model_has_quota_column() -> None:
    """Invite carries the quota the redeemed user inherits."""
    from cloude_api.models.invite import Invite

    cols = Invite.__table__.columns
    assert "quota_instances" in cols
    assert cols["quota_instances"].default.arg == 3
```

- [ ] **Step 2:** Run to verify failure

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_invite_model_has_quota_column -v
```

Expected: `AssertionError: 'quota_instances' in cols`.

- [ ] **Step 3:** Modify `apps/api/src/cloude_api/models/invite.py`

Ensure `Integer` is in the SQLAlchemy import. Append a column inside the `Invite` class AFTER the existing `created_at`:

```python
    # --- P1a extension column (2026-04-26 upgrade design §4.3) ---
    quota_instances: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
```

If `Integer` isn't yet in the imports, change the import line to:

```python
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, func
```

- [ ] **Step 4:** Re-run to verify pass

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_invite_model_has_quota_column -v
```

Expected: PASS.

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/models/invite.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): extend Invite model with quota_instances"
```

---

## Task 5: Create `Snapshot` and `DeviceFile` ORM models

**Files:**
- Create: `apps/api/src/cloude_api/models/snapshot.py`
- Create: `apps/api/src/cloude_api/models/device_file.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

- [ ] **Step 1:** Add the failing tests

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
def test_snapshot_model_shape() -> None:
    """Snapshot has all columns from design spec §4.2."""
    from cloude_api.models.snapshot import Snapshot

    cols = Snapshot.__table__.columns
    expected = {
        "id", "device_id", "user_id", "name", "kind", "size_bytes",
        "local_path", "s3_key", "state", "error_msg", "created_at",
    }
    assert expected.issubset(set(cols.keys())), (
        f"missing: {expected - set(cols.keys())}"
    )
    # Indexes
    index_names = {idx.name for idx in Snapshot.__table__.indexes}
    assert "ix_snapshots_device_created" in index_names


def test_device_file_model_shape() -> None:
    """DeviceFile has all columns from design spec §4.4."""
    from cloude_api.models.device_file import DeviceFile

    cols = DeviceFile.__table__.columns
    expected = {
        "id", "device_id", "user_id", "op", "filename", "phone_path",
        "size_bytes", "state", "error_msg", "created_at", "completed_at",
    }
    assert expected.issubset(set(cols.keys())), (
        f"missing: {expected - set(cols.keys())}"
    )
```

- [ ] **Step 2:** Run to verify failures

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_snapshot_model_shape tests/unit/test_extension_models.py::test_device_file_model_shape -v
```

Expected: 2 failures with `ModuleNotFoundError: No module named 'cloude_api.models.snapshot'` (and `device_file`).

- [ ] **Step 3:** Create `apps/api/src/cloude_api/models/snapshot.py`

```python
"""Snapshot of a device's /data volume.

A snapshot is a compressed (zstd) tarball stored at ``local_path`` on the
host. ``s3_key`` is populated only when the user has S3/B2 backup enabled
(P1d) and the snapshot has been uploaded.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import SnapshotKind, SnapshotState
from cloude_api.models.base import Base


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[SnapshotKind] = mapped_column(
        SAEnum(SnapshotKind, name="snapshot_kind", create_constraint=False, native_enum=True),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    state: Mapped[SnapshotState] = mapped_column(
        SAEnum(SnapshotState, name="snapshot_state", create_constraint=False, native_enum=True),
        nullable=False,
        default=SnapshotState.creating,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_snapshots_device_created", "device_id", "created_at"),
    )
```

- [ ] **Step 4:** Create `apps/api/src/cloude_api/models/device_file.py`

```python
"""Audit row for an APK install / file push / file pull operation.

This table is *audit only*. It does not store file bytes — uploaded files
live on host disk under /var/lib/cloude-phone/uploads/{user_id}/, with a
24h TTL cleanup cron (P1c). The row records what was attempted, by whom,
when, and the outcome.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceFileOp, DeviceFileState
from cloude_api.models.base import Base


class DeviceFile(Base):
    __tablename__ = "device_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    op: Mapped[DeviceFileOp] = mapped_column(
        SAEnum(DeviceFileOp, name="device_file_op", create_constraint=False, native_enum=True),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state: Mapped[DeviceFileState] = mapped_column(
        SAEnum(DeviceFileState, name="device_file_state", create_constraint=False, native_enum=True),
        nullable=False,
        default=DeviceFileState.pending,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_device_files_device_created", "device_id", "created_at"),
    )
```

- [ ] **Step 5:** Re-run the failing tests

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_snapshot_model_shape tests/unit/test_extension_models.py::test_device_file_model_shape -v
```

Expected: 2 passed.

- [ ] **Step 6:** Commit

```bash
git add apps/api/src/cloude_api/models/snapshot.py apps/api/src/cloude_api/models/device_file.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): add Snapshot + DeviceFile ORM models"
```

---

## Task 6: Re-export new models in `models/__init__.py`

**Files:**
- Modify: `apps/api/src/cloude_api/models/__init__.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

Why this matters: Alembic's `target_metadata = Base.metadata` autogeneration only sees models that have been imported. The existing `models/__init__.py` is the single import surface that pulls every model in.

- [ ] **Step 1:** Add the failing test

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
def test_models_package_exports_new_models() -> None:
    """models/__init__.py must export Snapshot + DeviceFile so Alembic sees them."""
    import cloude_api.models as m

    assert hasattr(m, "Snapshot")
    assert hasattr(m, "DeviceFile")
    assert "Snapshot" in m.__all__
    assert "DeviceFile" in m.__all__
```

- [ ] **Step 2:** Run to verify failure

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_models_package_exports_new_models -v
```

Expected: `AssertionError: hasattr(m, 'Snapshot')`.

- [ ] **Step 3:** Modify `apps/api/src/cloude_api/models/__init__.py`

Replace the file with:

```python
"""Re-export models so Alembic autogenerate sees them all."""
from cloude_api.models.audit_log import AuditLog
from cloude_api.models.base import Base
from cloude_api.models.device import Device
from cloude_api.models.device_file import DeviceFile
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.invite import Invite
from cloude_api.models.proxy import Proxy
from cloude_api.models.session import Session
from cloude_api.models.snapshot import Snapshot
from cloude_api.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Device",
    "DeviceFile",
    "DeviceProfile",
    "Invite",
    "Proxy",
    "Session",
    "Snapshot",
    "User",
]
```

- [ ] **Step 4:** Re-run

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_models_package_exports_new_models -v
```

Expected: PASS.

- [ ] **Step 5:** Run the full unit suite to confirm no regressions

```bash
cd apps/api && pytest tests/unit -v
```

Expected: all green.

- [ ] **Step 6:** Commit

```bash
git add apps/api/src/cloude_api/models/__init__.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): export Snapshot + DeviceFile from models package"
```

---

## Task 7: Write Alembic migration `0002_p1a_extension_schema.py`

**Files:**
- Create: `apps/api/alembic/versions/0002_p1a_extension_schema.py`

This migration is **the** binding contract between the ORM and Postgres for everything this plan adds. It must be writable both forward (`upgrade`) and backward (`downgrade`).

Order of operations matters:
1. Create the new enum types (`CREATE TYPE ...`).
2. Backfill-safe `ALTER TABLE ... ADD COLUMN` on `devices`, `proxies`, `invites`. Each new column is either NOT NULL with a `server_default` (so existing rows fill in) or NULL-allowed.
3. `CREATE TABLE` for `snapshots` and `device_files` and their indexes.

Downgrade reverses the order.

- [ ] **Step 1:** Create the migration file

Create `apps/api/alembic/versions/0002_p1a_extension_schema.py`:

```python
"""P1a extension schema: snapshots, device_files, plus columns on devices/proxies/invites.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reference handles for the new enum types. `create_type=False` because the
# CREATE TYPE statements are emitted explicitly via op.execute() below; this
# matches the pattern used by 0001_initial_schema.py.
image_variant = postgresql.ENUM(
    "vanilla", "daily", name="image_variant", create_type=False,
)
snapshot_kind = postgresql.ENUM(
    "manual", "auto", "pre-restore", name="snapshot_kind", create_type=False,
)
snapshot_state = postgresql.ENUM(
    "creating", "ready", "error", "deleted", name="snapshot_state", create_type=False,
)
device_file_op = postgresql.ENUM(
    "apk_install", "file_push", "file_pull", name="device_file_op", create_type=False,
)
device_file_state = postgresql.ENUM(
    "pending", "running", "done", "error", name="device_file_state", create_type=False,
)


def upgrade() -> None:
    # 1. Create the new enum types
    op.execute("CREATE TYPE image_variant AS ENUM ('vanilla', 'daily')")
    op.execute("CREATE TYPE snapshot_kind AS ENUM ('manual', 'auto', 'pre-restore')")
    op.execute("CREATE TYPE snapshot_state AS ENUM ('creating', 'ready', 'error', 'deleted')")
    op.execute("CREATE TYPE device_file_op AS ENUM ('apk_install', 'file_push', 'file_pull')")
    op.execute("CREATE TYPE device_file_state AS ENUM ('pending', 'running', 'done', 'error')")

    # 2. ALTER existing tables — devices
    op.add_column(
        "devices",
        sa.Column(
            "image_variant", image_variant,
            nullable=False, server_default="vanilla",
        ),
    )
    op.add_column(
        "devices",
        sa.Column("current_session_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_known_ip", postgresql.INET, nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_known_country", sa.String(2), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column(
            "tags", postgresql.ARRAY(sa.String),
            nullable=False, server_default="{}",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "auto_snapshot_enabled", sa.Boolean,
            nullable=False, server_default=sa.text("false"),
        ),
    )

    # 3. ALTER existing tables — proxies
    op.add_column(
        "proxies",
        sa.Column(
            "session_username_template", sa.String(255),
            nullable=False, server_default="{user}-session-{session}",
        ),
    )
    op.add_column(
        "proxies",
        sa.Column(
            "supports_rotation", sa.Boolean,
            nullable=False, server_default=sa.text("true"),
        ),
    )

    # 4. ALTER existing tables — invites
    op.add_column(
        "invites",
        sa.Column(
            "quota_instances", sa.Integer,
            nullable=False, server_default="3",
        ),
    )

    # 5. Create snapshots table
    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", snapshot_kind, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("local_path", sa.String(1024), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=True),
        sa.Column("state", snapshot_state, nullable=False, server_default="creating"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_snapshots_device_created", "snapshots", ["device_id", "created_at"],
    )

    # 6. Create device_files table
    op.create_table(
        "device_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("op", device_file_op, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("phone_path", sa.String(1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("state", device_file_state, nullable=False, server_default="pending"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True,
        ),
    )
    op.create_index(
        "ix_device_files_device_created", "device_files", ["device_id", "created_at"],
    )


def downgrade() -> None:
    # Reverse order of upgrade()
    op.drop_index("ix_device_files_device_created", table_name="device_files")
    op.drop_table("device_files")

    op.drop_index("ix_snapshots_device_created", table_name="snapshots")
    op.drop_table("snapshots")

    op.drop_column("invites", "quota_instances")

    op.drop_column("proxies", "supports_rotation")
    op.drop_column("proxies", "session_username_template")

    op.drop_column("devices", "auto_snapshot_enabled")
    op.drop_column("devices", "tags")
    op.drop_column("devices", "last_known_country")
    op.drop_column("devices", "last_known_ip")
    op.drop_column("devices", "current_session_id")
    op.drop_column("devices", "image_variant")

    op.execute("DROP TYPE device_file_state")
    op.execute("DROP TYPE device_file_op")
    op.execute("DROP TYPE snapshot_state")
    op.execute("DROP TYPE snapshot_kind")
    op.execute("DROP TYPE image_variant")
```

- [ ] **Step 2:** Lint-only sanity check (no DB needed)

```bash
cd apps/api && ruff check alembic/versions/0002_p1a_extension_schema.py
cd apps/api && python -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('m', 'alembic/versions/0002_p1a_extension_schema.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); assert mod.revision == '0002' and mod.down_revision == '0001'; print('migration metadata OK')"
```

Expected:
- ruff prints no errors
- second command prints `migration metadata OK`

- [ ] **Step 3:** Commit

```bash
git add apps/api/alembic/versions/0002_p1a_extension_schema.py
git commit -m "feat(api): alembic 0002 — snapshots + device_files + new columns"
```

---

## Task 8: Integration test — migration up/down + ORM round-trip

**Files:**
- Create: `apps/api/tests/integration/test_extension_migration.py`

This test is the only place where we verify migration `0002` actually runs against real Postgres and the ORM can write/read every new column.

The test pattern follows `2026-04-25-p1a-backend-foundation.md`'s integration tests: skipped unless `INTEGRATION=1` is set; assumes `docker compose up -d postgres redis` has been run.

- [ ] **Step 1:** Write the test

Create `apps/api/tests/integration/test_extension_migration.py`:

```python
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
        ["alembic", *args],
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
        rows = (await db.execute(text(
            "SELECT typname FROM pg_type WHERE typname IN "
            "('image_variant','snapshot_kind','snapshot_state',"
            "'device_file_op','device_file_state')"
        ))).all()
        names = {r[0] for r in rows}
        assert names == {
            "image_variant", "snapshot_kind", "snapshot_state",
            "device_file_op", "device_file_state",
        }


async def test_migration_adds_columns_to_devices() -> None:
    async with async_session_factory() as db:
        rows = (await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='devices'"
        ))).all()
        cols = {r[0] for r in rows}
        for new in (
            "image_variant", "current_session_id", "last_known_ip",
            "last_known_country", "tags", "auto_snapshot_enabled",
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
        loaded_device = (await db.execute(
            select(Device).where(Device.id == device.id)
        )).scalar_one()
        assert loaded_device.image_variant == ImageVariant.daily
        assert loaded_device.tags == ["daily", "test"]
        assert loaded_device.auto_snapshot_enabled is True

        loaded_snap = (await db.execute(
            select(Snapshot).where(Snapshot.id == snapshot.id)
        )).scalar_one()
        assert loaded_snap.kind == SnapshotKind.manual
        assert loaded_snap.state == SnapshotState.ready
        assert loaded_snap.size_bytes == 1234

        loaded_df = (await db.execute(
            select(DeviceFile).where(DeviceFile.id == device_file.id)
        )).scalar_one()
        assert loaded_df.op == DeviceFileOp.apk_install
        assert loaded_df.state == DeviceFileState.done


async def test_invite_quota_instances_default() -> None:
    """Insert an invite without specifying quota_instances → server default 3."""
    async with async_session_factory() as db:
        from datetime import datetime, timedelta, timezone

        admin = User(
            id=uuid.uuid4(),
            email=f"admin-{uuid.uuid4().hex[:8]}@x.test",
            password_hash="x",
            role=UserRole.admin,
        )
        invite = Invite(
            id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by=admin.id,
        )
        db.add_all([admin, invite])
        await db.commit()

        loaded = (await db.execute(
            select(Invite).where(Invite.id == invite.id)
        )).scalar_one()
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

        loaded = (await db.execute(
            select(Proxy).where(Proxy.id == proxy.id)
        )).scalar_one()
        assert loaded.session_username_template == "{user}-session-{session}"
        assert loaded.supports_rotation is True
```

- [ ] **Step 2:** Bring up Postgres + Redis (if not already running)

```bash
docker compose up -d postgres redis
```

Expected: containers running. (If `docker-compose.yml` doesn't exist yet — i.e. you haven't completed P1a Task 0 / docker-compose work — skip Steps 2–4 and run Step 5's full-suite check after P1a is done. Mark this step `(deferred)` in your tracker.)

- [ ] **Step 3:** Run the integration test

```bash
cd apps/api && INTEGRATION=1 pytest tests/integration/test_extension_migration.py -v
```

Expected: 5 passed. (If skipped due to missing `INTEGRATION` env, the test fixture skips at module level.)

- [ ] **Step 4:** Run the migration both directions one more time as a sanity check

```bash
cd apps/api && alembic downgrade base && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

Expected: each command prints alembic's `Running upgrade ...` / `Running downgrade ...` lines and exits 0.

- [ ] **Step 5:** Commit

```bash
git add apps/api/tests/integration/test_extension_migration.py
git commit -m "test(api): integration test for 0002 migration + ORM round-trip"
```

---

## Task 9: Pydantic schemas for `Snapshot` and `DeviceFile`

**Files:**
- Create: `apps/api/src/cloude_api/schemas/snapshot.py`
- Create: `apps/api/src/cloude_api/schemas/device_file.py`
- Modify: `apps/api/tests/unit/test_extension_models.py`

These schemas are not used by any endpoint in P1a — REST endpoints for snapshots and device files land in P1c. We define them now so:
1. P1c plan starts with the wire formats already pinned.
2. The shape of the response is documented alongside the model.
3. We catch any naming inconsistency between the ORM model and the schema before P1c work begins.

Only `Read` (response) schemas in this plan; `Create` schemas land in P1c when the endpoints exist.

- [ ] **Step 1:** Add the failing tests

Append to `apps/api/tests/unit/test_extension_models.py`:

```python
def test_snapshot_read_schema_round_trip() -> None:
    """SnapshotRead pydantic model accepts an ORM-shaped dict."""
    import uuid
    from datetime import datetime, timezone

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
        "created_at": datetime.now(timezone.utc),
    }
    read = SnapshotRead.model_validate(payload)
    assert read.kind == SnapshotKind.manual
    assert read.state == SnapshotState.ready


def test_device_file_read_schema_round_trip() -> None:
    """DeviceFileRead pydantic model accepts an ORM-shaped dict."""
    import uuid
    from datetime import datetime, timezone

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
        "created_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
    }
    read = DeviceFileRead.model_validate(payload)
    assert read.op == DeviceFileOp.apk_install
    assert read.state == DeviceFileState.done
```

- [ ] **Step 2:** Run to verify failure

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_snapshot_read_schema_round_trip tests/unit/test_extension_models.py::test_device_file_read_schema_round_trip -v
```

Expected: 2 failures with `ModuleNotFoundError: No module named 'cloude_api.schemas.snapshot'` (and `device_file`).

- [ ] **Step 3:** Create `apps/api/src/cloude_api/schemas/snapshot.py`

```python
"""Pydantic schemas for Snapshot. Read schema only in P1a — Create lands in P1c."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from cloude_api.enums import SnapshotKind, SnapshotState


class SnapshotRead(BaseModel):
    """Wire format returned by GET /snapshots/{id} and list endpoints (P1c)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    kind: SnapshotKind
    size_bytes: int
    local_path: str
    s3_key: str | None = None
    state: SnapshotState
    error_msg: str | None = None
    created_at: datetime
```

- [ ] **Step 4:** Create `apps/api/src/cloude_api/schemas/device_file.py`

```python
"""Pydantic schemas for DeviceFile. Read schema only in P1a — Create lands in P1c."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from cloude_api.enums import DeviceFileOp, DeviceFileState


class DeviceFileRead(BaseModel):
    """Wire format returned by GET /devices/{id}/files/operations (P1c)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    user_id: uuid.UUID
    op: DeviceFileOp
    filename: str
    phone_path: str | None = None
    size_bytes: int
    state: DeviceFileState
    error_msg: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

- [ ] **Step 5:** Re-run the failing tests

```bash
cd apps/api && pytest tests/unit/test_extension_models.py::test_snapshot_read_schema_round_trip tests/unit/test_extension_models.py::test_device_file_read_schema_round_trip -v
```

Expected: 2 passed.

- [ ] **Step 6:** Commit

```bash
git add apps/api/src/cloude_api/schemas/snapshot.py apps/api/src/cloude_api/schemas/device_file.py apps/api/tests/unit/test_extension_models.py
git commit -m "feat(api): SnapshotRead + DeviceFileRead pydantic schemas"
```

---

## Task 10: Final verification — full test suite + lint + types

**Files:** none modified — purely a verification gate before declaring P1a extension done.

- [ ] **Step 1:** Full unit suite

```bash
cd apps/api && pytest tests/unit -v
```

Expected: all unit tests green, including the 11 new ones from this plan (5 enum tests + 3 model column tests + 1 model package test + 2 schema round-trips).

- [ ] **Step 2:** Integration suite (if Postgres is up)

```bash
cd apps/api && INTEGRATION=1 pytest tests/integration -v
```

Expected: every integration test passes (existing P1a integration test + 5 new from Task 8). If `INTEGRATION` is unset, all integration tests SKIP — that's still a green result.

- [ ] **Step 3:** Lint

```bash
cd apps/api && ruff check .
```

Expected: no errors.

- [ ] **Step 4:** Types

```bash
cd apps/api && mypy --strict src
```

Expected: no errors.

- [ ] **Step 5:** Coverage spot-check

```bash
cd apps/api && pytest --cov=cloude_api --cov-report=term-missing tests/unit
```

Expected: total coverage stays ≥ 70 % (P1a CI target). The new files (`models/snapshot.py`, `models/device_file.py`, `schemas/snapshot.py`, `schemas/device_file.py`) should each show ≥ 80 % covered.

- [ ] **Step 6:** Commit (only if any minor lint/type fixups needed in earlier task files; otherwise skip)

```bash
git status
# If only the .md plan file or no changes are listed, skip the commit.
# If any earlier-task source file shows changes, commit them with:
#   git add <files>
#   git commit -m "fix(api): lint/type cleanup for P1a extension"
```

---

## Definition of Done (P1a extension)

- [ ] All 10 tasks above committed.
- [ ] `pytest tests/unit` green.
- [ ] `INTEGRATION=1 pytest tests/integration` green (when Postgres is up).
- [ ] `ruff check .` clean.
- [ ] `mypy --strict src` clean.
- [ ] `alembic upgrade head` applied cleanly to a fresh DB; `alembic downgrade base` cleans up.
- [ ] Schema as listed in design spec §13.1: tables `snapshots`, `device_files` exist; columns `image_variant`, `current_session_id`, `last_known_ip`, `last_known_country`, `tags`, `auto_snapshot_enabled` on `devices`; `session_username_template`, `supports_rotation` on `proxies`; `quota_instances` on `invites` — verified via the integration test in Task 8.

---

## What this plan deliberately does NOT do

To prevent scope creep, the following are explicitly out of scope and land in later phases:

- ❌ REST endpoints for snapshots, clones, IP rotation, APK install, file transfer — **P1c**.
- ❌ Worker job code for snapshot/restore/clone/ip-rotate/apk-install/file-push — **P1c**.
- ❌ `device-shell-proxy` service — **P1c**.
- ❌ `users.s3_backup_config` and `users.disk_quota_bytes` columns — **P1d** (separate migration `0003`).
- ❌ Daily-life image variant build (`docker/redroid-daily/Dockerfile`) — **P1d**.
- ❌ `Create` pydantic schemas for snapshot/device_file (only `Read` here; `Create` in P1c).
- ❌ Frontend changes — frontend lands across P1b/P1c/P1d per the upgrade design's phase map.

Subsequent plans in this series:
1. `2026-04-26-p1a-extension-schema.md` ← **this plan**
2. `2026-04-2X-p1b-spawn-and-frontend.md` — Docker SDK spawn + ws-scrcpy + minimal frontend (next)
3. `2026-04-2X-p1c-snapshots-and-panel.md` — snapshot subsystem + IP rotation + APK/files + panel UI
4. `2026-04-2X-p1d-daily-image-and-admin.md` — daily-life image + S3 backup + admin features
