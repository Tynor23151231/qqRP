from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class InlineButtonAlert(Base):
    """
    Текст для alert-кнопки, созданной командой ".btn Название | текст" в бизнес-чате.

    callback_data кнопки хранит только "btnalert:<id>" (лимит Bot API — 64 байта),
    а сам текст показа — здесь, потому что он может быть длиннее.
    """

    __tablename__ = "inline_button_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Кто владелец бизнес-аккаунта, создавший кнопку (для возможной будущей чистки/статистики).
    business_connection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    text: Mapped[str] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship()  # noqa: F821
