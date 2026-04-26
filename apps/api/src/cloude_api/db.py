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
