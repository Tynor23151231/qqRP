from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import Gender


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128))
    custom_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    gender: Mapped[Gender] = mapped_column(default=Gender.UNKNOWN)

    # Business Connection, через которую бот действует от имени пользователя
    business_connection_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Настройки (см. /settings в ТЗ)
    random_animations: Mapped[bool] = mapped_column(Boolean, default=True)
    compact_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    random_templates: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String(8), default="ru")

    registered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Статистика
    total_actions: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Премиум-подписка (платные функции вроде .typing)
    premium_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Реферальная программа: 10 приглашённых (кто дошёл до выбора пола) -> 7 дней премиума
    # + одноразовая скидка 50% на одну покупку. Награда выдаётся один раз (акция одноразовая).
    invited_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    referral_count: Mapped[int] = mapped_column(default=0)
    referral_reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    discount_pending: Mapped[bool] = mapped_column(Boolean, default=False)

    action_logs: Mapped[list["ActionLog"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    custom_triggers: Mapped[list["CustomTrigger"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def is_configured(self) -> bool:
        return self.gender != Gender.UNKNOWN

    @property
    def has_premium(self) -> bool:
        if self.premium_until is None:
            return False
        now = dt.datetime.now(dt.timezone.utc)
        premium_until = self.premium_until
        if premium_until.tzinfo is None:
            premium_until = premium_until.replace(tzinfo=dt.timezone.utc)
        return premium_until > now

    @property
    def display_name(self) -> str:
        return self.custom_name or self.first_name or (self.username and f"@{self.username}") or "Пользователь"
