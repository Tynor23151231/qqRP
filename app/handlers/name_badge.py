from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetBusinessAccountName
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import L
from app.keyboards.menu import back_to_menu_row
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="name_badge")

# Невидимый паддинг (soft hyphen) + сам значок. Число паддинг-символов можно
# подправить здесь одним местом, если визуально хочется больше/меньше отступа.
_PADDING = "\u00ad" * 20
_BADGE_SUFFIX = f"{_PADDING} ⌞ 👜 ⌝"
_MAX_LAST_NAME_LEN = 64


def _build_last_name(original: str | None) -> str:
    original = original or ""
    available = _MAX_LAST_NAME_LEN - len(_BADGE_SUFFIX) - 1  # -1 на разделяющий пробел
    if available < 0:
        return _BADGE_SUFFIX[:_MAX_LAST_NAME_LEN]
    trimmed = original[:available] if len(original) > available else original
    return f"{trimmed} {_BADGE_SUFFIX}" if trimmed else _BADGE_SUFFIX


def _paywall_payload(lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Значок в фамилии — премиум-функция", "Name badge is a premium feature"))
    b.add_text(
        L(
            lang,
            "\n\nБот дописывает к твоей настоящей фамилии декоративный значок "
            "⌞ 👜 ⌝ прямо в профиле Telegram (через Business API). Отключишь — "
            "фамилия вернётся к исходной.\n\nОформить: ",
            "\n\nThe bot appends a decorative badge ⌞ 👜 ⌝ to your real last name right "
            "in your Telegram profile (via the Business API). Turn it off and your "
            "last name goes back to normal.\n\nGet it: ",
        )
    )
    b.add_code("/premium")
    return b.build()


def _keyboard(lang: str, *, enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        button = InlineKeyboardButton(
            text=L(lang, "Отключить", "Turn off"),
            callback_data="namebadge:toggle",
            icon_custom_emoji_id=emoji("disable")[1],
            style="danger",
        )
    else:
        button = InlineKeyboardButton(
            text=L(lang, "Включить", "Turn on"),
            callback_data="namebadge:toggle",
            icon_custom_emoji_id=emoji("check")[1],
            style="success",
        )
    rows = [[button], back_to_menu_row(lang)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def name_badge_screen(db_user: User) -> tuple[str, list, InlineKeyboardMarkup]:
    lang = db_user.language
    if not db_user.has_premium:
        text, entities = _paywall_payload(lang)
        return text, entities, InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row(lang)])

    b = EntityTextBuilder()
    b.add_bold(L(lang, "Значок в фамилии", "Name badge"))
    b.add_text(
        L(
            lang,
            "\n\nДобавляет к твоей фамилии в профиле Telegram значок ⌞ 👜 ⌝ (через Business API). "
            "Отключишь — вернётся исходная фамилия.\n\n",
            "\n\nAdds a badge ⌞ 👜 ⌝ to your Telegram profile last name (via the Business API). "
            "Turn it off and your original last name comes back.\n\n",
        )
    )

    if db_user.business_connection_id is None:
        b.add_text(
            L(
                lang,
                "⚠️ Сначала подключи бота как Telegram Business Bot.",
                "⚠️ First connect the bot as a Telegram Business Bot.",
            )
        )
    elif not db_user.can_edit_name:
        b.add_text(
            L(
                lang,
                "⚠️ У бота нет права менять имя. В настройках Business-подключения включи "
                "право «Изменение имени» и вернись сюда.",
                "⚠️ The bot doesn't have permission to change your name. In your Business "
                "connection settings, enable the \"Edit name\" right and come back here.",
            )
        )
    else:
        status = L(lang, "включён ✅", "on ✅") if db_user.name_badge_enabled else L(lang, "выключен", "off")
        b.add_text(L(lang, f"Статус: {status}", f"Status: {status}"))

    text, entities = b.build()
    keyboard = _keyboard(lang, enabled=db_user.name_badge_enabled)
    return text, entities, keyboard


@router.callback_query(F.data == "menu:namebadge")
async def cb_menu_name_badge(callback: CallbackQuery, db_user: User) -> None:
    text, entities, keyboard = await name_badge_screen(db_user)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "namebadge:toggle")
async def cb_toggle_name_badge(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    if not db_user.has_premium:
        await callback.answer(L(lang, "Нужен премиум", "Premium required"), show_alert=True)
        return
    if db_user.business_connection_id is None:
        await callback.answer(
            L(lang, "Сначала подключи Business Bot", "Connect the Business Bot first"), show_alert=True
        )
        return
    if not db_user.can_edit_name:
        await callback.answer(
            L(lang, "У бота нет права менять имя", "The bot doesn't have permission to edit the name"),
            show_alert=True,
        )
        return

    user_service = UserService(session)
    turning_on = not db_user.name_badge_enabled
    first_name = db_user.name_badge_original_first_name or callback.from_user.first_name

    new_last_name = (
        _build_last_name(db_user.name_badge_original_last_name)
        if turning_on
        else (db_user.name_badge_original_last_name or None)
    )

    try:
        await callback.bot(
            SetBusinessAccountName(
                business_connection_id=db_user.business_connection_id,
                first_name=first_name,
                last_name=new_last_name,
            )
        )
    except TelegramBadRequest:
        await callback.answer(
            L(
                lang,
                "Не получилось изменить имя — проверь права бота в Business-подключении",
                "Couldn't change the name — check the bot's rights in the Business connection",
            ),
            show_alert=True,
        )
        return

    await user_service.set_name_badge_enabled(db_user, turning_on)
    await callback.answer(L(lang, "Готово", "Done"))

    text, entities, keyboard = await name_badge_screen(db_user)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
