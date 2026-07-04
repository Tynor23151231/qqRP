from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальная конфигурация проекта, читается из переменных окружения / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qqrp_bot"

    # Префикс, с которого начинаются RP-команды (по ТЗ — точка)
    command_prefix: str = "."

    # Owner / admin telegram id (для служебных команд, если понадобятся)
    admin_id: int | None = None

    # Значения по умолчанию для пользовательских настроек
    default_language: str = "ru"
    log_level: str = "INFO"

    # Railway передаёт порт для веб-сервисов; боту-воркеру он не нужен,
    # но переменная может присутствовать в окружении — не должна ломать чтение конфига.
    port: int = 8080

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """
        Railway Postgres-плагин отдаёт DATABASE_URL как postgres:// или postgresql://
        (синхронный psycopg-стиль). Приводим к schema, которую понимает SQLAlchemy Async + asyncpg.
        """
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value


settings = Settings()  # type: ignore[call-arg]

