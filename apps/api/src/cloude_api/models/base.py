"""Declarative base shared by all ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this. Note: SQLAlchemy reserves the attribute
    name ``metadata`` on DeclarativeBase, so any column literally called
    ``metadata`` (e.g. on audit_log) must be mapped via a different Python
    attribute name (we use ``metadata_``)."""
