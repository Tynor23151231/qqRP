from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_models() -> None:
    """Создаёт таблицы, если их ещё нет (для локальной разработки; в проде — Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
