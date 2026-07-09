from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import L
from app.models import User
from app.utils.premium_emoji import emoji


def main_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    lang = user.language
    premium_label = L(lang, "Премиум ✔️", "Premium ✔️") if user.has_premium else L(lang, "Премиум", "Premium")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Профиль", "Profile"),
                    callback_data="menu:profile",
                    icon_custom_emoji_id=emoji("profile")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Настройки", "Settings"),
                    callback_data="menu:settings",
                    icon_custom_emoji_id=emoji("settings2")[1],
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Список команд", "Commands list"),
                    callback_data="menu:commands",
                    icon_custom_emoji_id=emoji("commands")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Своё RP", "My RP"),
                    callback_data="menu:addrp",
                    icon_custom_emoji_id=emoji("addrp")[1],
                ),
            ],
            [
                InlineKeyboardButton(
                    text=premium_label,
                    callback_data="menu:premium",
                    icon_custom_emoji_id=emoji("premium")[1],
                    style="success" if user.has_premium else None,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Как подключить Business", "How to connect Business"),
                    callback_data="menu:howto",
                    icon_custom_emoji_id=emoji("howto")[1],
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "👜 Значок в фамилии", "👜 Name badge"),
                    callback_data="menu:namebadge",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Рефералы", "Referrals"),
                    callback_data="menu:referral",
                ),
            ],
        ]
    )


def back_to_menu_row(lang: str = "ru") -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=L(lang, "Меню", "Menu"), callback_data="menu:home", icon_custom_emoji_id=emoji("home2")[1]
        )
    ]


def with_back_button(keyboard: InlineKeyboardMarkup, lang: str = "ru") -> InlineKeyboardMarkup:
    """Добавляет строку с кнопкой возврата в главное меню к уже готовой клавиатуре."""
    return InlineKeyboardMarkup(
        inline_keyboard=[*keyboard.inline_keyboard, back_to_menu_row(lang)]
    )


def back_only_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row(lang)])
