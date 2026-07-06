from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.keyboards.gender import gender_keyboard
from app.keyboards.menu import back_only_keyboard, main_menu_keyboard, with_back_button
from app.keyboards.profile import profile_keyboard
from app.keyboards.settings import settings_keyboard
from app.models import Gender, User
from app.services.action_service import ActionService
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="start")

ONBOARDING_TEXT = (
    "👋 <b>Привет! Это qqRP Bot.</b>\n\n"
    "Я умею красиво оформлять RP-действия по коротким командам с точкой — "
    f"например <code>{settings.command_prefix}муа</code>, <code>{settings.command_prefix}обнять</code>, "
    f"<code>{settings.command_prefix}цветы</code>.\n\n"
    "<b>Как это работает:</b>\n"
    "1️⃣ Подключаешь меня как Telegram Business Bot к своему аккаунту\n"
    "2️⃣ Пишешь в любом чате (личном или группе) команду вида "
    f"<code>{settings.command_prefix}муа</code> (в ответ на сообщение человека, "
    "или с <code>@username</code> после команды)\n"
    "3️⃣ Я удаляю твоё сообщение-команду и отправляю красивое RP-действие "
    "с кликабельными именами вместо него\n\n"
    "Для начала выбери свой пол — это нужно, чтобы правильно склонять действия "
    "(«поцеловал» / «поцеловала»):"
)

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _howto_text() -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("howto")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold("Как подключить Telegram Business")
    b.add_text(
        "\n\nНужен Telegram Premium — без него бизнес-функции недоступны.\n\n"
        "1. Открой Настройки → Telegram для бизнеса → Чат-боты\n"
        "2. Введи имя этого бота и подключи его\n"
        "3. Обязательно включи права:\n"
        "   • Читать сообщения\n"
        "   • Отправлять сообщения\n"
        "   • Удалять отправленные сообщения ⚠️ без этого права команды "
        "не будут удаляться после срабатывания\n\n"
        f"После подключения просто пиши команды вроде {settings.command_prefix}муа "
        "в любом чате — я отвечу от твоего имени."
    )
    return b.build()


def _format_commands_list(action_service: ActionService) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("commands")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold("Список команд")
    b.add_text("\n\nПиши в чате в ответ на сообщение человека или с @username:\n\n")
    for key, aliases, action_emoji in sorted(action_service.builtin_display_list(), key=lambda x: x[0]):
        names = f"{settings.command_prefix}{key}"
        if aliases:
            names += " / " + " / ".join(f"{settings.command_prefix}{a}" for a in aliases)
        b.add_text(f"{action_emoji} ")
        b.add_code(names)
        b.add_text("\n")
    b.add_text(f"\n➕ Плюс можно создать свои действия через {settings.command_prefix}addrp (премиум).")
    return b.build()


def _menu_home_payload(name: str | None = None) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("home")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold("Главное меню")
    if name:
        b.add_text(f"\n\nС возвращением, {name}! ")
        wg, wid = emoji("wave")
        b.add_custom_emoji(wg, wid)
    return b.build()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    if db_user.is_configured:
        text, entities = _menu_home_payload(db_user.display_name)
        await message.answer(
            text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
            reply_markup=main_menu_keyboard(db_user),
        )
        return

    await message.answer(ONBOARDING_TEXT, reply_markup=gender_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User) -> None:
    text, entities = _menu_home_payload()
    await message.answer(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )


@router.callback_query(F.data.startswith("gender:"))
async def on_gender_chosen(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    gender_value = callback.data.split(":", 1)[1]
    gender = Gender.MALE if gender_value == "male" else Gender.FEMALE

    service = UserService(session)
    await service.set_gender(db_user, gender)

    b = EntityTextBuilder()
    b.add_text("Готово! Пол установлен: ")
    key = "male" if gender == Gender.MALE else "female"
    glyph, cid = emoji(key)
    b.add_custom_emoji(glyph, cid)
    label = " Мужчина" if gender == Gender.MALE else " Женщина"
    b.add_bold(label)
    b.add_text(
        ".\n\nОсталось подключить меня как Telegram Business Bot — жми «Как подключить Business» "
        f"ниже, а потом пробуй команды вроде {settings.command_prefix}муа в ответ на сообщение."
    )
    text, entities = b.build()

    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )
    await callback.answer("Пол сохранён")


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, db_user: User) -> None:
    text, entities = _menu_home_payload()
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.profile import _format_profile_entities  # локальный импорт во избежание циклов

    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or "ещё нет"

    text, entities = _format_profile_entities(db_user, favorite)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=with_back_button(profile_keyboard()),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery, db_user: User) -> None:
    b = EntityTextBuilder()
    glyph, cid = emoji("settings2")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold("Настройки")
    text, entities = b.build()
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None,
        reply_markup=with_back_button(settings_keyboard(db_user)),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:commands")
async def cb_menu_commands(callback: CallbackQuery, session: AsyncSession) -> None:
    action_service = ActionService(session)
    text, entities = _format_commands_list(action_service)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=back_only_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:howto")
async def cb_menu_howto(callback: CallbackQuery) -> None:
    text, entities = _howto_text()
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=back_only_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:addrp")
async def cb_menu_addrp(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.custom_rp import my_rp_screen  # локальный импорт во избежание циклов

    text, entities, keyboard = await my_rp_screen(db_user, session)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "menu:premium")
async def cb_menu_premium(callback: CallbackQuery, db_user: User) -> None:
    from app.handlers.premium import _buy_keyboard, _status_text  # локальный импорт во избежание циклов

    text, entities = _status_text(db_user)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(_buy_keyboard())
    )
    await callback.answer()
