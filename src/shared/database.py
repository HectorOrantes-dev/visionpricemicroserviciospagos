"""Infraestructura de base de datos (SQLAlchemy async).

Expone el engine, la fábrica de sesiones y la Base declarativa. La dependencia
`get_session` provee una `AsyncSession` por request (patrón unit-of-work).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.shared.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa compartida por todos los modelos ORM."""


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI: abre una sesión por request y la cierra al final."""
    async with SessionLocal() as session:
        yield session
