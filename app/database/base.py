from __future__ import annotations

from sqlalchemy import text
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


async def _run_light_migrations() -> None:
    """
    Точечные ALTER TABLE для колонок, добавленных после первого деплоя.
    Полноценного Alembic в проекте нет, поэтому недостающие колонки
    добавляем идемпотентно прямо при старте.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_name VARCHAR(128)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMPTZ")
        )
        await conn.execute(
            text("ALTER TABLE custom_triggers ADD COLUMN IF NOT EXISTS emojis_json TEXT")
        )


async def init_models() -> None:
    """Создаёт таблицы, если их ещё нет (для локальной разработки; в проде — Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_light_migrations()
