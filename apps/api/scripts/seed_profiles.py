"""Seed the 6 public device profiles. Idempotent: skips if name already exists."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from cloude_api.db import async_session_factory
from cloude_api.models.device_profile import DeviceProfile

PROFILES: list[dict[str, object]] = [
    {
        "name": "Pixel 5 (1080×2340)",  # noqa: RUF001
        "screen_width": 1080,
        "screen_height": 2340,
        "screen_dpi": 440,
        "ram_mb": 4096,
        "cpu_cores": 4,
        "manufacturer": "Google",
        "model": "Pixel 5",
    },
    {
        "name": "Pixel 7 (1080×2400)",  # noqa: RUF001
        "screen_width": 1080,
        "screen_height": 2400,
        "screen_dpi": 420,
        "ram_mb": 6144,
        "cpu_cores": 4,
        "manufacturer": "Google",
        "model": "Pixel 7",
    },
    {
        "name": "Galaxy A53 (1080×2400)",  # noqa: RUF001
        "screen_width": 1080,
        "screen_height": 2400,
        "screen_dpi": 405,
        "ram_mb": 4096,
        "cpu_cores": 4,
        "manufacturer": "Samsung",
        "model": "SM-A536U",
    },
    {
        "name": "Low-end 720p",
        "screen_width": 720,
        "screen_height": 1600,
        "screen_dpi": 320,
        "ram_mb": 2048,
        "cpu_cores": 2,
        "manufacturer": "Generic",
        "model": "Generic-720p",
    },
    {
        "name": "Tablet 1200×1920",  # noqa: RUF001
        "screen_width": 1200,
        "screen_height": 1920,
        "screen_dpi": 240,
        "ram_mb": 4096,
        "cpu_cores": 4,
        "manufacturer": "Generic",
        "model": "Tablet-10",
    },
    {
        "name": "Small phone 720×1280",  # noqa: RUF001
        "screen_width": 720,
        "screen_height": 1280,
        "screen_dpi": 320,
        "ram_mb": 2048,
        "cpu_cores": 2,
        "manufacturer": "Generic",
        "model": "Compact",
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
