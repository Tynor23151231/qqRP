from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.action_service import ActionService
from app.services.user_service import UserService
from app.utils.text_parsing import parse_dot_command

logger = logging.getLogger(__name__)
router = Router(name="group_actions")


async def _resolve_target(
    message: Message, username: str | None, session: AsyncSession
) -> tuple[int, str, str | None] | None:
    """
    Определяет цель действия в обычном (не business) чате:
    1) ответ на сообщение -> автор этого сообщения;
    2) указан @username -> резолвим через get_chat;
    3) иначе -> None.
    """
    user_service = UserService(session)

    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        target_user = message.reply_to_message.from_user
        fallback_name = target_user.first_name or target_user.username or "Пользователь"
        known = await user_service.get_by_telegram_id(target_user.id)
        name = (known.custom_name if known else None) or fallback_name
        uname = (known.username if known else None) or target_user.username
        return target_user.id, name, uname

    if username:
        try:
            chat = await message.bot.get_chat(f"@{username}")
        except TelegramBadRequest:
            return None
        fallback_name = getattr(chat, "first_name", None) or getattr(chat, "title", None) or username
        known = await user_service.get_by_telegram_id(chat.id)
        name = (known.custom_name if known else None) or fallback_name
        uname = (known.username if known else None) or chat.username or username
        return chat.id, name, uname

    return None


async def _delete_source_message(message: Message) -> None:
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except TelegramBadRequest:
        # Нет прав на удаление (бот не админ) — просто оставляем команду как есть.
        logger.debug("Не удалось удалить исходное сообщение %s", message.message_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def handle_dot_command(message: Message, db_user: User, session: AsyncSession) -> None:
    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not db_user.is_configured:
        await message.reply(
            "⚠️ Сначала выбери пол в личном чате с ботом командой /start, чтобы я мог правильно склонять действия."
        )
        return

    target = await _resolve_target(message, parsed.target_username, session)
    if target is None:
        if parsed.target_username:
            await message.reply(f"❌ Не удалось найти пользователя @{parsed.target_username}.")
        else:
            await message.reply(
                "🤔 Не понял, к кому применить действие. "
                "Ответь этой командой на сообщение нужного человека или укажи @username."
            )
        return

    target_id, target_name, target_username = target

    action_service = ActionService(session)
    rendered = await action_service.render(
        db_user, parsed.action_key, target_id, target_name, target_username
    )
    if rendered is None:
        return  # неизвестная команда — молча игнорируем, чтобы не мешать обычной переписке

    await _delete_source_message(message)
    await message.bot.send_message(
        chat_id=message.chat.id, text=rendered.text, entities=rendered.entities, parse_mode=None
    )

    user_service = UserService(session)
    await user_service.register_action_usage(db_user, parsed.action_key, target_id)
