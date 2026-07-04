from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.action_service import ActionService
from app.services.user_service import UserService
from app.utils.text_parsing import parse_dot_command

logger = logging.getLogger(__name__)
router = Router(name="business_actions")


async def _resolve_target(message: Message, username: str | None) -> tuple[int, str] | None:
    """
    Определяет цель действия по правилам ТЗ:
    1) ответ на сообщение -> автор этого сообщения;
    2) указан @username -> резолвим через get_chat;
    3) иначе -> None (вызывающий код попросит выбрать пользователя).
    """
    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        target_user = message.reply_to_message.from_user
        return target_user.id, target_user.first_name or target_user.username or "Пользователь"

    if username:
        try:
            chat = await message.bot.get_chat(f"@{username}")
        except TelegramBadRequest:
            return None
        name = getattr(chat, "first_name", None) or getattr(chat, "title", None) or username
        return chat.id, name

    if message.chat.type == "private" and message.chat.id != message.from_user.id:
        chat = message.chat
        name = chat.first_name or chat.username or chat.title or "Пользователь"
        return chat.id, name

    return None


async def _send_business_message(message: Message, text: str, entities) -> None:
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        entities=entities,
        business_connection_id=message.business_connection_id,
    )


async def _delete_source_message(message: Message) -> None:
    try:
        if message.business_connection_id:
            await message.bot.delete_business_messages(
                business_connection_id=message.business_connection_id,
                message_ids=[message.message_id],
            )
        else:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id,
            )
    except TelegramBadRequest:
        # Нет прав на удаление (например, в группе) — просто оставляем команду как есть.
        logger.debug("Не удалось удалить исходное сообщение %s", message.message_id)


@router.business_message()
async def handle_dot_command(message: Message, db_user: User, session: AsyncSession) -> None:
    if not message.text:
        return

    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not db_user.is_configured:
        await _send_business_message(
            message,
            "⚠️ Сначала выбери пол в личном чате с ботом командой /start, чтобы я мог правильно склонять действия.",
            None,
        )
        return

    target = await _resolve_target(message, parsed.target_username)
    if target is None:
        if parsed.target_username:
            await _send_business_message(
                message, f"❌ Не удалось найти пользователя @{parsed.target_username}.", None
            )
        else:
            await _send_business_message(
                message,
                "🤔 Не понял, к кому применить действие. "
                "Ответь этой командой на сообщение нужного человека или укажи @username.",
                None,
            )
        return

    target_id, target_name = target

    action_service = ActionService(session)
    rendered = await action_service.render(db_user, parsed.action_key, target_id, target_name)
    if rendered is None:
        return  # неизвестная команда — молча игнорируем, чтобы не мешать обычной переписке

    await _delete_source_message(message)
    await _send_business_message(message, rendered.text, rendered.entities)

    user_service = UserService(session)
    await user_service.register_action_usage(db_user, parsed.action_key, target_id)
