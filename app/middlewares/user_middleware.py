from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.services.user_service import UserService


class UserMiddleware(BaseMiddleware):
    """
    Достаёт from_user из апдейта (Message / BusinessConnection / business_message
    и т.д.), находит или создаёт соответствующего User и кладёт его в data['db_user'].
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        aiogram_user = data.get("event_from_user")
        session = data.get("session")

        if aiogram_user is not None and session is not None:
            service = UserService(session)
            db_user, created = await service.get_or_create(
                telegram_id=aiogram_user.id,
                first_name=aiogram_user.first_name or aiogram_user.username or str(aiogram_user.id),
                username=aiogram_user.username,
            )
            data["db_user"] = db_user
            data["db_user_created"] = created

        return await handler(event, data)
