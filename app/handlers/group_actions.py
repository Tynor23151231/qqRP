from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.models import User
from app.services.action_service import ActionService
from app.services.subscription_service import is_subscribed, subscription_required_payload
from app.services.typing_effect import reveal_text
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji
from app.utils.text_parsing import parse_dot_command, parse_typing_command

logger = logging.getLogger(__name__)
router = Router(name="group_actions")


async def _resolve_target(
    message: Message, username: str | None, session: AsyncSession, lang: str
) -> tuple[int, str, str | None] | None:
    """
    Определяет цель действия в обычном (не business) чате:
    1) ответ на сообщение -> автор этого сообщения;
    2) указан @username -> резолвим через get_chat;
    3) иначе -> None.
    """
    user_service = UserService(session)
    fallback_default = L(lang, "Пользователь", "User")

    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        target_user = message.reply_to_message.from_user
        fallback_name = target_user.first_name or target_user.username or fallback_default
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
    lang = db_user.language
    typing_payload = parse_typing_command(message.text, prefix=settings.command_prefix)
    if typing_payload is not None:
        if not await is_subscribed(message.bot, message.from_user.id):
            text, entities = subscription_required_payload(lang)
            await message.reply(text, entities=entities, parse_mode=None)
            return
        if not db_user.has_premium:
            b = EntityTextBuilder()
            g, gid = emoji("lock")
            b.add_custom_emoji(g, gid)
            b.add_text(" ")
            b.add_code(f"{settings.command_prefix}typing")
            b.add_text(
                L(
                    lang,
                    f" — платная функция ({settings.premium_price_stars} ⭐️ / "
                    f"{settings.premium_duration_days} дней). Оформи в личном чате с ботом командой ",
                    f" is a paid feature ({settings.premium_price_stars} ⭐️ / "
                    f"{settings.premium_duration_days} days). Get it in a private chat with the bot via ",
                )
            )
            b.add_code("/premium")
            b.add_text(".")
            text, entities = b.build()
            await message.reply(text, entities=entities, parse_mode=None)
            return
        await _delete_source_message(message)
        await reveal_text(message.bot, message.chat.id, typing_payload)
        return

    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not await is_subscribed(message.bot, message.from_user.id):
        text, entities = subscription_required_payload(lang)
        await message.reply(text, entities=entities, parse_mode=None)
        return

    if not db_user.is_configured:
        await message.reply(
            L(
                lang,
                "⚠️ Сначала выбери пол в личном чате с ботом командой /start, чтобы я мог правильно склонять действия.",
                "⚠️ First choose your gender in a private chat with the bot via /start, so I can conjugate actions correctly.",
            )
        )
        return

    action_service = ActionService(session)
    custom = await action_service.get_custom_trigger(db_user.id, parsed.action_key)
    if custom is not None and not db_user.has_premium:
        b = EntityTextBuilder()
        g, gid = emoji("lock")
        b.add_custom_emoji(g, gid)
        b.add_text(
            L(
                lang,
                f" Это своё РП-действие требует активного премиума ({settings.premium_price_stars} ⭐️ / "
                f"{settings.premium_duration_days} дней). Оформи в личном чате с ботом командой ",
                f" This custom RP action requires active premium ({settings.premium_price_stars} ⭐️ / "
                f"{settings.premium_duration_days} days). Get it in a private chat with the bot via ",
            )
        )
        b.add_code("/premium")
        b.add_text(".")
        text, entities = b.build()
        await message.reply(text, entities=entities, parse_mode=None)
        return

    target = await _resolve_target(message, parsed.target_username, session, lang)
    if target is None:
        if parsed.target_username:
            await message.reply(
                L(
                    lang,
                    f"❌ Не удалось найти пользователя @{parsed.target_username}.",
                    f"❌ Couldn't find user @{parsed.target_username}.",
                )
            )
        else:
            await message.reply(
                L(
                    lang,
                    "🤔 Не понял, к кому применить действие. "
                    "Ответь этой командой на сообщение нужного человека или укажи @username.",
                    "🤔 I couldn't tell who to apply this action to. "
                    "Reply with this command to the right person's message, or specify @username.",
                )
            )
        return

    target_id, target_name, target_username = target

    rendered = await action_service.render(
        db_user, parsed.action_key, target_id, target_name, target_username, keyword=parsed.keyword
    )
    if rendered is None:
        return  # неизвестная команда — молча игнорируем, чтобы не мешать обычной переписке

    await _delete_source_message(message)
    if rendered.gif_file_id:
        await message.bot.send_animation(
            chat_id=message.chat.id,
            animation=rendered.gif_file_id,
            caption=rendered.text,
            caption_entities=rendered.entities,
            parse_mode=None,
        )
    else:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=rendered.text,
            entities=rendered.entities,
            parse_mode=None,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    user_service = UserService(session)
    await user_service.register_action_usage(db_user, parsed.action_key, target_id)
