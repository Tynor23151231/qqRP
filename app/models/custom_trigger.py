from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CustomTrigger(Base):
    """
    Действие, добавленное самим пользователем через диалог 'Добавить РП'.

    Хранится отдельно от встроенных действий (JSON), чтобы список могли
    расширять пользователи без изменения кода.
    """

    __tablename__ = "custom_triggers"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Слово/фраза после точки, например "выепать" -> команда .выепать
    trigger: Mapped[str] = mapped_column(String(64), index=True)

    # Обычное emoji-представление (fallback, если премиум эмодзи не поддерживается получателем)
    emoji: Mapped[str] = mapped_column(String(16), default="✨")

    # ID премиум (кастомного) эмодзи, если пользователь прислал именно его
    custom_emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Шаблон текста, например: "{user} выебал(а) {target}"
    template: Mapped[str] = mapped_column(String(256))

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="custom_triggers")  # noqa: F821
