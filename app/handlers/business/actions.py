from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.action_service import ActionService
from app.services.typing_effect import reveal_text
from app.services.user_service import UserService
from app.utils.text_parsing import parse_dot_command, parse_typing_command

logger = logging.getLogger(__name__)
router = Router(name="business_actions")


async def _is_from_connection_owner(message: Message, session: AsyncSession) -> bool:
    """
    В Business-чате business_message приходит для сообщений ОБОИХ сторон переписки:
    и владельца аккаунта, и его собеседника (клиента). Отправка же сообщений через
    business_connection_id всегда идёт от лица владельца — поэтому dot-команды нужно
    обрабатывать, только если их прислал сам владелец, а не случайный собеседник.
    """
    if message.business_connection_id is None or message.from_user is None:
        return False

    user_service = UserService(session)
    owner = await user_service.get_by_business_connection_id(message.business_connection_id)
    return owner is not None and owner.telegram_id == message.from_user.id


async def _display_info_for(
    session: AsyncSession, telegram_id: int, fallback_name: str, fallback_username: str | None
) -> tuple[str, str | None]:
    """Если пользователь уже известен боту — берём его кастомное имя/username из БД."""
    user_service = UserService(session)
    known = await user_service.get_by_telegram_id(telegram_id)
    if known is not None:
        name = known.custom_name or fallback_name
        username = known.username or fallback_username
        return name, username
    return fallback_name, fallback_username


async def _resolve_target(
    message: Message, username: str | None, session: AsyncSession
) -> tuple[int, str, str | None] | None:
    """
    Определяет цель действия по правилам ТЗ:
    1) ответ на сообщение -> автор этого сообщения;
    2) указан @username -> резолвим через get_chat;
    3) иначе, в личном чате -> собеседник;
    4) иначе -> None (вызывающий код попросит выбрать пользователя).
    """
    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        target_user = message.reply_to_message.from_user
        fallback_name = target_user.first_name or target_user.username or "Пользователь"
        name, uname = await _display_info_for(session, target_user.id, fallback_name, target_user.username)
        return target_user.id, name, uname

    if username:
        try:
            chat = await message.bot.get_chat(f"@{username}")
        except TelegramBadRequest:
            return None
        fallback_name = getattr(chat, "first_name", None) or getattr(chat, "title", None) or username
        name, uname = await _display_info_for(session, chat.id, fallback_name, chat.username or username)
        return chat.id, name, uname

    if message.chat.type == "private" and message.chat.id != message.from_user.id:
        chat = message.chat
        fallback_name = chat.first_name or chat.username or chat.title or "Пользователь"
        name, uname = await _display_info_for(session, chat.id, fallback_name, chat.username)
        return chat.id, name, uname

    return None


async def _send_business_message(message: Message, text: str, entities) -> None:
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        entities=entities,
        parse_mode=None,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
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
    except TelegramBadRequest as e:
        # Чаще всего причина — у бота нет права "Удалять отправленные сообщения"
        # в настройках Business-подключения (Telegram Settings -> Business -> Chatbots).
        logger.warning(
            "Не удалось удалить сообщение %s (business_connection_id=%s): %s",
            message.message_id, message.business_connection_id, e,
        )


@router.business_message()
async def handle_dot_command(message: Message, db_user: User, session: AsyncSession) -> None:
    if not message.text:
        return

    typing_payload = parse_typing_command(message.text, prefix=settings.command_prefix)
    if typing_payload is not None:
        if not await _is_from_connection_owner(message, session):
            return
        if not db_user.has_premium:
            await _send_business_message(
                message,
                "🔒 <code>.typing</code> — платная функция "
                f"({settings.premium_price_stars} ⭐️ / {settings.premium_duration_days} дней). "
                "Оформи в личном чате с ботом командой /premium.",
                None,
            )
            return
        await _delete_source_message(message)
        await reveal_text(
            message.bot, message.chat.id, typing_payload,
            business_connection_id=message.business_connection_id,
        )
        return

    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not await _is_from_connection_owner(message, session):
        # Команду прислал не владелец бизнес-аккаунта (например клиент в переписке) —
        # молча игнорируем, чтобы не позволить постороннему слать сообщения от имени владельца.
        return

    if not db_user.is_configured:
        await _send_business_message(
            message,
            "⚠️ Сначала выбери пол в личном чате с ботом командой /start, чтобы я мог правильно склонять действия.",
            None,
        )
        return

    target = await _resolve_target(message, parsed.target_username, session)
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

    target_id, target_name, target_username = target

    action_service = ActionService(session)
    rendered = await action_service.render(
        db_user, parsed.action_key, target_id, target_name, target_username, keyword=parsed.keyword
    )
    if rendered is None:
        return  # неизвестная команда — молча игнорируем, чтобы не мешать обычной переписке

    await _delete_source_message(message)
    await _send_business_message(message, rendered.text, rendered.entities)

    user_service = UserService(session)
    await user_service.register_action_usage(db_user, parsed.action_key, target_id)
