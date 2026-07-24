from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

MAX_SCREENS = 6
MAX_BUTTONS_PER_SCREEN = 6


class ButtonFlow(Base):
    """
    Именованная цепочка экранов "текст + кнопки", создаётся через меню "Кнопки".
    Вызывается в бизнес-чате как обычный свой триггер: ".<trigger>".

    screens — список экранов (максимум MAX_SCREENS), каждый экран:
        {
            "text": str,
            "buttons": [
                {"label": str, "type": "url" | "alert" | "next", "payload": str},
                ...
            ],
        }
    Кнопка type="next" ведёт на следующий экран в этом же списке (screens[i+1]);
    на последнем экране кнопок с type="next" быть не может.
    """

    __tablename__ = "button_flows"
    __table_args__ = (UniqueConstraint("owner_id", "trigger", name="uq_button_flow_owner_trigger"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(64))
    screens: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship()  # noqa: F821
