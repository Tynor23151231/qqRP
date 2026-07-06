from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import User
from app.utils.premium_emoji import emoji


def main_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    premium_label = "💎 Премиум ✔️" if user.has_premium else "💎 Премиум"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Профиль", callback_data="menu:profile", icon_custom_emoji_id=emoji("profile")[1]
                ),
                InlineKeyboardButton(
                    text="Настройки", callback_data="menu:settings", icon_custom_emoji_id=emoji("settings2")[1]
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Список команд", callback_data="menu:commands", icon_custom_emoji_id=emoji("commands")[1]
                ),
                InlineKeyboardButton(
                    text="Своё RP", callback_data="menu:addrp", icon_custom_emoji_id=emoji("addrp")[1]
                ),
            ],
            [
                InlineKeyboardButton(
                    text=premium_label.replace("💎 ", ""),
                    callback_data="menu:premium",
                    icon_custom_emoji_id=emoji("premium")[1],
                    style="success" if user.has_premium else None,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Как подключить Business",
                    callback_data="menu:howto",
                    icon_custom_emoji_id=emoji("howto")[1],
                ),
            ],
        ]
    )


def back_to_menu_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text="Меню", callback_data="menu:home", icon_custom_emoji_id=emoji("home2")[1]
        )
    ]


def with_back_button(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Добавляет строку с кнопкой возврата в главное меню к уже готовой клавиатуре."""
    return InlineKeyboardMarkup(
        inline_keyboard=[*keyboard.inline_keyboard, back_to_menu_row()]
    )


def back_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row()])
