from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.keyboards.menu import back_to_menu_row
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder

router = Router(name="qq_relay")


def _status_keyboard(lang: str, *, configured: bool, enabled: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if configured:
        rows.append(
            [
                InlineKeyboardButton(
                    text=L(lang, "🚫 Отключить", "🚫 Turn off") if enabled else L(lang, "✅ Включить", "✅ Turn on"),
                    callback_data="qqrelay:toggle",
                    style="danger" if enabled else "success",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text=L(lang, "🗑 Сбросить группу", "🗑 Reset group"), callback_data="qqrelay:reset")]
        )
    rows.append(back_to_menu_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def qq_relay_screen(db_user: User) -> tuple[str, list, InlineKeyboardMarkup]:
    lang = db_user.language
    configured = db_user.qq_relay_chat_id is not None
    enabled = configured and db_user.qq_relay_enabled

    b = EntityTextBuilder()
    b.add_bold(L(lang, "🔗 Поддержка ссылок (.qq)", "🔗 Link support (.qq)"))
    b.add_text(
        L(
            lang,
            f"\n\nКоманда {settings.command_prefix}qq <ссылка> скачивает видео из TikTok/Pinterest "
            f"через @{settings.qq_download_bot_username} и присылает результат прямо в чат.\n\n"
            "Так как Telegram не даёт ботам напрямую переписываться друг с другом, нужна "
            "своя служебная группа-посредник — один раз настроишь и забудешь.\n\n",
            f"\n\nThe {settings.command_prefix}qq <link> command downloads TikTok/Pinterest videos "
            f"via @{settings.qq_download_bot_username} and sends the result right into the chat.\n\n"
            "Since Telegram doesn't let bots message each other directly, you need your own "
            "relay group — set it up once and forget about it.\n\n",
        )
    )

    b.add_bold(L(lang, "Как настроить:", "How to set up:"))
    b.add_text(
        L(
            lang,
            "\n1️⃣ Создай новую приватную группу (можно назвать как угодно)\n"
            "2️⃣ Добавь в неё этого бота — через «Добавить в группу» из его профиля\n"
            f"3️⃣ Добавь туда же @{settings.qq_download_bot_username}\n"
            f"4️⃣ У @{settings.qq_download_bot_username} отключи Privacy Mode: напиши @BotFather → "
            "/mybots → выбери бота → Bot Settings → Group Privacy → Turn off "
            "(без этого он не увидит ссылки от другого бота в группе)\n"
            f"5️⃣ Напиши в этой группе команду {settings.command_prefix}chatid — бот пришлёт "
            "id группы с кнопкой подтверждения\n"
            "6️⃣ Нажми «Использовать эту группу» — готово, можно пользоваться "
            f"{settings.command_prefix}qq из любого чата",
            "\n1️⃣ Create a new private group (any name works)\n"
            "2️⃣ Add this bot to it — usually easiest via \"Add to Group\" from its profile\n"
            f"3️⃣ Add @{settings.qq_download_bot_username} to the same group\n"
            f"4️⃣ Turn off Privacy Mode for @{settings.qq_download_bot_username}: message @BotFather → "
            "/mybots → pick the bot → Bot Settings → Group Privacy → Turn off "
            "(otherwise it won't see links from another bot in the group)\n"
            f"5️⃣ In that group, send the command {settings.command_prefix}chatid — the bot will "
            "reply with the group's id and a confirm button\n"
            "6️⃣ Tap \"Use this group\" — done, you can now use "
            f"{settings.command_prefix}qq from any chat",
        )
    )

    b.add_text(L(lang, "\n\nСтатус: ", "\n\nStatus: "))
    if not configured:
        b.add_text(L(lang, "не настроено", "not set up"))
    elif enabled:
        b.add_text(L(lang, "✅ активировано", "✅ active"))
    else:
        b.add_text(L(lang, "⏸ настроено, но отключено", "⏸ set up, but turned off"))

    text, entities = b.build()
    return text, entities, _status_keyboard(lang, configured=configured, enabled=enabled)


@router.callback_query(F.data == "menu:qqrelay")
async def cb_menu_qq_relay(callback: CallbackQuery, db_user: User) -> None:
    text, entities, keyboard = qq_relay_screen(db_user)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "qqrelay:toggle")
async def cb_qq_relay_toggle(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    if db_user.qq_relay_chat_id is None:
        await callback.answer()
        return
    user_service = UserService(session)
    await user_service.set_qq_relay_enabled(db_user, not db_user.qq_relay_enabled)
    text, entities, keyboard = qq_relay_screen(db_user)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "qqrelay:reset")
async def cb_qq_relay_reset(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    user_service = UserService(session)
    await user_service.clear_qq_relay(db_user)
    text, entities, keyboard = qq_relay_screen(db_user)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
    await callback.answer(L(db_user.language, "Сброшено", "Reset"))


@router.message(Command("chatid"))
async def cmd_chat_id(message: Message, db_user: User) -> None:
    lang = db_user.language
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            L(
                lang,
                f"Эта команда для группы: напиши {settings.command_prefix}chatid внутри "
                "своей служебной группы для .qq.",
                f"This command is for groups: send {settings.command_prefix}chatid inside "
                "your .qq relay group.",
            )
        )
        return

    await message.answer(
        L(
            lang,
            f"🆔 id этой группы: <code>{message.chat.id}</code>\n\nЕсли это твоя группа-посредник "
            f"для .qq (внутри уже добавлен @{settings.qq_download_bot_username} с выключенным "
            "Privacy Mode) — нажми кнопку ниже.",
            f"🆔 This group's id: <code>{message.chat.id}</code>\n\nIf this is your .qq relay group "
            f"(with @{settings.qq_download_bot_username} already added and Privacy Mode off) — "
            "tap the button below.",
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=L(lang, "✅ Использовать эту группу", "✅ Use this group"),
                        callback_data=f"qqrelay:use:{message.chat.id}",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("qqrelay:use:"))
async def cb_qq_relay_use(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    chat_id = int(callback.data.split(":", 2)[2])

    user_service = UserService(session)
    await user_service.set_qq_relay_chat(db_user, chat_id)

    await callback.answer(L(lang, "Сохранено!", "Saved!"))
    await callback.message.edit_text(
        L(
            lang,
            f"✅ Готово! Теперь {settings.command_prefix}qq <ссылка> работает из любого чата "
            "через эту группу.",
            f"✅ Done! {settings.command_prefix}qq <link> now works from any chat via this group.",
        )
    )
