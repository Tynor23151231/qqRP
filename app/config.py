from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальная конфигурация проекта, читается из переменных окружения / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qqrp_bot"

    # Префикс, с которого начинаются RP-команды (по ТЗ — точка)
    command_prefix: str = "."

    # ID администраторов бота (через запятую в .env), которые могут выдавать/забирать
    # премиум через встроенную админ-консоль (/admin). Пример: ADMIN_IDS=123456789,987654321
    admin_ids_raw: str = Field(default="", validation_alias="ADMIN_IDS")

    # Стоимость и длительность премиум-подписки (Telegram Stars, XTR)
    premium_price_stars: int = 99
    premium_duration_days: int = 30
    basic_premium_price_stars: int = 25
    basic_premium_max_custom_rp: int = 7

    # Обязательная подписка на канал перед использованием бота.
    # chat_id канала/супергруппы (с "-100" префиксом) и публичный username без "@".
    required_channel_id: int = -1003062068266
    required_channel_username: str = "Infoaboutqq"

    # Внешний сервис-проверяльщик подписок (qqkop7555-ops/check на Railway).
    # Если не задан — используем нативную проверку через Bot API (getChatMember).
    checker_url: str | None = None
    checker_api_key: str | None = None
    bot_name: str = "qqRPBot"

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

    @property
    def admin_ids(self) -> list[int]:
        """ADMIN_IDS="123,456" -> [123, 456]. Пустые/некорректные значения игнорируются."""
        ids: list[int] = []
        for chunk in self.admin_ids_raw.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.append(int(chunk))
        return ids

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids


settings = Settings()  # type: ignore[call-arg]

