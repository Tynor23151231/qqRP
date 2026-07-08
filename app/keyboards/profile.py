from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import L
from app.utils.premium_emoji import emoji


def profile_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Изменить пол", "Change gender"),
                    callback_data="profile:change_gender",
                    icon_custom_emoji_id=emoji("change_gender")[1],
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Статистика", "Stats"),
                    callback_data="profile:stats",
                    icon_custom_emoji_id=emoji("stats")[1],
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Настройки", "Settings"),
                    callback_data="profile:settings",
                    icon_custom_emoji_id=emoji("settings2")[1],
                )
            ],
        ]
    )
