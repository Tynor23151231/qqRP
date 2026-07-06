from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.premium_emoji import emoji


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить пол",
                    callback_data="profile:change_gender",
                    icon_custom_emoji_id=emoji("change_gender")[1],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Статистика", callback_data="profile:stats", icon_custom_emoji_id=emoji("stats")[1]
                )
            ],
            [
                InlineKeyboardButton(
                    text="Настройки", callback_data="profile:settings", icon_custom_emoji_id=emoji("settings2")[1]
                )
            ],
        ]
    )
