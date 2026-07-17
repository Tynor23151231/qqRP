from __future__ import annotations

import asyncio
import logging

from aiogram import Router
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
    message: Message, username: str | None, session: AsyncSession, lang: str
) -> tuple[int, str, str | None] | None:
    """
    Определяет цель действия по правилам ТЗ:
    1) ответ на сообщение -> автор этого сообщения;
    2) указан @username -> сначала ищем среди уже зарегистрированных в боте (надёжно),
       и только если не нашли — пробуем get_chat (Telegram ненадёжно резолвит по
       username обычных пользователей, даже если бот их технически "видит");
    3) иначе, в личном чате -> собеседник;
    4) иначе -> None (вызывающий код попросит выбрать пользователя).
    """
    fallback_default = L(lang, "Пользователь", "User")
    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        target_user = message.reply_to_message.from_user
        fallback_name = target_user.first_name or target_user.username or fallback_default
        name, uname = await _display_info_for(session, target_user.id, fallback_name, target_user.username)
        return target_user.id, name, uname

    if username:
        user_service = UserService(session)
        known = await user_service.get_by_username(username)
        if known is not None:
            return known.telegram_id, known.display_name, known.username or username

        try:
            chat = await message.bot.get_chat(f"@{username}")
        except TelegramBadRequest:
            return None
        fallback_name = getattr(chat, "first_name", None) or getattr(chat, "title", None) or username
        name, uname = await _display_info_for(session, chat.id, fallback_name, chat.username or username)
        return chat.id, name, uname

    if message.chat.type == "private" and message.chat.id != message.from_user.id:
        chat = message.chat
        fallback_name = chat.first_name or chat.username or chat.title or fallback_default
        name, uname = await _display_info_for(session, chat.id, fallback_name, chat.username)
        return chat.id, name, uname

    return None


async def _resolve_targets(
    message: Message, parsed, session: AsyncSession, lang: str
) -> list[tuple[int, str, str | None]]:
    """
    Если в команде указано несколько @username — резолвит их все (мульти-таргет).
    Иначе — прежнее поведение через _resolve_target (reply/один @username/DM-собеседник).
    """
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
            name, un = await _display_info_for(session, chat.id, fallback_name, chat.username or uname)
            resolved.append((chat.id, name, un))
        return resolved

    single = await _resolve_target(message, parsed.target_username, session, lang)
    return [single] if single is not None else []


async def _send_business_message(message: Message, text: str, entities) -> None:
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        entities=entities,
        parse_mode=None,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        business_connection_id=message.business_connection_id,
    )


async def _send_business_action(message: Message, rendered) -> None:
    """Отправляет готовое RP-действие: с гифкой (send_animation + подпись), если она задана,
    иначе обычным текстовым сообщением."""
    if rendered.gif_file_id:
        await message.bot.send_animation(
            chat_id=message.chat.id,
            animation=rendered.gif_file_id,
            caption=rendered.text,
            caption_entities=rendered.entities,
            parse_mode=None,
            business_connection_id=message.business_connection_id,
        )
    else:
        await _send_business_message(message, rendered.text, rendered.entities)


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


async def _relay_to_qq_download_bot(message: Message, link: str) -> None:
    """
    Отправляет ссылку боту-загрузчику (@QQdownloadbot) от лица владельца через
    business_connection_id, ждёт его ответ до settings.qq_download_timeout_seconds,
    и пересылает полученное сообщение обратно в исходный чат. Если новый ответ не
    пришёл вовремя — пересылает последнее ранее полученное от него сообщение (если есть).
    """
    connection_id = message.business_connection_id
    future = qq_download.register_waiter(connection_id)

    try:
        qq_chat = await message.bot.get_chat(f"@{settings.qq_download_bot_username}")
    except TelegramBadRequest as e:
        logger.warning("Не удалось найти @%s: %s", settings.qq_download_bot_username, e)
        qq_download.clear_waiter(connection_id)
        await _send_business_message(
            message, f"⚠️ Не нашёл бота @{settings.qq_download_bot_username}.", None
        )
        return

    try:
        await message.bot.send_message(
            chat_id=qq_chat.id,
            text=link,
            business_connection_id=connection_id,
        )
    except TelegramBadRequest as e:
        logger.warning("Не удалось отправить ссылку в %s: %s", settings.qq_download_bot_username, e)
        qq_download.clear_waiter(connection_id)
        await _send_business_message(
            message,
            f"⚠️ Не получилось отправить ссылку в @{settings.qq_download_bot_username}.",
            None,
        )
        return

    reply_message: Message | None = None
    timed_out = False
    try:
        reply_message = await asyncio.wait_for(future, timeout=settings.qq_download_timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        qq_download.clear_waiter(connection_id)

    if reply_message is None and timed_out:
        reply_message = qq_download.get_last_message(connection_id)

    if reply_message is None:
        await _send_business_message(
            message,
            f"⚠️ @{settings.qq_download_bot_username} не ответил за "
            f"{settings.qq_download_timeout_seconds} сек, и раньше сообщений от него тоже не было.",
            None,
        )
        return

    try:
        await message.bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=reply_message.chat.id,
            message_id=reply_message.message_id,
            reply_markup=reply_message.reply_markup,
            business_connection_id=connection_id,
        )
    except TelegramBadRequest as e:
        logger.warning("Не удалось переслать ответ %s: %s", settings.qq_download_bot_username, e)
        await _send_business_message(
            message, f"⚠️ Получил ответ от @{settings.qq_download_bot_username}, но не смог его переслать.", None
        )


@router.business_message()
async def handle_dot_command(message: Message, db_user: User, session: AsyncSession) -> None:
    if (
        message.business_connection_id is not None
        and message.from_user is not None
        and message.from_user.username == settings.qq_download_bot_username
    ):
        # Ответ от бота-загрузчика — не dot-команда, отдаём тому, кто ждёт (.qq), и выходим.
        qq_download.resolve_waiter(message.business_connection_id, message)
        return

    if not message.text:
        return

    typing_payload = parse_typing_command(message.text, prefix=settings.command_prefix)
    if typing_payload is not None:
        if not await _is_from_connection_owner(message, session):
            return
        if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
            text, entities = subscription_required_payload(db_user.language)
            await _send_business_message(message, text, entities)
            return
        if not db_user.has_plus:
            b = EntityTextBuilder()
            g, gid = emoji("lock")
            b.add_custom_emoji(g, gid)
            b.add_text(" ")
            b.add_code(f"{settings.command_prefix}typing")
            b.add_text(
                L(
                    db_user.language,
                    f" — функция Премиум+ ({settings.premium_price_stars} ⭐️ / "
                    f"{settings.premium_duration_days} дней). Оформи в личном чате с ботом командой ",
                    f" is a Premium+ feature ({settings.premium_price_stars} ⭐️ / "
                    f"{settings.premium_duration_days} days). Get it in a private chat with the bot via ",
                )
            )
            b.add_code("/premium")
            b.add_text(".")
            text, entities = b.build()
            await _send_business_message(message, text, entities)
            return
        await _delete_source_message(message)
        await reveal_text(
            message.bot, message.chat.id, typing_payload,
            business_connection_id=message.business_connection_id,
        )
        return

    qq_prefix = f"{settings.command_prefix}qq"
    if message.text == qq_prefix or message.text.startswith(f"{qq_prefix} "):
        if not await _is_from_connection_owner(message, session):
            return
        link = message.text[len(qq_prefix):].strip()
        if not link:
            await _send_business_message(
                message,
                L(
                    db_user.language,
                    f"Пришли ссылку после команды: {qq_prefix} <ссылка>",
                    f"Send a link after the command: {qq_prefix} <link>",
                ),
                None,
            )
            return
        await _delete_source_message(message)
        await _relay_to_qq_download_bot(message, link)
        return

    parsed = parse_dot_command(message.text, prefix=settings.command_prefix)
    if parsed is None:
        return  # обычное сообщение, не RP-команда

    if not await _is_from_connection_owner(message, session):
        # Команду прислал не владелец бизнес-аккаунта (например клиент в переписке) —
        # молча игнорируем, чтобы не позволить постороннему слать сообщения от имени владельца.
        return

    if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
        text, entities = subscription_required_payload(db_user.language)
        await _send_business_message(message, text, entities)
        return

    if not db_user.is_configured:
        await _send_business_message(
            message,
            L(
                db_user.language,
                "⚠️ Сначала выбери пол в личном чате с ботом командой /start, чтобы я мог правильно склонять действия.",
                "⚠️ First choose your gender in a private chat with the bot via /start, so I can conjugate actions correctly.",
            ),
            None,
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
                db_user.language,
                f" Это своё РП-действие требует активного премиума ({settings.premium_price_stars} ⭐️ / "
                f"{settings.premium_duration_days} дней). Оформи в личном чате с ботом командой ",
                f" This custom RP action requires active premium ({settings.premium_price_stars} ⭐️ / "
                f"{settings.premium_duration_days} days). Get it in a private chat with the bot via ",
            )
        )
        b.add_code("/premium")
        b.add_text(".")
        text, entities = b.build()
        await _send_business_message(message, text, entities)
        return

    targets = await _resolve_targets(message, parsed, session, db_user.language)
    if not targets:
        if parsed.target_username:
            await _send_business_message(
                message,
                L(
                    db_user.language,
                    f"❌ Не удалось найти пользователя @{parsed.target_username}.",
                    f"❌ Couldn't find user @{parsed.target_username}.",
                ),
                None,
            )
        else:
            await _send_business_message(
                message,
                L(
                    db_user.language,
                    "🤔 Не понял, к кому применить действие. "
                    "Ответь этой командой на сообщение нужного человека или укажи @username.",
                    "🤔 I couldn't tell who to apply this action to. "
                    "Reply with this command to the right person's message, or specify @username.",
                ),
                None,
            )
        return

    rendered = await action_service.render(db_user, parsed.action_key, targets, keyword=parsed.keyword)
    if rendered is None:
        return  # неизвестная команда — молча игнорируем, чтобы не мешать обычной переписке

    await _delete_source_message(message)
    await _send_business_action(message, rendered)

    user_service = UserService(session)
    for target_id, _, _ in targets:
        await user_service.register_action_usage(db_user, parsed.action_key, target_id)
