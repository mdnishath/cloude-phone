"""Tests for the Redis-backed ADB port allocator."""

from __future__ import annotations

from typing import Any

import pytest

from cloude_api.workers import port_allocator as pa


class FakeRedis:
    """In-memory SET implementation covering only the methods port_allocator uses."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self._sets else 0

    async def sadd(self, key: str, *values: Any) -> int:
        s = self._sets.setdefault(key, set())
        before = len(s)
        for v in values:
            s.add(str(v))
        return len(s) - before

    async def srem(self, key: str, *values: Any) -> int:
        s = self._sets.get(key, set())
        before = len(s)
        for v in values:
            s.discard(str(v))
        return before - len(s)

    async def spop(self, key: str) -> str | None:
        s = self._sets.get(key, set())
        if not s:
            return None
        v = next(iter(s))
        s.discard(v)
        return v

    async def scard(self, key: str) -> int:
        return len(self._sets.get(key, set()))


class FakeDb:
    """Stub of AsyncSession exposing only scalars(...).all() over a list of int|None."""

    def __init__(self, ports: list[int | None]) -> None:
        self._ports = ports

    async def scalars(self, _stmt: Any) -> Any:
        class _Result:
            def __init__(self, items: list[int | None]) -> None:
                self._items = items

            def all(self) -> list[int | None]:
                return list(self._items)

        return _Result(self._ports)


@pytest.mark.asyncio
async def test_initialize_seeds_full_range_on_cold_key() -> None:
    r = FakeRedis()
    db = FakeDb(ports=[])
    await pa.initialize(r, db)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == pa.PORT_POOL_MAX - pa.PORT_POOL_MIN + 1


@pytest.mark.asyncio
async def test_initialize_is_idempotent_when_key_exists() -> None:
    r = FakeRedis()
    # Pre-populate with only two ports — initialize should NOT reseed.
    await r.sadd(pa.PORT_SET_KEY, 40000, 40001)
    db = FakeDb(ports=[])
    await pa.initialize(r, db)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 2


@pytest.mark.asyncio
async def test_initialize_removes_ports_claimed_by_live_devices() -> None:
    r = FakeRedis()
    db = FakeDb(ports=[40005, 40007, None])  # None should be ignored
    await pa.initialize(r, db)  # type: ignore[arg-type]
    # full range minus the two claimed ports
    assert await r.scard(pa.PORT_SET_KEY) == (pa.PORT_POOL_MAX - pa.PORT_POOL_MIN + 1) - 2


@pytest.mark.asyncio
async def test_acquire_returns_an_int_in_range() -> None:
    r = FakeRedis()
    await r.sadd(pa.PORT_SET_KEY, 40123)
    port = await pa.acquire(r)  # type: ignore[arg-type]
    assert port == 40123
    assert pa.PORT_POOL_MIN <= port <= pa.PORT_POOL_MAX


@pytest.mark.asyncio
async def test_acquire_returns_none_on_empty_set() -> None:
    r = FakeRedis()
    port = await pa.acquire(r)  # type: ignore[arg-type]
    assert port is None


@pytest.mark.asyncio
async def test_release_puts_port_back() -> None:
    r = FakeRedis()
    await pa.release(r, 40500)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 1
    got = await pa.acquire(r)  # type: ignore[arg-type]
    assert got == 40500


@pytest.mark.asyncio
async def test_release_is_idempotent() -> None:
    r = FakeRedis()
    await pa.release(r, 40500)  # type: ignore[arg-type]
    await pa.release(r, 40500)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 1
