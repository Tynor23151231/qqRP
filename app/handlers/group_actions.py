from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.models import User
from app.services import qq_download
from app.services.action_service import ActionService
from app.services.subscription_service import is_subscribed, subscription_required_payload
from app.services.typing_effect import reveal_text
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji
from app.utils.text_parsing import parse_dot_command, parse_typing_command

logger = logging.getLogger(__name__)
router = Router(name="group_actions")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.from_user.username == settings.qq_download_bot_username)
async def handle_qq_bot_reply_in_relay_group(message: Message) -> None:
    """Ответ от @QQdownloadbot в чьей-то служебной группе-релее — отдаём тому, кто ждёт .qq."""
    qq_download.resolve_waiter(str(message.chat.id), message)


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
        known = await user_service.get_by_username(username)
        if known is not None:
            return known.telegram_id, known.display_name, known.username or username

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


async def _resolve_targets(
    message: Message, parsed, session: AsyncSession, lang: str
) -> list[tuple[int, str, str | None]]:
    """Мульти-таргет при 2+ @username, иначе прежнее поведение через _resolve_target."""
    if len(parsed.target_usernames) >= 2:
        user_service = UserService(session)
        resolved: list[tuple[int, str, str | None]] = []
        for uname in parsed.target_usernames:
            known = await user_service.get_by_username(uname)
            if known is not None:
                resolved.append((known.telegram_id, known.display_name, known.username or uname))
                continue

            try:
                chat = await message.bot.get_chat(f"@{uname}")
            except TelegramBadRequest:
                continue
            fallback_name = getattr(chat, "first_name", None) or getattr(chat, "title", None) or uname
            known = await user_service.get_by_telegram_id(chat.id)
            name = (known.custom_name if known else None) or fallback_name
            un = (known.username if known else None) or chat.username or uname
            resolved.append((chat.id, name, un))
        return resolved

    single = await _resolve_target(message, parsed.target_username, session, lang)
    return [single] if single is not None else []


async def _relay_to_qq_download_bot(message: Message, link: str, db_user: User) -> None:
    """Аналог business-версии, но для обычных групп: без business_connection_id,
    обычными send_message/copy_message. Логика ожидания та же (см. app/services/qq_download.py)."""
    lang = db_user.language
    if not db_user.qq_relay_chat_id or not db_user.qq_relay_enabled:
        b = EntityTextBuilder()
        g, gid = emoji("lock")
        b.add_custom_emoji(g, gid)
        b.add_text(
            L(
                lang,
                " Сначала настрой поддержку ссылок: Меню → Список команд → "
                "«🔗 Включить поддержку ссылок» (там пошаговая инструкция).",
                " First set up link support: Menu → Commands list → "
                "\"🔗 Enable link support\" (step-by-step guide there).",
            )
        )
        text, entities = b.build()
        await message.reply(text, entities=entities, parse_mode=None)
        return

    relay_key = str(db_user.qq_relay_chat_id)
    future = qq_download.register_waiter(relay_key)

    try:
        await message.bot.send_message(chat_id=db_user.qq_relay_chat_id, text=link)
    except TelegramBadRequest as e:
        logger.warning("Не удалось отправить ссылку в группу-релей %s: %s", db_user.qq_relay_chat_id, e)
        qq_download.clear_waiter(relay_key)
        await message.reply(
            L(
                lang,
                "⚠️ Не получилось отправить ссылку в служебную группу. Проверь, что бот всё ещё "
                "состоит в ней (Меню → Список команд → «🔗 Включить поддержку ссылок»).",
                "⚠️ Couldn't send the link to the relay group. Check that the bot is still a "
                "member (Menu → Commands list → \"🔗 Enable link support\").",
            )
        )
        return

    reply_message: Message | None = None
    timed_out = False
    try:
        reply_message = await asyncio.wait_for(future, timeout=settings.qq_download_timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        qq_download.clear_waiter(relay_key)

    if reply_message is None and timed_out:
        reply_message = qq_download.get_last_message(relay_key)

    if reply_message is None:
        await message.reply(
            L(
                lang,
                f"⚠️ @{settings.qq_download_bot_username} не ответил за "
                f"{settings.qq_download_timeout_seconds} сек, и раньше сообщений от него тоже не было.",
                f"⚠️ @{settings.qq_download_bot_username} didn't reply within "
                f"{settings.qq_download_timeout_seconds}s, and there's no earlier message from it either.",
            )
        )
        return

    try:
        await qq_download.resend_message(message.bot, message.chat.id, reply_message)
    except TelegramBadRequest as e:
        logger.warning("Не удалось переслать ответ %s: %s", settings.qq_download_bot_username, e)
        await message.reply(
            L(
                lang,
                f"⚠️ Получил ответ от @{settings.qq_download_bot_username}, но не смог его переслать.",
                f"⚠️ Got a reply from @{settings.qq_download_bot_username}, but couldn't forward it.",
            )
        )


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
        if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
            text, entities = subscription_required_payload(lang)
            await message.reply(text, entities=entities, parse_mode=None)
            return
        if not db_user.has_plus:
            b = EntityTextBuilder()
            g, gid = emoji("lock")
            b.add_custom_emoji(g, gid)
            b.add_text(" ")
            b.add_code(f"{settings.command_prefix}typing")
            b.add_text(
                L(
                    lang,
                    f" — функция Премиум+ ({settings.premium_price_stars} ⭐️ / "
                    f"{settings.premium_duration_days} дней). Оформи в личном чате с ботом командой ",
                    f" is a Premium+ feature ({settings.premium_price_stars} ⭐️ / "
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

    qq_prefix = f"{settings.command_prefix}qq"
    if message.text == qq_prefix or message.text.startswith(f"{qq_prefix} "):
        if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
            text, entities = subscription_required_payload(lang)
            await message.reply(text, entities=entities, parse_mode=None)
            return
        link = message.text[len(qq_prefix):].strip()
        if not link:
            await message.reply(
                L(
                    lang,
                    f"Пришли ссылку после команды: {qq_prefix} <ссылка>",
                    f"Send a link after the command: {qq_prefix} <link>",
                )
            )
            return
        await _delete_source_message(message)
        await _relay_to_qq_download_bot(message, link, db_user)
        return

    chatid_prefix = f"{settings.command_prefix}chatid"
    if message.text == chatid_prefix:
        from app.handlers.qq_relay import send_chatid_reply  # локальный импорт во избежание циклов

        await send_chatid_reply(message, db_user)
        return

    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
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

    targets = await _resolve_targets(message, parsed, session, lang)
    if not targets:
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

    rendered = await action_service.render(db_user, parsed.action_key, targets, keyword=parsed.keyword)
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
    for target_id, _, _ in targets:
        await user_service.register_action_usage(db_user, parsed.action_key, target_id)
